import asyncio
import json

import httpx

from vic.evidence.connectors.opentargets import OpenTargetsConnector, extract_symbol_tokens

JAK1 = {"id": "ENSG00000000001", "name": "JAK1", "entity": "target", "description": "Janus kinase 1"}
PDCD1 = {"id": "ENSG00000000002", "name": "PDCD1", "entity": "target", "description": "PD-1"}
AMB_A = {"id": "ENSG00000000003", "name": "AMB1", "entity": "target", "description": "A"}
AMB_B = {"id": "ENSG00000000004", "name": "AMB1", "entity": "target", "description": "B"}
HITS = {"JAK1": [JAK1], "PD-1": [PDCD1], "AMB1": [AMB_A, AMB_B], "NOPE1": []}


async def _nosleep(_):
    return None


def _resolve(mechanism, handler=None):
    def default(request):
        q = json.loads(request.content)["variables"]["q"]
        return httpx.Response(200, json={"data": {"search": {"hits": HITS.get(q, [])}}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler or default)) as c:
            return await OpenTargetsConnector(c, sleep=_nosleep, min_interval=0).resolve(mechanism)
    return asyncio.run(go())


def test_token_extraction_ignores_generic_words():
    assert extract_symbol_tokens("selective JAK1 inhibitor") == ["JAK1"]
    assert extract_symbol_tokens("anti-PD-1 antibody") == ["PD-1"]
    assert extract_symbol_tokens("small molecule mRNA siRNA ADC") == []
    assert extract_symbol_tokens("TNF blocker") == ["TNF"]


def test_exact_unique_symbol_is_resolved_without_warning():
    r = _resolve("selective JAK1 inhibitor")
    assert r.status == "resolved" and r.resolved[0].id == "ENSG00000000001" and r.warnings == []


def test_ambiguous_symbol_is_not_chosen_automatically():
    r = _resolve("AMB1 inhibitor")
    assert r.status == "ambiguous" and r.resolved == [] and len(r.ambiguous["AMB1"]) == 2
    assert any("ambiguous" in w and "clarify" in w for w in r.warnings)


def test_synonym_without_exact_match_returns_candidates_not_a_guess():
    r = _resolve("anti-PD-1 antibody")  # symbol is PDCD1, user wrote PD-1
    assert r.status == "ambiguous" and r.resolved == []
    assert "PDCD1" in r.warnings[0] and "Nothing was chosen" in r.warnings[0]


def test_no_symbol_in_text_and_unknown_target():
    assert _resolve("novel small molecule").status == "not_found"
    r = _resolve("NOPE1 inhibitor")
    assert r.status == "not_found" and any("no target found" in w for w in r.warnings)


def test_outage_and_graphql_errors_do_not_crash():
    down = _resolve("JAK1 inhibitor", handler=lambda request: httpx.Response(503))
    assert down.status == "unavailable" and any("NOT evidence" in w for w in down.warnings)
    bad = _resolve("JAK1 inhibitor", handler=lambda request: httpx.Response(200, json={"errors": [{"message": "x"}]}))
    assert bad.status == "unavailable"
    