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
    assert len(pack.sources) == 2 and pack.synthetic is False
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

def test_external_input_limits_preserve_literal_utf8_excerpts_and_user_documents():
    from vic.config import Settings
    from vic.evidence.retrieval import _bounded_external
    literature = [parse_text(f'Paper {i}', 'Український текст про безпеку. ' * 90) for i in range(3)]
    registry = [parse_text(f'Trial {i}', 'Trial terminated for toxicity. ' * 90) for i in range(3)]
    settings = Settings(_env_file=None, retrieval_max_external_documents=2, retrieval_excerpt_max_bytes=150)
    selected = _bounded_external([literature, registry], settings)
    assert [doc.title for doc in selected] == ['Paper 0', 'Trial 0']
    for doc in selected:
        assert len(doc.annotations) == 1
        annotation = doc.annotations[0]
        assert 0 < len(annotation.excerpt.encode('utf-8')) <= 150
        assert annotation.excerpt in doc.unit_by_locator(annotation.locator).text
        assert 'omitted text' in annotation.limitations[-1]
        assert len(doc.text.encode('utf-8')) > 150
    extra = parse_text('User submission', 'User data ' * 200)
    pack = _run(_router(), extra_documents=[extra], settings=settings)
    assert len(pack.sources) == 3
    assert any('partial sample' in warning for warning in pack.retrieval_warnings)
    assert any(e.source_id == extra.source_id and len(e.excerpt.encode()) > 150 for e in pack.evidence)


def test_small_retrieval_defaults_are_sent_to_connectors():
    seen = []
    _run(_router(seen))
    pubmed = [r for r in seen if r.url.path.endswith('esearch.fcgi')]
    trials = [r for r in seen if r.url.host == CT]
    assert pubmed and all(r.url.params['retmax'] == '1' for r in pubmed)
    assert trials and all(r.url.params['pageSize'] == '1' for r in trials)


def test_default_limited_external_pack_fits_translation_request_budget():
    from vic.agents.science.translation import TranslationAnalysis, _build_payload
    from vic.config import Settings
    from vic.evidence.importer import build_pack
    from vic.evidence.retrieval import _bounded_external
    from vic.llm import request_sizes, structured_request
    docs = [parse_text(f'External paper {i}', f'Paper {i}. ' + 'Reported animal findings and safety uncertainty. ' * 1000)
            for i in range(12)]
    selected = _bounded_external([docs[:6], docs[6:]], Settings(_env_file=None))
    imported = build_pack(selected)
    pack = imported.pack
    assert len(pack.sources) == len(pack.evidence) == 2
    assert sum(len(e.excerpt.encode()) for e in pack.evidence) <= 1000
    assert verify_pack(imported) == []
    _, system, messages = structured_request('translation', _build_payload(CASE, pack), TranslationAnalysis, _ctx())
    assert request_sizes(system, messages)['request_bytes'] <= 15500
