"""Índice SQLite tipado para FAOSTAT PP; leitura de CSV em lotes, sem varredura por request."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from threading import Lock
import time
from uuid import uuid4

from openpyxl import load_workbook
from .store import normalized
from .vendor.intelligence.core.errors import ServiceError

CSV = "Prices_E_All_Data_(Normalized).csv"
COUNTRIES = "Agrion_Codigos_Paises_FAOSTAT.xlsx"
HEADERS = ["Area Code", "Area Code (M49)", "Area", "Item Code", "Item Code (CPC)", "Item", "Element Code", "Element", "Year Code", "Year", "Months Code", "Months", "Unit", "Value", "Flag"]
COUNTRY_HEADERS = ["Código FAOSTAT", "Código M49", "País ou área em inglês", "País ou área em português", "ID MapTiler (gid)", "Códigos ISO"]
VERSION = 2
LOCK = Lock()
DOCS = "https://www.fao.org/faostat/en/#data/PP"
ELEMENTS = {
    "5530": ("Producer Price (LCU/tonne)", "LCU", "local_currency_per_tonne"),
    "5531": ("Producer Price (SLC/tonne)", "SLC", "standard_local_currency_per_tonne"),
    "5532": ("Producer Price (USD/tonne)", "USD", "usd_per_tonne"),
    "5539": ("Producer Price Index (2014-2016 = 100)", "", "index_2014_2016_100"),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code(value):
    result = str(value)
    if not re.fullmatch(r"[0-9]+", result):
        raise ValueError("Código FAOSTAT numérico textual inválido.")
    return result


class FaostatStore:
    def __init__(self, root, database=None):
        self.root = Path(root)
        self.database = Path(database) if database is not None else self.root / ".runtime/faostat.sqlite3"
        self._metadata = None

    @property
    def configured(self):
        return all((self.root / name).is_file() for name in (CSV, COUNTRIES))

    def prepare(self):
        if not self.configured:
            return
        with LOCK:
            fingerprint = {"schema": VERSION, "files": {name: sha256(self.root / name) for name in (CSV, COUNTRIES)}}
            if self.database.exists():
                try:
                    with self.connect() as con:
                        metadata = json.loads(con.execute("SELECT value FROM state WHERE key='metadata'").fetchone()[0])
                    if metadata["fingerprint"] == fingerprint:
                        self._metadata = metadata
                        return
                except (sqlite3.DatabaseError, TypeError, KeyError):
                    pass
            self.database.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.database.parent / ("faostat-" + uuid4().hex + ".building.sqlite3")
            start = time.perf_counter()
            try:
                with closing(sqlite3.connect(temporary)) as con:
                    con.executescript("""
                    PRAGMA journal_mode=OFF;
                    PRAGMA synchronous=OFF;
                    CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE countries(area_code TEXT PRIMARY KEY,m49 TEXT,english TEXT,portuguese TEXT,gid TEXT,iso2 TEXT,iso3 TEXT,source_row INTEGER,raw TEXT,search TEXT);
                    CREATE INDEX country_iso2 ON countries(iso2) WHERE iso2 IS NOT NULL;
                    CREATE TABLE areas(code TEXT PRIMARY KEY,m49_raw TEXT,label TEXT);
                    CREATE TABLE items(code TEXT PRIMARY KEY,cpc_raw TEXT,label TEXT,search TEXT);
                    CREATE TABLE elements(code TEXT PRIMARY KEY,label TEXT);
                    CREATE TABLE periods(code TEXT PRIMARY KEY,label TEXT);
                    CREATE TABLE observations(source_row INTEGER PRIMARY KEY,area_code TEXT NOT NULL,item_code TEXT NOT NULL,element_code TEXT NOT NULL,
                        year INTEGER NOT NULL,year_code TEXT NOT NULL,months_code TEXT NOT NULL,unit TEXT NOT NULL,value_text TEXT NOT NULL,value REAL,flag TEXT NOT NULL);
                    """)
                    self._countries(con)
                    total = self._prices(con)
                    con.execute("CREATE INDEX prices_series ON observations(area_code,item_code,year,months_code,element_code,source_row)")
                    con.execute("ANALYZE")
                    metadata = self._summary(con, total, fingerprint)
                    if {name: sha256(self.root / name) for name in (CSV, COUNTRIES)} != fingerprint["files"]:
                        raise ValueError("Fontes FAOSTAT mudaram durante a carga; índice não publicado.")
                    metadata["build_seconds"] = round(time.perf_counter() - start, 3)
                    con.execute("INSERT INTO state VALUES ('metadata',?)", (json.dumps(metadata, ensure_ascii=False),))
                    con.commit()
                temporary.replace(self.database)
                self._metadata = metadata
            finally:
                # Somente arquivo temporário de índice criado por este carregador, na pasta autorizada.
                if temporary.exists():
                    temporary.unlink()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def metadata(self):
        if self._metadata is None:
            raise ServiceError(503, "FAOSTAT_FILES_MISSING", "FAOSTAT indisponível: forneça os dois arquivos originais e reinicie o serviço.")
        return self._metadata

    def _countries(self, con):
        book = load_workbook(self.root / COUNTRIES, read_only=True, data_only=False)
        try:
            if book.sheetnames != ["Países"]:
                raise ValueError("Aba de países FAOSTAT incompatível.")
            iterator = iter(book["Países"].values)
            if list(next(iterator)) != COUNTRY_HEADERS:
                raise ValueError("Cabeçalho de países FAOSTAT incompatível.")
            for line, row in enumerate(iterator, 2):
                if not any(v is not None for v in row):
                    continue
                if any(isinstance(v, str) and v.startswith("=") for v in row):
                    raise ValueError("Países deve fornecer códigos literais, sem fórmulas.")
                area, m49, english, portuguese, gid, iso = row
                area = code(area)
                m49 = str(m49).zfill(3) if m49 is not None else None
                if m49 is not None and not re.fullmatch(r"\d{3}", m49):
                    raise ValueError("M49 inválido na planilha de países.")
                iso2, iso3 = None, None
                if iso:
                    match = re.fullmatch(r"\s*([A-Z]{2})\s*/\s*([A-Z]{3})(?:\s*/\s*[A-Z]{4})?\s*", iso)
                    if not match:
                        raise ValueError("Par ISO inválido; não foi inferido.")
                    iso2, iso3 = match.groups()
                con.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?,?,?,?)", (area, m49, english, portuguese,
                    None if gid is None else str(gid), iso2, iso3, line, json.dumps(dict(zip(COUNTRY_HEADERS, row)), ensure_ascii=False),
                    normalized(" ".join(str(v) for v in row if v is not None))))
        finally:
            book.close()

    def _prices(self, con):
        dimensions = {"areas": {}, "items": {}, "elements": {}, "periods": {}}
        batch, total = [], 0
        with (self.root / CSV).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            if next(reader) != HEADERS:
                raise ValueError("Cabeçalho FAOSTAT PP incompatível.")
            for line, row in enumerate(reader, 2):
                if len(row) != len(HEADERS):
                    raise ValueError(f"Registro CSV inválido: {line}")
                area, m49, label, item, cpc, product, element, measure, yc, ys, month, period, unit, raw_value, flag = row
                for identifier in (area, item, element, month, yc, ys): code(identifier)
                if yc != ys or ys != str(int(ys)) or not 1900 <= int(ys) <= 2100:
                    raise ValueError(f"Ano/código de ano incompatível: {line}")
                value = None
                if raw_value.strip():
                    try:
                        decimal = Decimal(raw_value)
                        value = float(decimal)
                    except (InvalidOperation, ValueError, OverflowError):
                        raise ValueError(f"Valor FAOSTAT não numérico: {line}") from None
                    if not decimal.is_finite() or not math.isfinite(value):
                        raise ValueError(f"Valor FAOSTAT não finito: {line}")
                for table, key, attributes in (("areas", area, (m49, label)), ("items", item, (cpc, product)),
                                                ("elements", element, (measure,)), ("periods", month, (period,))):
                    previous = dimensions[table].setdefault(key, attributes)
                    if previous != attributes:
                        raise ValueError(f"Código com rótulos conflitantes em {table}: {key}")
                batch.append((line, area, item, element, int(ys), yc, month, unit, raw_value, value, flag))
                total += 1
                if len(batch) >= 10000:
                    con.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
                    batch.clear()
            con.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
        for key, (m49, label) in dimensions["areas"].items(): con.execute("INSERT INTO areas VALUES (?,?,?)", (key, m49, label))
        for key, (cpc, label) in dimensions["items"].items(): con.execute("INSERT INTO items VALUES (?,?,?,?)", (key, cpc, label, normalized(key + " " + cpc + " " + label)))
        for table in ("elements", "periods"):
            con.executemany(f"INSERT INTO {table} VALUES (?,?)", [(key, value[0]) for key, value in dimensions[table].items()])
        return total

    def _summary(self, con, total, fingerprint):
        years = con.execute("SELECT min(year),max(year) FROM observations").fetchone()
        mapped = con.execute("SELECT count(*) FROM areas a JOIN countries c ON c.area_code=a.code AND c.m49=ltrim(a.m49_raw, char(39))").fetchone()[0]
        return {"id": "faostat_prices", "file": CSV, "sha256": fingerprint["files"][CSV], "fingerprint": fingerprint,
            "country_mapping": {"file": COUNTRIES, "sha256": fingerprint["files"][COUNTRIES], "records": con.execute("SELECT count(*) FROM countries").fetchone()[0],
                "price_areas_matched_by_code_and_m49": mapped},
            "records": total, "areas": con.execute("SELECT count(*) FROM areas").fetchone()[0],
            "items": con.execute("SELECT count(*) FROM items").fetchone()[0], "year_min": years[0], "year_max": years[1],
            "elements": [dict(zip(("code", "label", "source_unit", "records", "year_min", "year_max"), r)) for r in con.execute("SELECT e.code,e.label,o.unit,count(*),min(o.year),max(o.year) FROM observations o JOIN elements e ON e.code=o.element_code GROUP BY e.code,o.unit ORDER BY e.code")],
            "periods": [dict(zip(("code", "label", "records", "year_min", "year_max"), r)) for r in con.execute("SELECT p.code,p.label,count(*),min(o.year),max(o.year) FROM observations o JOIN periods p ON p.code=o.months_code GROUP BY p.code ORDER BY p.code")],
            "flags": dict(con.execute("SELECT flag,count(*) FROM observations GROUP BY flag")),
            "ambiguous_iso2": [r[0] for r in con.execute("SELECT iso2 FROM countries WHERE iso2 IS NOT NULL GROUP BY iso2 HAVING count(*)>1 ORDER BY iso2")],
            "null_values": con.execute("SELECT count(*) FROM observations WHERE value IS NULL").fetchone()[0],
            "duplicate_keys": con.execute("SELECT count(*) FROM (SELECT 1 FROM observations GROUP BY area_code,item_code,year,months_code,element_code HAVING count(*)>1)").fetchone()[0],
            "indexed_at": datetime.now(timezone.utc).isoformat(), "source_url": DOCS,
            "limitations": ["Snapshot local; não é cotação em tempo real nem previsão de preço.",
                "Preço recebido pelo produtor não é custo de produção nem preço garantido ao talhão.",
                "LCU/SLC não identificam moeda ISO e podem atravessar reformas monetárias; sem conversão presumida.",
                "Índice 2014–2016=100 não é preço por tonelada; unidade vazia e flags são preservadas.",
                "Cobertura varia por produto, país, ano, frequência e elemento; nenhum ausente vira zero."]}

    def source(self):
        meta = self.metadata()
        return {k: meta[k] for k in ("file", "sha256", "country_mapping", "indexed_at", "source_url")}

    def area_code(self, *, area_code=None, country_iso2=None):
        self.metadata()
        if (area_code is None) == (country_iso2 is None):
            raise ServiceError(422, "FAOSTAT_COUNTRY_REQUIRED", "Informe area_code FAOSTAT ou country_iso2, exclusivamente.")
        with self.connect() as con:
            if country_iso2 is not None:
                rows = con.execute("SELECT a.code FROM areas a JOIN countries c ON c.area_code=a.code AND c.m49=ltrim(a.m49_raw,char(39)) WHERE c.iso2=?", (country_iso2,)).fetchall()
            else:
                rows = con.execute("SELECT code FROM areas WHERE code=?", (area_code,)).fetchall()
        if len(rows) > 1:
            raise ServiceError(422, "FAOSTAT_COUNTRY_AMBIGUOUS", "ISO compartilhado por países/áreas históricos; selecione area_code FAOSTAT explicitamente.")
        if not rows:
            raise ServiceError(404, "FAOSTAT_COUNTRY_NOT_FOUND", "País sem correspondência inequívoca com os preços; não foi escolhido outro país.")
        return rows[0][0]

    def countries(self, q=None):
        self.metadata()
        with self.connect() as con:
            rows = con.execute("""SELECT c.*,a.code IS NOT NULL AS has_price_data FROM countries c
                LEFT JOIN areas a ON a.code=c.area_code AND c.m49=ltrim(a.m49_raw,char(39))
                WHERE (? IS NULL OR instr(c.search,?)>0) ORDER BY c.portuguese,c.area_code""", (q, normalized(q) if q else None)).fetchall()
        return {"items": [{"area_code": r["area_code"], "m49": r["m49"], "name": r["english"], "name_pt": r["portuguese"],
            "maptiler_gid": r["gid"], "iso2": r["iso2"], "iso3": r["iso3"], "has_price_data": bool(r["has_price_data"]),
            "source_row": r["source_row"], "raw": json.loads(r["raw"])} for r in rows], "source": self.source()}

    def items(self, q=None, area=None):
        self.metadata()
        clauses, args = [], []
        if q:
            clauses.append("instr(i.search,?)>0"); args.append(normalized(q))
        if area:
            clauses.append("EXISTS (SELECT 1 FROM observations o WHERE o.area_code=? AND o.item_code=i.code)"); args.append(area)
        with self.connect() as con:
            rows = con.execute("SELECT i.code AS item_code,i.cpc_raw,i.label AS name FROM items i" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY i.label,i.code", args).fetchall()
        return {"items": [dict(r) for r in rows], "source": self.source()}

    def prices(self, area, item, start_year, end_year, *, frequency="annual", month=None, element_code=None, limit=100, offset=0):
        self.metadata()
        if start_year > end_year or (month is not None and frequency != "monthly"):
            raise ServiceError(422, "FAOSTAT_PERIOD_INVALID", "Período invertido ou mês sem frequência mensal.")
        where, args = ["o.area_code=?", "o.item_code=?", "o.year BETWEEN ? AND ?"], [area, item, start_year, end_year]
        if frequency == "annual": where.append("o.months_code='7021'")
        elif frequency == "monthly":
            where.append("o.months_code=?" if month is not None else "o.months_code BETWEEN '7001' AND '7012'")
            if month is not None: args.append(str(7000 + month))
        if element_code is not None: where.append("o.element_code=?"); args.append(element_code)
        condition = " AND ".join(where)
        with self.connect() as con:
            total = con.execute("SELECT count(*) FROM observations o WHERE " + condition, args).fetchone()[0]
            rows = con.execute("""SELECT o.*,a.label AS area,a.m49_raw,i.label AS item,i.cpc_raw,e.label AS element,p.label AS months
                FROM observations o JOIN areas a ON a.code=o.area_code JOIN items i ON i.code=o.item_code
                JOIN elements e ON e.code=o.element_code JOIN periods p ON p.code=o.months_code WHERE """ + condition +
                " ORDER BY o.year,o.months_code,o.element_code,o.source_row LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "items": [self.observation(r) for r in rows], "source": self.source()}

    @staticmethod
    def observation(row):
        r = dict(row)
        known = ELEMENTS.get(r["element_code"])
        kind = known[2] if known and known[:2] == (r["element"], r["unit"]) else "unknown"
        raw = [r["area_code"], r["m49_raw"], r["area"], r["item_code"], r["cpc_raw"], r["item"], r["element_code"], r["element"],
               r["year_code"], str(r["year"]), r["months_code"], r["months"], r["unit"], r["value_text"], r["flag"]]
        return {"source_row": r["source_row"], "area_code": r["area_code"], "area_m49": r["m49_raw"].removeprefix("'"), "area": r["area"],
            "item_code": r["item_code"], "item_cpc": r["cpc_raw"].removeprefix("'"), "item": r["item"], "element_code": r["element_code"],
            "element": r["element"], "year": r["year"], "months_code": r["months_code"], "months": r["months"], "unit": r["unit"],
            "value": r["value"], "value_text": r["value_text"], "flag": r["flag"], "value_kind": kind,
            "currency_iso3": "USD" if kind == "usd_per_tonne" else None, "raw": dict(zip(HEADERS, raw))}
