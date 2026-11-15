"""Validação HTTP da base REAL local; rendimento/custos do cenário são CONTROLADOS."""
from pathlib import Path
import json
import statistics
import sys
import time

import httpx


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    report = {"synthetic_prices": False, "financial_yield_and_cost_are_controlled": True, "checks": []}
    with httpx.Client(base_url=base, timeout=120, trust_env=False) as client:
        def get(path, **params):
            r = client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        prefix = "/v1/data/faostat"
        report["metadata"] = get(prefix + "/metadata")
        assert report["metadata"]["records"] == 1319583
        assert report["metadata"]["country_mapping"]["price_areas_matched_by_code_and_m49"] == 182
        br = get(prefix + "/countries", q="Brasil")["items"][0]
        assert (br["area_code"], br["m49"], br["iso2"]) == ("21", "076", "BR")
        queries = [
            ("BR_maize_2024_USD", {"country_iso2": "BR", "item_code": "56", "element_code": "5532"}, 142.2, "usd_per_tonne"),
            ("US_maize_2024_USD", {"country_iso2": "US", "item_code": "56", "element_code": "5532"}, 171.3, "usd_per_tonne"),
            ("BR_maize_2024_index", {"country_iso2": "BR", "item_code": "56", "element_code": "5539"}, 149.49, "index_2014_2016_100"),
            ("Indonesia_maize_Jan2024_LCU", {"area_code": "101", "item_code": "56", "element_code": "5530", "frequency": "monthly", "month": 1}, 6221737.3, "local_currency_per_tonne"),
        ]
        for label, args, expected, kind in queries:
            result = get(prefix + "/prices", start_year=2024, end_year=2024, **args)
            assert result["total"] == 1
            assert result["items"][0]["value"] == expected and result["items"][0]["value_kind"] == kind
            report["checks"].append({"case": label, "response": result})
        absent = get(prefix + "/prices", country_iso2="BR", item_code="56", element_code="5532", start_year=2030, end_year=2030)
        assert absent["total"] == 0 and not absent["items"]
        payload = {"include": ["I14"], "inputs": {"crop_margin": {
            "crop_id": "maize", "start_date": "2026-01-01", "end_date": "2026-12-31", "area_ha": 2,
            "expected_yield_t_per_ha": 3, "cost_per_ha": 200, "currency": "USD",
            "assumptions_reference": "CONTROLLED yield/costs; historical price is not a forecast",
            "faostat_price": {"country_iso2": "BR", "item_code": "56", "year": 2024,
                "reference": "Explicit historical 2024 producer-price assumption for this controlled scenario"}}}}
        response = client.post("/v1/analysis/economics", json=payload)
        response.raise_for_status()
        financial = response.json()
        indicator = financial["result"]["indicators"]["I14"]
        assert abs(indicator["value"] - 453.2) < 1e-9 and indicator["declared_costs"] == 400
        assert indicator["price_per_t_used"] == 142.2 and indicator["quality"]["kind"] == "scenario"
        report["financial_request"] = payload
        report["financial_response"] = financial
        latencies = []
        for _ in range(30):
            started = time.perf_counter()
            get(prefix + "/prices", country_iso2="BR", item_code="56", element_code="5532", start_year=2020, end_year=2024)
            latencies.append((time.perf_counter() - started) * 1000)
        report["http_median_ms"] = statistics.median(latencies)
        report["http_p95_ms"] = sorted(latencies)[28]
        assert client.get("/health").json()["status"] == "ok"
    target = Path(__file__).resolve().parents[1] / ".runtime/faostat-http-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": [r["case"] for r in report["checks"]], "scenario_margin_USD": indicator["value"],
        "controlled_costs_and_yield": True, "http_median_ms": report["http_median_ms"], "report": str(target)}))


if __name__ == "__main__": main()
