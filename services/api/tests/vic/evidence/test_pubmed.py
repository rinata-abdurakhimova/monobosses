import asyncio
from datetime import date

import httpx

from vic.contracts import Scope
from vic.evidence.connectors.pubmed import PubMedConnector, build_queries, parse_pubmed_xml
from vic.evidence.importer import build_pack, verify_pack

XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle><MedlineCitation><PMID>111</PMID><Article>
  <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>Human trial of <i>SYN</i> inhibition</ArticleTitle>
  <Abstract>
   <AbstractText Label="BACKGROUND">Marker M is elevated in disease D.</AbstractText>
   <AbstractText Label="RESULTS">Treatment lowered marker M by 30% in 40 patients.</AbstractText>
  </Abstract>
  <ArticleDate DateType="Electronic"><Year>2020</Year><Month>05</Month><Day>10</Day></ArticleDate>
  <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
 </Article><MeshHeadingList><MeshHeading><DescriptorName>Humans</DescriptorName></MeshHeading></MeshHeadingList></MedlineCitation></PubmedArticle>
 <PubmedArticle><MedlineCitation><PMID>222</PMID><Article>
  <Journal><JournalIssue><PubDate><Year>2022</Year><Month>Mar</Month></PubDate></JournalIssue></Journal>
  <ArticleTitle>Mouse toxicity of a SYN inhibitor</ArticleTitle>
  <Abstract><AbstractText>Liver enzymes rose in treated mice.</AbstractText></Abstract>
  <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
 </Article><MeshHeadingList><MeshHeading><DescriptorName>Mice</DescriptorName></MeshHeading></MeshHeadingList></MedlineCitation></PubmedArticle>
 <PubmedArticle><MedlineCitation><PMID>333</PMID><Article>
  <Journal><JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>Record without abstract</ArticleTitle>
 </Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""

IDS = {"EFF": ["111", "222"], "SAF": ["222"], "NEG": [], "ALL": ["111", "222", "333"]}
QUERIES = {"efficacy": "EFF", "safety": "SAF", "negative": "NEG"}


async def _nosleep(_):
    return None


def _handler(seen=None, fail_term=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        p = request.url.params
        if request.url.path.endswith("esearch.fcgi"):
            if fail_term and p["term"] == fail_term:
                return httpx.Response(500)
            return httpx.Response(200, json={"esearchresult": {"idlist": IDS[p["term"]]}})
        return httpx.Response(200, text=XML)
    return handler


def _search(handler, queries=QUERIES, as_of=None, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            conn = PubMedConnector(client, sleep=_nosleep, min_interval=0, **kw)
            return await conn.search(queries, as_of=as_of)
    return asyncio.run(go())


def test_documents_are_abstract_only_approach_scope_with_metadata():
    res = _search(_handler(), {"efficacy": "EFF", "safety": "SAF", "negative": "NEG"})
    assert res.status == "ok"
    ids = sorted(d.identifier for d in res.documents)
    assert ids == ["PMID111", "PMID222"]  # 222 found by two queries, kept once
    pack = build_pack(res.documents)
    assert verify_pack(pack) == []
    src = {s.document_id: s for s in pack.pack.sources}["PMID111"]
    assert src.url == "https://pubmed.ncbi.nlm.nih.gov/111/" and src.type == "peer_reviewed"
    assert src.synthetic is False
    for ev in pack.pack.evidence:
        assert ev.scope == Scope.APPROACH
        assert any("Abstract only" in x for x in ev.limitations)
    animal = [e for e in pack.pack.evidence if "mice" in e.excerpt.lower()][0]
    assert any("non-human" in x for x in animal.limitations)
    assert any("efficacy, safety" in x for x in animal.limitations)  # found via both queries


def test_record_without_abstract_is_skipped_not_invented():
    res = _search(_handler(), {"all": "ALL"})
    assert "PMID333" not in [d.identifier for d in res.documents]
    assert any("333" in w and "no abstract" in w for w in res.warnings)


def test_no_results_is_not_the_same_as_outage():
    empty = _search(_handler(), {"negative": "NEG"})
    assert empty.status == "empty" and any("returned no records" in w for w in empty.warnings)

    def down(request):
        return httpx.Response(503)

    out = _search(down)
    assert out.status == "unavailable" and out.documents == []
    assert any("NOT evidence of absence" in w for w in out.warnings)


def test_one_failing_query_does_not_kill_the_others():
    res = _search(_handler(fail_term="SAF"))
    assert res.status == "partial" and len(res.documents) == 2
    assert any("[safety]" in w and "did not respond" in w for w in res.warnings)


def test_retry_after_429_then_success():
    calls = {"n": 0}

    def flaky(request):
        if request.url.path.endswith("esearch.fcgi"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429)
            return httpx.Response(200, json={"esearchresult": {"idlist": ["111"]}})
        return httpx.Response(200, text=XML)

    res = _search(flaky, {"efficacy": "EFF"})
    assert calls["n"] == 2 and "PMID111" in [d.identifier for d in res.documents]


def test_as_of_date_filters_and_sets_entrez_date_limit():
    seen = []
    res = _search(_handler(seen), {"efficacy": "EFF"}, as_of=date(2021, 1, 1))
    assert [d.identifier for d in res.documents] == ["PMID111"]  # 222 is dated 2022-03-31 (latest possible)
    assert any("excluded by as_of_date" in w for w in res.warnings)
    es = [r for r in seen if r.url.path.endswith("esearch.fcgi")][0]
    assert es.url.params["datetype"] == "edat" and es.url.params["maxdate"] == "2021/01/01"


def test_api_key_is_sent_but_never_leaked_in_warnings():
    seen = []

    def down(request):
        seen.append(request)
        return httpx.Response(503)

    res = _search(down, api_key="SECRETKEY123", email="a@b.c")
    assert seen[0].url.params["api_key"] == "SECRETKEY123" and seen[0].url.params["tool"]
    assert not any("SECRETKEY123" in w for w in res.warnings)


def test_imprecise_dates_use_latest_possible_and_are_flagged():
    recs = {r.pmid: r for r in parse_pubmed_xml(XML)}
    assert recs["222"].pub_date == date(2022, 3, 31) and recs["222"].date_imprecise
    assert recs["111"].pub_date == date(2020, 5, 10) and not recs["111"].date_imprecise
    assert recs["111"].title == "Human trial of SYN inhibition"  # inline tags stripped


def test_build_queries_cover_efficacy_safety_and_negative_results():
    q = build_queries('PCSK9 "inhibitor"', "hypercholesterolemia")
    assert set(q) == {"efficacy", "safety", "negative"}
    assert '"' not in q["efficacy"].replace('("', "").replace('")', "").replace('" ', "").replace(' "', "")
    assert "failed" in q["negative"] and "toxicity" in q["safety"]
    