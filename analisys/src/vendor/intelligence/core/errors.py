import logging
from typing import get_args

from pydantic import BaseModel

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from src.vendor.intelligence.schemas.common import ErrorInfo, ErrorResponse

logger = logging.getLogger("agrion.errors")


def declared_field_names(annotation, visited=None):
    """Allowlist schema-defined names; never echo arbitrary keys from validation locs."""
    visited = set() if visited is None else visited
    names = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in visited:
            return names
        visited.add(annotation)
        for name, field in annotation.model_fields.items():
            names.add(field.alias or name)
            names.update(declared_field_names(field.annotation, visited))
    else:
        for arg in get_args(annotation):
            names.update(declared_field_names(arg, visited))
    return names


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False,
                 details: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def error_response(error: ServiceError) -> JSONResponse:
    body = ErrorResponse(error=ErrorInfo(code=error.code, message=error.message,
                                       retryable=error.retryable, details=error.details))
    return JSONResponse(status_code=error.status, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Static messages only: never echo values, user-controlled field names,
        # validator messages, exception context or request bodies.
        descriptions = {
            "missing": "Campo obrigatório ausente.",
            "float_type": "O campo exige número JSON, sem texto, booleano ou null.",
            "float_parsing": "Valor numérico inválido.",
            "finite_number": "O campo exige número finito.",
            "greater_than_equal": "Valor abaixo do limite mínimo permitido.",
            "less_than_equal": "Valor acima do limite máximo permitido.",
            "extra_forbidden": "Campo não reconhecido pelo contrato.",
            "literal_error": "Valor fora das opções documentadas.",
            "value_error": "Data, formato ou combinação de campos inválidos.",
            "too_long": "Quantidade de registros acima do limite permitido.",
        }
        issues = list(dict.fromkeys(descriptions.get(issue["type"], "Entrada incompatível com o schema documentado.")
                                    for issue in exc.errors()))
        details = {"issue_count": len(exc.errors()), "issues": issues}
        allowed = set()
        route = request.scope.get("route")
        for field in getattr(getattr(route, "dependant", None), "body_params", []):
            allowed.update(declared_field_names(field.type_))
        paths = []
        for issue in exc.errors():
            loc = issue["loc"]
            if loc and loc[0] == "body" and len(loc) > 1 and all(
                (isinstance(part, int) and part >= 0) or part in allowed for part in loc[1:]
            ):
                paths.append(".".join(str(part) for part in loc[1:]))
        if paths:
            details["fields"] = list(dict.fromkeys(paths))
        return error_response(ServiceError(422, "VALIDATION_ERROR", "Entrada inválida para esta operação.",
                                           details=details))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(ServiceError(exc.status_code, "HTTP_ERROR", "Requisição não atendida."))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("internal_error request_id=%s", getattr(request.state, "request_id", "unknown"))
        return error_response(ServiceError(500, "INTERNAL_ERROR", "Falha interna do serviço."))
