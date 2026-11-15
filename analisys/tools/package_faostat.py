"""Executar de analisys/: python -B tools/package_faostat.py."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.faostat_store import FaostatStore
from src.faostat_snapshot import package, BUNDLE

if __name__ == "__main__":
    store = FaostatStore(ROOT)
    if not store.originals_available:
        raise SystemExit("Atualização exige CSV e planilha originais; nenhum snapshot anterior foi reempacotado.")
    package(store)
    print(f"Snapshot criado: {BUNDLE}, {(ROOT / BUNDLE).stat().st_size} bytes")
