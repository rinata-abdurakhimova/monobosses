import asyncio
import json
from datetime import date

import httpx

from vic.contracts import CaseInput, RunContext, RunMode, Scope
from vic.evidence.connectors.clinicaltrials import STOPPED
from vic.evidence.importer import parse_text, verify_pack
from vic.evidence.retrieval import build_evidence_pack

from .test_clinicaltrials import RECRUITING, TERMINATED
from .test_pubmed import XML

PUBMED, CT, OT = "eutils.ncbi.nlm.nih.gov", "clinicaltrials.gov", "api.platform.opentargets.org"
CASE = CaseInput(indication="Disease D", mechanism="SYN1 inhibitor", scope=Scope.APPROACH)


async def _nosleep(_):
    return None


def _ctx(mode=RunMode.LIVE, as_of=None):
    return RunContext(case_id="c1", run_id="r1", snapshot_id=None, as_of_date=as_of, mode=mode)


def _router(seen=None, down=(), ot_name=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        host = request.url.host
        if host in down:
            return httpx.Response(503)
        if host == PUBMED:
            if request.url.path.endswith("esearch.fcgi"):
                return httpx.Response(200, json={"esearchresult": {"idlist": ["111", "222"]}})
            return httpx.Response(200, text=XML)
        if host == CT:
            status = request.url.params.get("filter.overallStatus")
            return httpx.Response(200, json={"studies": [RECRUITING] if status and status != STOPPED else [TERMINATED]})
        q = json.loads(request.content)["variables"]["q"]
        hit = {"id": "ENSG00000000001", "name": ot_name or q, "entity": "target", "description": "x"}
        return httpx.Response(200, json={"data": {"search": {"hits": [hit]}}})
    return handler


def _run(handler, ctx=None, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await build_evidence_pack(CASE, ctx or _ctx(), client=client, sleep=_nosleep, **kw)
    return asyncio.run(go())


def test_live_pack_combines_literature_and_registry():
    pack = _run(_router())
    assert {s.type for s in pack.sources} == {"peer_reviewed", "registry"}
    assert len(pack.sources) == 4 and pack.synthetic is False
    assert all(not s.synthetic for s in pack.sources)
    assert all(e.source_id in {s.id for s in pack.sources} for e in pack.evidence)
    assert not any("ambiguous" in w for w in pack.retrieval_warnings)


def test_evidence_only_makes_no_external_calls():
    seen = []
    pack = _run(_router(seen), ctx=_ctx(RunMode.EVIDENCE_ONLY))
    assert seen == [] and pack.sources == [] and pack.evidence == []
    assert any("evidence_only" in w for w in pack.retrieval_warnings)


def test_evidence_only_keeps_user_documents():
    doc = parse_text("My data", "Compound X-001 lowered marker M in mice by 48%.")
    pack = _run(_router(), ctx=_ctx(RunMode.EVIDENCE_ONLY), extra_documents=[doc])
    assert [s.type for s in pack.sources] == ["user_upload"] and len(pack.evidence) == 1


def test_one_source_down_gives_partial_pack_with_warning():
    pack = _run(_router(down={PUBMED}))
    assert {s.type for s in pack.sources} == {"registry"}
    assert any("PubMed" in w and "NOT evidence of absence" in w for w in pack.retrieval_warnings)


def test_all_sources_down_returns_empty_pack_not_exception():
    pack = _run(_router(down={PUBMED, CT, OT}))
    assert pack.sources == [] and pack.evidence == []
    assert any("No external evidence was retrieved" in w for w in pack.retrieval_warnings)


def test_ambiguous_target_is_reported_in_warnings():
    pack = _run(_router(ot_name="OTHER"))
    assert any("Target identity not confirmed" in w for w in pack.retrieval_warnings)


def test_historical_mode_skips_registry_and_filters_literature():
    pack = _run(_router(), ctx=_ctx(as_of=date(2021, 1, 1)))
    assert {s.type for s in pack.sources} == {"peer_reviewed"}
    assert [s.document_id for s in pack.sources] == ["PMID111"]  # PMID222 is dated 2022-03-31
    assert any("ClinicalTrials.gov: skipped" in w for w in pack.retrieval_warnings)


def test_slow_source_is_cut_by_deadline_and_others_survive():
    base = _router()

    async def handler(request):
        if request.url.host == PUBMED:
            await asyncio.sleep(5)
        return base(request)

    pack = _run(handler, overall_timeout=0.5)
    assert {s.type for s in pack.sources} == {"registry"}
    assert any("PubMed: did not finish" in w for w in pack.retrieval_warnings)


def test_user_document_is_merged_and_deduplicated_with_external():
    doc = parse_text("My data", "Compound X-001 lowered marker M in mice by 48%.")
    pack = _run(_router(), extra_documents=[doc, doc])
    assert sorted({s.type for s in pack.sources}) == ["peer_reviewed", "registry", "user_upload"]
    assert sum(s.type == "user_upload" for s in pack.sources) == 1

def test_pre_cap_connector_defaults_are_restored_even_with_retired_variables(monkeypatch):
    monkeypatch.setenv('RETRIEVAL_PUBMED_RETMAX', '1')
    monkeypatch.setenv('RETRIEVAL_TRIALS_PAGE_SIZE', '1')
    seen = []
    _run(_router(seen))
    pubmed = [r for r in seen if r.url.path.endswith('esearch.fcgi')]
    trials = [r for r in seen if r.url.host == CT]
    assert pubmed and all(r.url.params['retmax'] == '3' for r in pubmed)
    assert trials and all(r.url.params['pageSize'] == '4' for r in trials)


def test_full_external_records_and_excerpts_survive_pack_assembly():
    from vic.evidence.retrieval import _finish
    docs = [parse_text(f'Paper {i}', f'Paper {i}: ' + 'Untrimmed safety evidence. ' * 1000) for i in range(12)]
    from vic.evidence.importer import Annotation
    for doc in docs:
        doc.annotations = [Annotation(u.text, u.locator, Scope.APPROACH, []) for u in doc.units]
    pack = _finish(docs, [], _ctx())
    assert len(pack.sources) == 12
    expected = {doc.source_id: [u.text for u in doc.units] for doc in docs}
    for evidence in pack.evidence:
        assert evidence.excerpt in expected[evidence.source_id]
    assert sum(len(e.excerpt.encode('utf-8')) for e in pack.evidence) > 1000
