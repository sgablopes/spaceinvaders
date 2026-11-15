"""Seleção explícita das bases normalizadas, sem inferir cultura/estádio ou resolver variantes."""
import math

from .vendor.intelligence.core.errors import ServiceError


def ecocrop_limits(store, crop_id):
    page = store.records("ecocrop", "requisitos", filters={"crop_id": crop_id}, limit=2)
    if page["total"] != 1:
        raise ServiceError(404, "CATALOG_RECORD_NOT_FOUND", "Identificador ECOCROP não encontrado ou não único.")
    row = page["items"][0]["data"]
    lower, upper = row["temp_abs_min_C"], row["temp_abs_max_C"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lower, upper)) or lower >= upper:
        raise ServiceError(503, "CATALOG_REVIEW_REQUIRED", "Faixa ECOCROP ausente ou inconsistente; não foi inferida.")
    return lower, upper, row["url_registro"], page["source"], row["nome_na_fonte"]


def fao_kc(store, selection):
    page = store.records("fao56", "indice_atomico", filters={"ID": selection.record_id, "Parametro": selection.parameter}, limit=2)
    audit = store.records("fao56", "auditoria_registros", filters={"ID": selection.record_id}, limit=2)
    if page["total"] != 1 or audit["total"] != 1:
        raise ServiceError(404, "CATALOG_RECORD_NOT_FOUND", "Kc e auditoria devem ter um registro inequívoco para o ID/parâmetro selecionado.")
    row, qa = page["items"][0]["data"], audit["items"][0]["data"]
    pending_fields = {v.strip() for v in (qa["Campos_nao_escalares"] or "").split(",")}
    permitted = qa["Status_auditoria"] in {"CONFERIDO_ESTRUTURALMENTE", "PENDENTE_INTERPRETAR_FAIXAS_OU_NOTAS"}
    value = row["Valor"]
    if not permitted or selection.parameter in pending_fields or row["Revisao"] != "OK_EXTRAIDO" or row["Unidade"] != "adimensional" or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ServiceError(503, "CATALOG_REVIEW_REQUIRED", "Kc não escalar, ambíguo ou pendente de revisão; não foi escolhida média nem variante.")
    reference = f"{selection.record_id}/{selection.parameter}; PDF p.{row['Pagina_PDF']}; {row['Fonte_DOI']}"
    return value, reference, page["source"], row["Cultura"], qa["Status_auditoria"]
