"""Distribuição do índice FAOSTAT estático; nunca contém dados da aplicação."""
import gzip
import json
import shutil
import sqlite3
from uuid import uuid4

from .faostat_store import VERSION, COUNTRIES, sha256

BUNDLE = "data/faostat.sqlite3.gz"
MANIFEST = "data/faostat.manifest.json"


def restore(store):
    """Valida o snapshot versionado e publica atomicamente no volume existente."""
    manifest = json.loads((store.root / MANIFEST).read_text(encoding="utf-8"))
    if manifest["fingerprint"]["schema"] != VERSION:
        raise ValueError("Versão do snapshot FAOSTAT incompatível.")
    country = store.root / COUNTRIES
    if country.exists() and sha256(country) != manifest["fingerprint"]["files"][COUNTRIES]:
        raise ValueError("Planilha de países diverge do snapshot FAOSTAT; regenere a entrega.")
    expected_size = manifest["database_bytes"]
    if not isinstance(expected_size, int) or not 0 < expected_size <= 1024 ** 3:
        raise ValueError("Tamanho do snapshot FAOSTAT inválido.")
    if store.database.exists() and sha256(store.database) == manifest["database_sha256"]:
        store._metadata = validate_database(store.database, manifest)
        return
    bundle = store.root / BUNDLE
    if sha256(bundle) != manifest["gzip_sha256"]:
        raise ValueError("Checksum do pacote FAOSTAT inválido; índice anterior preservado.")
    store.database.parent.mkdir(parents=True, exist_ok=True)
    temporary = store.database.parent / ("faostat-" + uuid4().hex + ".building.sqlite3")
    try:
        written = 0
        with gzip.open(bundle, "rb") as source, temporary.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                written += len(chunk)
                if written > expected_size:
                    raise ValueError("Snapshot FAOSTAT excede tamanho declarado.")
                target.write(chunk)
        if written != expected_size or sha256(temporary) != manifest["database_sha256"]:
            raise ValueError("Checksum/tamanho do banco FAOSTAT inválido.")
        metadata = validate_database(temporary, manifest)
        temporary.replace(store.database)
        store._metadata = metadata
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_database(path, manifest):
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("Integridade SQLite FAOSTAT inválida.")
        metadata = json.loads(con.execute("SELECT value FROM state WHERE key='metadata'").fetchone()[0])
        if metadata["fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Procedência do banco diverge do manifesto FAOSTAT.")
        return metadata
    finally:
        con.close()


def package(store):
    """Empacota apenas o índice derivado das duas fontes originais validadas."""
    store.prepare()
    metadata = store.metadata()
    bundle = store.root / BUNDLE
    bundle.parent.mkdir(parents=True, exist_ok=True)
    # Backup SQLite consistente, sem copiar um arquivo que possa estar em escrita.
    backup = store.database.parent / ("faostat-package-" + uuid4().hex + ".sqlite3")
    try:
        con = sqlite3.connect(backup)
        try:
            with store.connect() as source:
                source.backup(con)
        finally:
            con.close()
        with backup.open("rb") as source, bundle.open("wb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0, compresslevel=9) as packed:
                shutil.copyfileobj(source, packed)
        manifest = {"fingerprint": metadata["fingerprint"], "database_bytes": backup.stat().st_size,
                    "database_sha256": sha256(backup), "gzip_sha256": sha256(bundle)}
        (store.root / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest
    finally:
        if backup.exists():
            backup.unlink()
