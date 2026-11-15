"""GAEZ v5 ao vivo: API JSON pública do bucket FAO + leitura HTTP por janela."""
from datetime import datetime, timezone
import math
import re
from urllib.parse import quote

import httpx
import rasterio
from rasterio.warp import transform

BUCKET = "fao-gismgr-gaez-v5-data"
PREFIX = "DATA/GAEZ-V5/MAPSET/"
API = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
MEDIA = f"https://storage.googleapis.com/{BUCKET}/"
DOCUMENTATION = "https://github.com/un-fao/gaezv5/wiki/21.-GAEZ-v5-Platform-User-Guide"
LAYER_PATTERN = r"DATA/GAEZ-V5/MAPSET/[A-Z0-9-]+/GAEZ-V5\.[A-Za-z0-9_.-]+\.tif"


class ExternalError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Gaez:
    def __init__(self, client=None):
        self.client = client or httpx.Client(timeout=httpx.Timeout(20, connect=5), follow_redirects=False)

    def close(self):
        self.client.close()

    def _get(self, path="", params=None):
        try:
            response = self.client.get(API + path, params=params)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Objeto JSON esperado da fonte externa.")
            return data
        except httpx.TimeoutException as exc:
            raise ExternalError(504, "GAEZ: tempo limite da fonte externa excedido.") from exc
        except httpx.HTTPStatusError as exc:
            status = 404 if exc.response.status_code == 404 else 502
            raise ExternalError(status, "GAEZ: camada não encontrada." if status == 404 else "GAEZ: fonte externa indisponível.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalError(502, "GAEZ: erro de comunicação ou resposta inválida da fonte externa.") from exc

    def layers(self, variable=None, filename_prefix=None, limit=50, page_token=None):
        prefix = PREFIX
        if variable:
            prefix += variable + "/"
            if filename_prefix:
                prefix += filename_prefix
        params = {"prefix": prefix, "maxResults": limit,
                  "fields": "items(name,size,updated),nextPageToken"}
        if page_token:
            params["pageToken"] = page_token
        data = self._get(params=params)
        return {"source": "FAO/IIASA GAEZ v5", "source_url": str(httpx.URL(API, params=params)),
                "accessed_at": datetime.now(timezone.utc).isoformat(),
                "next_page_token": data.get("nextPageToken"),
                "items": [{**item, "layer": item["name"], "url": MEDIA + quote(item["name"], safe="/")}
                          for item in data.get("items", []) if re.fullmatch(LAYER_PATTERN, item.get("name", ""))],
                "warnings": ["Paginação corresponde aos objetos externos; uma página pode conter zero GeoTIFFs.",
                             "Selecione produto, cultura, período e manejo compatíveis antes de comparar."]}

    def point(self, layer, latitude, longitude):
        if not re.fullmatch(LAYER_PATTERN, layer):
            raise ValueError("Camada inválida; selecione um identificador retornado em /gaez/layers.")
        metadata = self._get("/" + quote(layer, safe=""), {"fields": "name,size,updated,generation,metadata"})
        url = MEDIA + quote(layer, safe="/")
        tokens = layer.rsplit("/", 1)[-1].removesuffix(".tif").split(".")
        dimensions = {"version": tokens[0], "variable": tokens[1], "tokens": tokens[2:]}
        if len(tokens) == 7:
            dimensions.update(zip(("period", "climate", "scenario", "crop", "management"), tokens[2:]))
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                              GDAL_HTTP_TIMEOUT="20", GDAL_HTTP_MAX_RETRY="0", VSI_CACHE=False):
                with rasterio.open(url) as raster:
                    if raster.crs is None:
                        raise ExternalError(502, "GAEZ: raster sem sistema de coordenadas.")
                    x, y = transform("EPSG:4326", raster.crs, [longitude], [latitude])
                    if not (raster.bounds.left <= x[0] < raster.bounds.right and raster.bounds.bottom < y[0] <= raster.bounds.top):
                        raise ExternalError(404, "GAEZ: coordenada fora da cobertura da camada.")
                    sample = next(raster.sample([(x[0], y[0])], indexes=1, masked=True))[0]
                    raw = None if bool(getattr(sample, "mask", False)) else float(sample)
                    if raw is not None and not math.isfinite(raw):
                        raw = None
                    scale, offset = raster.scales[0], raster.offsets[0]
                    return {"source": "FAO/IIASA GAEZ v5", "layer": layer, "source_url": url,
                            "documentation": DOCUMENTATION, "accessed_at": datetime.now(timezone.utc).isoformat(),
                            "object_metadata": metadata, "latitude": latitude, "longitude": longitude,
                            "dimensions_from_filename": dimensions,
                            "status": "nodata" if raw is None else "ok", "raw_value": raw,
                            "value": None if raw is None else raw * scale + offset,
                            "unit": raster.units[0], "band_scale": scale, "band_offset": offset,
                            "crs": str(raster.crs), "resolution": list(raster.res),
                            "tags": {**raster.tags(), **raster.tags(1)},
                            "warnings": ["Valor regional modelado, não medição do talhão nem previsão de colheita.",
                                         "Escala e unidade são apenas as declaradas no GeoTIFF; se ausentes, conferir a documentação do produto antes de interpretar.",
                                         "Resolução está em unidades do CRS; consulta ao pixel, sem média do talhão."]}
        except ExternalError:
            raise
        except (rasterio.errors.RasterioError, OSError, ValueError) as exc:
            raise ExternalError(502, "GAEZ: não foi possível ler o pixel remoto; verifique disponibilidade e suporte a HTTP Range da fonte.") from exc
