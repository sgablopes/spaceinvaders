"""Índice descartável; fontes sempre abertas somente para leitura."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sqlite3
import unicodedata
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

VERSION = 1
FILES = {
    "aquacrop": "0. Modelo_Entrada App Git - AquaCrop.xlsx",
    "ecocrop": "1. Requisitos por Cultura - ECOCROP - 2568 Especies.xlsx",
    "fao56": "2. FAO - Diretrizes para o cálculo das necessidades hídricas das culturas.xlsx",
    "conhecimento": "4. Base de conhecimento GERAL - Embrapa e afins.zip",
}
KNOWLEDGE_TABLES = {
    "culturas", "fontes", "fonte_culturas", "evidencias", "evidencia_culturas",
    "calendarios", "rotacoes", "pragas_doencas", "manejo_solo",
}
WARNINGS = {
    "ecocrop": ["Requisitos gerais de espécies; não são aptidão local ou recomendação agronômica."],
    "fao56": ["Faixas e variantes permanecem literais; consultar auditorias e limitações metodológicas.",
              "Esta API disponibiliza tabelas; não implementa cálculo de ETo."],
    "aquacrop": ["Contrato intermediário Agrion, não formato nativo AquaCrop nem simulação executada.",
                 "Abas de entrada vazias não representam observações disponíveis."],
    "conhecimento": ["Conferência documental não equivale a validação agronômica local.",
                     "Relação mandioca → milho requer revisão antes de qualquer recomendação.",
                     "Quarentena e históricos não integram as tabelas ativas; direitos variam por fonte."],
}


def normalized(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      default=lambda v: v.isoformat() if isinstance(v, (date, datetime)) else str(v))


def hashes(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FILES.values()}


class Store:
    def __init__(self, root: Path, database: Path):
        self.root, self.database = root.resolve(), database.resolve()
        if not self.database.is_relative_to(self.root):
            raise ValueError("O índice deve ficar dentro de analisys/.")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(f"{self.database.as_uri()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def prepare(self):
        fingerprint = {"schema_version": VERSION, "files": hashes(self.root)}
        if self.database.exists():
            with self.connect() as con:
                try:
                    previous = json.loads(con.execute("SELECT value FROM state WHERE key='fingerprint'").fetchone()[0])
                    if previous == fingerprint:
                        return
                except (sqlite3.DatabaseError, TypeError):
                    pass
        self.database.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.database.with_suffix(".building")
        con = sqlite3.connect(temporary)
        try:
            con.executescript("""
                DROP TABLE IF EXISTS state;
                DROP TABLE IF EXISTS datasets;
                DROP TABLE IF EXISTS tables;
                DROP TABLE IF EXISTS records;
                DROP TABLE IF EXISTS documents;
                CREATE TABLE state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE datasets(id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
                CREATE TABLE tables(dataset TEXT, name TEXT, metadata TEXT NOT NULL,
                                    PRIMARY KEY(dataset,name));
                CREATE TABLE records(dataset TEXT, tab TEXT, row_number INTEGER,
                                     data TEXT NOT NULL, search TEXT NOT NULL,
                                     PRIMARY KEY(dataset,tab,row_number));
                CREATE TABLE documents(name TEXT PRIMARY KEY, data TEXT NOT NULL);
            """)
            for dataset, filename in FILES.items():
                source = {"file": filename, "sha256": fingerprint["files"][filename],
                          "warnings": WARNINGS[dataset]}
                con.execute("INSERT INTO datasets VALUES (?,?)", (dataset, dump(source)))
                if filename.endswith(".xlsx"):
                    self._workbook(con, dataset, self.root / filename)
                else:
                    self._knowledge(con, self.root / filename)
            for key, value in {"fingerprint": fingerprint, "indexed_at": datetime.now(timezone.utc).isoformat()}.items():
                con.execute("INSERT INTO state VALUES (?,?)", (key, dump(value)))
            con.commit()
        finally:
            con.close()
        temporary.replace(self.database)

    def _table(self, con, dataset, name, columns, rows, locator):
        if not columns or any(not isinstance(c, str) or not c.strip() for c in columns) or len(set(columns)) != len(columns):
            raise ValueError(f"Cabeçalhos inválidos: {dataset}/{name}")
        count = 0
        for row_number, values in rows:
            if not any(v is not None and v != "" for v in values):
                continue
            record = {key: (None if value == "" else value) for key, value in zip(columns, values)}
            payload = dump(record)
            search = normalized(" ".join(str(v) for v in record.values() if v is not None))
            con.execute("INSERT INTO records VALUES (?,?,?,?,?)", (dataset, name, row_number, payload, search))
            count += 1
        metadata = {"name": name, "columns": columns, "total": count, "locator": locator,
                    "values": "Cabeçalhos e unidades preservados; vazios são null; IDs CSV são texto."}
        con.execute("INSERT INTO tables VALUES (?,?,?)", (dataset, name, dump(metadata)))

    def _workbook(self, con, dataset, path):
        book = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in book:
                iterator = iter(sheet.values)
                columns = list(next(iterator))
                # A primeira linha de LEIA_PRIMEIRO é o título, não um cabeçalho tabular.
                if sheet.title == "LEIA_PRIMEIRO":
                    first = tuple(columns)
                    rows = [(1, first), *enumerate(iterator, 2)]
                    columns = ["campo", "descricao"]
                else:
                    rows = enumerate(iterator, 2)
                self._table(con, dataset, sheet.title.lower(), columns, rows, {"sheet": sheet.title})
        finally:
            book.close()

    def _knowledge(self, con, path):
        with zipfile.ZipFile(path) as archive:
            prefix = "agrion-knowledge-base-v0.4.0/"
            manifest = json.loads(archive.read(prefix + "manifesto.json"))
            for name, expected in manifest["checksums_sha256"].items():
                if hashlib.sha256(archive.read(prefix + name)).hexdigest() != expected:
                    raise ValueError(f"Checksum da biblioteca divergente: {name}")
            for table in sorted(KNOWLEDGE_TABLES):
                member = prefix + table + ".csv"
                reader = csv.reader(io.StringIO(archive.read(member).decode("utf-8-sig")))
                self._table(con, "conhecimento", table, next(reader), enumerate(reader, 2),
                            {"member": member, "version": manifest["versao"]})
            for name in archive.namelist():
                short = name.removeprefix(prefix)
                if "/" not in short and short.endswith((".json", ".md")):
                    content = archive.read(name).decode("utf-8-sig")
                    value = json.loads(content) if short.endswith(".json") else content
                    con.execute("INSERT INTO documents VALUES (?,?)", (short, dump(value)))

    def datasets(self):
        with self.connect() as con:
            return [{"id": r["id"], **json.loads(r["metadata"])} for r in con.execute("SELECT * FROM datasets ORDER BY id")]

    def tables(self, dataset):
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute("SELECT metadata FROM tables WHERE dataset=? ORDER BY name", (dataset,))]

    def metadata(self, dataset, table):
        with self.connect() as con:
            result = con.execute("SELECT metadata FROM tables WHERE dataset=? AND name=?", (dataset, table)).fetchone()
            if result is None:
                raise KeyError(table)
            return json.loads(result[0])

    def records(self, dataset, table, limit=50, offset=0, q=None, filters=None):
        meta = self.metadata(dataset, table)
        clauses, parameters = ["dataset=?", "tab=?"], [dataset, table]
        if q:
            clauses.append("instr(search, ?) > 0")
            parameters.append(normalized(q))
        for field, value in (filters or {}).items():
            if field not in meta["columns"]:
                raise ValueError(f"Campo desconhecido: {field}")
            if isinstance(value, (dict, list)):
                raise ValueError("Filtros devem conter valores escalares ou null.")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Filtros numéricos devem ser finitos.")
            clauses.append("json_extract(data, ?) IS ?")
            parameters.extend(['$."' + field.replace('"', '\\"') + '"', value])
        where = " AND ".join(clauses)
        with self.connect() as con:
            total = con.execute("SELECT count(*) FROM records WHERE " + where, parameters).fetchone()[0]
            rows = con.execute("SELECT row_number,data FROM records WHERE " + where + " ORDER BY row_number LIMIT ? OFFSET ?",
                               [*parameters, limit, offset]).fetchall()
            source = json.loads(con.execute("SELECT metadata FROM datasets WHERE id=?", (dataset,)).fetchone()[0])
        return {"dataset": dataset, "table": table, "total": total, "limit": limit, "offset": offset,
                "source": {**source, **meta["locator"]},
                "items": [{"source_row": r["row_number"], "data": json.loads(r["data"])} for r in rows]}

    def documents(self, name=None):
        with self.connect() as con:
            if name is None:
                return [r[0] for r in con.execute("SELECT name FROM documents ORDER BY name")]
            row = con.execute("SELECT data FROM documents WHERE name=?", (name,)).fetchone()
            if row is None:
                raise KeyError(name)
            return json.loads(row[0])
