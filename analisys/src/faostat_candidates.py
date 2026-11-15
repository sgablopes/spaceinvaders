"""Comparação lexical entre catálogos locais; nunca equivale a revisão agronômica."""
import re
from .store import normalized


def words(text):
    # Singularização lexical simples, explicitamente usada apenas para candidatos.
    result = set()
    for word in re.findall(r"[a-z0-9]+", normalized(text or "")):
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 4 and word.endswith("oes"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        result.add(word)
    return result


def candidates(local, faostat, query, area=None):
    query = query.strip()
    knowledge = local.records("conhecimento", "culturas", limit=500, q=query)
    eco = local.records("ecocrop", "culturas", limit=100, q=query)
    # Permite partir de um ID ECO ou nome científico, mantendo IDs dos catálogos distintos.
    known = {r["data"]["cultura_id"]: r for r in knowledge["items"]}
    for entry in eco["items"]:
        scientific = entry["data"].get("nome_cientifico")
        if scientific:
            linked = local.records("conhecimento", "culturas", limit=500, filters={"nome_cientifico": scientific})
            known.update({r["data"]["cultura_id"]: r for r in linked["items"]})
    eco_rows = {r["data"]["crop_id"]: r for r in eco["items"]}
    for entry in known.values():
        scientific = entry["data"].get("nome_cientifico")
        if scientific:
            linked = local.records("ecocrop", "culturas", limit=100, filters={"nome_cientifico": scientific})
            eco_rows.update({r["data"]["crop_id"]: r for r in linked["items"]})
    catalog = faostat.items(area=area)
    found = []
    direct = words(query)
    for item in catalog["items"]:
        label = words(item["name"])
        evidence = []
        complete = False
        if direct and direct <= label:
            evidence.append({"kind": "faostat_label_tokens", "matched_terms": sorted(direct)})
            complete = True
        for entry in known.values():
            data = entry["data"]
            for alias in (data.get("nomes_en") or "").split("|"):
                alias_words = words(alias)
                overlap = alias_words & label
                # Adjetivos comerciais isolados não identificam a cultura.
                informative = overlap - {"common", "dry", "fresh", "raw", "other", "green"}
                if informative:
                    complete = complete or alias_words <= label
                    evidence.append({"kind": "knowledge_english_alias_tokens", "cultura_id": data["cultura_id"],
                        "source_row": entry["source_row"], "alias": alias.strip(), "matched_terms": sorted(overlap),
                        "all_alias_terms_matched": alias_words <= label})
        if evidence:
            found.append({**item, "mapping_status": "candidate_unreviewed", "evidence": evidence,
                          "match_strength": "complete_alias_tokens" if complete else "partial_alias_tokens"})
    complete_matches = [item for item in found if item["match_strength"] == "complete_alias_tokens"]
    partial_matches = [item for item in found if item["match_strength"] == "partial_alias_tokens"]
    return {"query": query, "mapping_status": "candidate_unreviewed", "requires_review": True,
        "selected_item_code": None, "candidates": complete_matches or partial_matches,
        "additional_partial_candidates": partial_matches if complete_matches else [],
        "knowledge_cultures": list(known.values()), "ecocrop_cultures": list(eco_rows.values()),
        "search_coverage": {"knowledge_matches": knowledge["total"], "ecocrop_matches": eco["total"],
            "ecocrop_direct_returned": len(eco["items"]), "ecocrop_direct_truncated": eco["total"] > len(eco["items"])},
        "sources": {"faostat": catalog["source"], "knowledge": knowledge["source"], "ecocrop": eco["source"]},
        "method": "lexical_tokens_with_simple_english_plural_reduction_using_existing_aliases",
        "limitations": ["Candidatos lexicais, sem tradução inventada, equivalência validada ou escolha automática.",
            "Espécie, finalidade e produto comercial podem diferir; confirme grão/verde, seco/fresco e demais recortes.",
            "Um único candidato também exige revisão; ausência não autoriza substituir produto.",
            "Nomes científicos ligam registros locais por igualdade literal; não há inferência taxonômica."]}
