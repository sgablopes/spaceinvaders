"""Importação explícita e versionada do núcleo anterior, sem alterar sua origem."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "core/__init__.py", "core/errors.py",
    "schemas/__init__.py", "schemas/common.py", "schemas/gdd.py", "schemas/rainfall.py",
    "schemas/indicators.py", "schemas/analysis.py",
    "indicators/__init__.py", "indicators/gdd.py", "indicators/gdd_service.py",
    "indicators/rainfall_accumulation.py", "indicators/rainfall_service.py",
    "indicators/analysis.py", "indicators/catalog.py",
]


def transform(text, name):
    text = re.sub(r"(?m)^(\s*)from app\.", r"\1from src.vendor.intelligence.", text)
    if name == "indicators/analysis.py":
        text = text.replace("def analyze(group: str, payload, request_id: str):",
                            "def analyze(group: str, payload, request_id: str, *, bindings=None, response_model=None):\n    bindings = BINDINGS if bindings is None else bindings")
        text = text.replace("BINDINGS[identifier]", "bindings[identifier]")
        text = text.replace("return RESPONSE_MODELS[group](", "return (response_model or RESPONSE_MODELS[group])(")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    destination = ROOT / "src" / "vendor" / "intelligence"
    manifest = {"origin": "agrion-intelligence/app", "files": {},
                "adaptations": ["Imports absolutos remapeados para pacote isolado.",
                                "Orquestrador recebe bindings/response_model opcionais; comportamento padrão preservado.",
                                "Fórmulas e validações não alteradas."]}
    for name in FILES:
        raw = (args.source / "app" / name).read_bytes()
        content = transform(raw.decode("utf-8-sig").replace("\r\n", "\n"), name).encode("utf-8")
        target = destination / name
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError(f"Destino já contém versão diferente: {name}; revisar antes de atualizar.")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        manifest["files"][name] = {"source_sha256": hashlib.sha256(raw).hexdigest(),
                                   "packaged_sha256": hashlib.sha256(content).hexdigest()}
    for path in (ROOT / "src/vendor/__init__.py", destination / "__init__.py"):
        if not path.exists():
            path.write_text('"""Componentes anteriores preservados e versionados."""\n', encoding="utf-8")
    manifest_path = destination / "manifest.json"
    rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists():
        if manifest_path.read_text(encoding="utf-8") != rendered:
            raise ValueError("Manifesto existente divergente; revisar atualização explicitamente.")
    else:
        manifest_path.write_text(rendered, encoding="utf-8")
    print(f"{len(FILES)} módulos importados; origem preservada.")


if __name__ == "__main__":
    main()
