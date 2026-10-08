import asyncio
from datetime import date

import httpx

from vic.contracts import Scope
from vic.evidence.connectors.clinicaltrials import STOPPED, ClinicalTrialsConnector, _ct_date
from vic.evidence.importer import build_pack, verify_pack


async def _nosleep(_):
    return None


def _study(nct, title, status, why=None, first="2021-06-15", has_results=False):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": title},
            "statusModule": {
                "overallStatus": status,
                **({"whyStopped": why} if why else {}),
                "startDateStruct": {"date": "2021-07"},
                "studyFirstPostDateStruct": {"date": first},
                "lastUpdatePostDateStruct": {"date": "2023-01-10"},
            },
            "descriptionModule": {"briefSummary": "A phase 2 study of a SYN-1 inhibitor."},
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
            "conditionsModule": {"conditions": ["Disease D"]},
            "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "X-001"}]},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Synthetic Pharma"}},
        },
        "hasResults": has_results,
    }


TERMINATED = _study("NCT00000001", "X-001 in Disease D", "TERMINATED", why="Lack of efficacy")
RECRUITING = _study("NCT00000002", "Competitor Y in Disease D", "RECRUITING", first="2024-02")


def _handler(seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        status = request.url.params.get("filter.overallStatus")
        if status == STOPPED:
            return httpx.Response(200, json={"studies": [TERMINATED]})
        if status:
            return httpx.Response(200, json={"studies": [RECRUITING], "nextPageToken": "abc"})
        return httpx.Response(200, json={"studies": [TERMINATED]})
    return handler


def _search(handler, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            conn = ClinicalTrialsConnector(client, sleep=_nosleep, min_interval=0)
            return await conn.search(condition="Disease D", intervention="SYN-1 inhibitor", **kw)
    return asyncio.run(go())


def test_stopped_trial_and_competitor_are_captured_with_provenance():
    res = _search(_handler())
    assert res.status == "ok"
    assert sorted(d.identifier for d in res.documents) == ["NCT00000001", "NCT00000002"]  # deduplicated
    pack = build_pack(res.documents)
    assert verify_pack(pack) == []
    src = {s.document_id: s for s in pack.pack.sources}["NCT00000001"]
    assert src.type == "registry" and src.url == "https://clinicaltrials.gov/study/NCT00000001"
    assert src.synthetic is False
    texts = [e.excerpt for e in pack.pack.evidence if e.source_id == src.id]
    assert any("TERMINATED" in t and "Lack of efficacy" in t for t in texts)
    for ev in pack.pack.evidence:
        assert ev.scope == Scope.APPROACH
        assert any("not a published result" in x for x in ev.limitations)
    term_ev = [e for e in pack.pack.evidence if "Why stopped" in e.excerpt][0]
    assert any("non-scientific" in x for x in term_ev.limitations)
    assert any("intervention, stopped" in x for x in term_ev.limitations)  # found via two queries


def test_more_results_than_page_is_disclosed():
    res = _search(_handler())
    assert any("more studies match" in w for w in res.warnings)


def test_historical_mode_skips_registry_without_any_request():
    seen = []
    res = _search(_handler(seen), as_of=date(2022, 1, 1))
    assert res.status == "skipped" and res.documents == [] and seen == []
    assert any("skipped" in w and "as_of_date" in w for w in res.warnings)


def test_outage_is_not_confused_with_empty_result():
    out = _search(lambda request: httpx.Response(503))
    assert out.status == "unavailable" and any("NOT evidence of absence" in w for w in out.warnings)
    empty = _search(lambda request: httpx.Response(200, json={"studies": []}))
    assert empty.status == "empty" and any("returned no studies" in w for w in empty.warnings)


def test_malformed_response_does_not_crash():
    res = _search(lambda request: httpx.Response(200, text="<html>oops</html>"))
    assert res.status == "unavailable" and res.documents == []


def test_registry_dates_use_latest_possible_when_imprecise():
    assert _ct_date("2024-02") == (date(2024, 2, 29), True)
    assert _ct_date("2021-06-15") == (date(2021, 6, 15), False)
    assert _ct_date("2020") == (date(2020, 12, 31), True)
    assert _ct_date("garbage") == (None, False)

def test_first_posted_date_is_read_from_real_api_field():
    res = _search(_handler())
    by_id = {d.identifier: d for d in res.documents}
    assert str(by_id["NCT00000001"].published_at) == "2021-06-15"
    assert str(by_id["NCT00000002"].published_at) == "2024-02-29"  # imprecise: latest possible
