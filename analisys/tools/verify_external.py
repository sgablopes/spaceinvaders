"""Smoke test opt-in com GAEZ real. Executar a partir de analisys/."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.gaez import ExternalError, Gaez


def main():
    gaez = Gaez()
    report = {"synthetic": False, "source": "FAO/IIASA GAEZ v5", "queries": []}
    try:
        page = gaez.layers("RES05-SIX", "GAEZ-V5.RES05-SIX.HP0120", 500)
        report["catalog_source"] = page["source_url"]
        report["first_layers"] = [r["layer"] for r in page["items"][:3]]
        report["crop_codes_in_page"] = sorted({r["layer"].split(".")[-3] for r in page["items"]})
        for crop in ("MZE", "SOY"):
            candidates = [r for r in page["items"] if f".{crop}." in r["layer"] and ".HRLM." in r["layer"]]
            if not candidates:
                report["queries"].append({"crop": crop, "status": "not_in_first_catalog_page"})
                continue
            layer = candidates[0]["layer"]
            try:
                report["queries"].append(gaez.point(layer, -16.5, -49.3))
            except ExternalError as exc:
                report["queries"].append({"layer": layer, "http_status": exc.status, "error": exc.message})
    except ExternalError as exc:
        report["error"] = {"http_status": exc.status, "message": exc.message}
    finally:
        gaez.close()
    destination = Path(__file__).resolve().parents[1] / ".runtime" / "gaez-live-check.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
