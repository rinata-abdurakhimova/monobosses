import asyncio

import httpx

from vic.evidence.connectors.pubmed import PubMedConnector

XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle><MedlineCitation><PMID>901</PMID><Article>
  <Journal><JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>Positive trial</ArticleTitle>
  <Abstract><AbstractText>Treatment reduced marker M by 30%.</AbstractText></Abstract>
 </Article></MedlineCitation></PubmedArticle>
 <PubmedArticle><MedlineCitation><PMID>902</PMID><Article>
  <Journal><JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue></Journal>
  <ArticleTitle>Negative trial</ArticleTitle>
  <Abstract><AbstractText>Treatment failed to show efficacy on marker M.</AbstractText></Abstract>
 </Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


async def _nosleep(_):
    return None


def test_positive_and_negative_results_are_both_kept():
    def handler(request):
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["901", "902"]}})
        return httpx.Response(200, text=XML)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            conn = PubMedConnector(client, sleep=_nosleep, min_interval=0)
            return await conn.search({"efficacy": "ANY"})

    res = asyncio.run(go())
    texts = " ".join(d.text for d in res.documents).lower()
    assert sorted(d.identifier for d in res.documents) == ["PMID901", "PMID902"]
    assert "reduced marker m" in texts and "failed to show efficacy" in texts  # nothing is "resolved" away