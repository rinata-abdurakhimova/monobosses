import asyncio
from pathlib import Path

import pytest

from vic.contracts import EvidencePack, Scope, UploadedDocument
from vic.evidence import fixtures
from vic.evidence.errors import InvalidDocument, UnreadableDocument, UnsupportedDocument
from vic.evidence.importer import (
    build_pack,
    import_document,
    parse_document,
    parse_json,
    parse_pdf,
    parse_text,
    verify_pack,
)
from vic.evidence.normalization import content_hash, excerpt_in_text, normalize_text

from .pdf_helpers import make_pdf

TEXT = (
    "# Findings\n\n"
    "Compound X-001 reduced marker M in mice by 48%.\n\n"
    "# Gaps\n\n"
    "Human exposure has not been measured."
)
R2_FIXTURE = Path(__file__).resolve().parents[5] / "contracts" / "fixtures" / "evidence-pack.json"


def _upload(filename, content, ctype, title="Doc", synthetic=False):
    return UploadedDocument(
        filename=filename, content_type=ctype, content=content, title=title, synthetic=synthetic
    )


# ---- text / JSON

def test_text_import_excerpt_exists_in_document():
    result = build_pack([parse_text("My note", TEXT)])
    assert verify_pack(result) == []
    assert len(result.pack.evidence) == 2
    ev = result.pack.evidence[0]
    assert ev.locator == "section: Findings, paragraph 1"
    assert excerpt_in_text(ev.excerpt, result.documents[0].text)


def test_user_upload_provenance_and_default_scope():
    result = build_pack([parse_text("My note", TEXT)])
    src = result.pack.sources[0]
    assert src.synthetic is False and src.type == "user_upload"
    assert src.content_hash.startswith("sha256:")
    assert result.pack.synthetic is False
    ev = result.pack.evidence[0]
    assert ev.scope == Scope.APPROACH and ev.limitations  # unspecified scope is never "program"


def test_reimport_does_not_multiply_evidence():
    a = parse_text("Study", TEXT)
    b = parse_text("Study (copy)", "\r\n" + TEXT + "  \r\n")  # same content, other title/whitespace
    result = build_pack([a, b])
    assert len(result.pack.sources) == 1 and len(result.pack.evidence) == 2
    assert any("Duplicate document skipped" in w for w in result.pack.retrieval_warnings)


def test_ids_are_stable_across_imports():
    r1 = build_pack([parse_text("Study", TEXT)])
    r2 = build_pack([parse_text("Study", TEXT)])
    assert [e.id for e in r1.pack.evidence] == [e.id for e in r2.pack.evidence]
    assert r1.pack.snapshot_id == r2.pack.snapshot_id


def test_same_title_different_content_not_merged():
    result = build_pack([parse_text("Same", TEXT), parse_text("Same", TEXT + "\n\nExtra finding.")])
    assert len(result.pack.sources) == 2


def test_same_identifier_different_content_warns_keeps_both():
    a = parse_text("A", TEXT, identifier="NCT00000000")
    b = parse_text("A v2", TEXT + "\n\nUpdate.", identifier="NCT00000000")
    result = build_pack([a, b])
    assert len(result.pack.sources) == 2
    assert result.pack.sources[0].document_id == "NCT00000000"
    assert any("NCT00000000" in w for w in result.pack.retrieval_warnings)


def test_identifier_not_valid_as_id_is_dropped_with_warning():
    result = build_pack([parse_text("A", TEXT, identifier="10.1000/abc")])  # '/' not allowed in Id
    assert result.pack.sources[0].document_id is None
    assert any("document_id" in w for w in result.pack.retrieval_warnings)


def test_empty_text_title_date_rejected():
    with pytest.raises(InvalidDocument):
        parse_text("Empty", "  \n \n")
    with pytest.raises(InvalidDocument):
        parse_text("", TEXT)
    with pytest.raises(InvalidDocument):
        parse_text("T", TEXT, published_at="yesterday")


def test_json_annotation_must_exist_in_text():
    doc = {"title": "T", "text": "Alpha beta gamma.", "evidence": [{"excerpt": "Delta epsilon."}]}
    with pytest.raises(InvalidDocument) as e:
        parse_json(doc)
    assert e.value.code == "excerpt_not_found"


def test_json_annotation_scope_and_limitations():
    doc = {
        "title": "T",
        "sections": [{"heading": "H", "text": "Alpha beta. Gamma delta."}],
        "evidence": [{"excerpt": "Gamma delta.", "scope": "program", "limitations": ["n=1"]}],
    }
    result = build_pack([parse_json(doc)])
    ev = result.pack.evidence[0]
    assert (ev.locator, ev.scope, ev.limitations) == ("section: H, paragraph 1", Scope.PROGRAM, ["n=1"])
    assert verify_pack(result) == []


def test_json_bad_locator_scope_and_syntax_rejected():
    with pytest.raises(InvalidDocument):
        parse_json({"title": "T", "text": "Alpha.", "evidence": [{"excerpt": "Alpha.", "locator": "paragraph 9"}]})
    with pytest.raises(InvalidDocument):
        parse_json({"title": "T", "text": "Alpha.", "evidence": [{"excerpt": "Alpha.", "scope": "global"}]})
    with pytest.raises(InvalidDocument):
        parse_json("{not json")


# ---- PDF

def test_pdf_page_locators():
    pdf = make_pdf([["Page one finding: marker M fell by 48 percent."], ["Page two gap: no human data exist."]])
    result = build_pack([parse_pdf(pdf, "PDF study")])
    assert verify_pack(result) == []
    by_loc = {e.locator: e.excerpt for e in result.pack.evidence}
    assert "marker M fell by 48 percent" in by_loc["page 1, paragraph 1"]
    assert "no human data exist" in by_loc["page 2, paragraph 1"]


def test_pdf_blank_page_warned_and_page_numbers_correct():
    result = build_pack([parse_pdf(make_pdf([[], ["Text only on page two."]]), "P")])
    assert result.pack.evidence[0].locator.startswith("page 2")
    assert any("Page 1" in w for w in result.pack.retrieval_warnings)


def test_scanned_pdf_is_unreadable_not_empty_success():
    with pytest.raises(UnreadableDocument) as e:
        parse_pdf(make_pdf([[], []]), "Scan")
    assert e.value.code == "unreadable_document"


def test_corrupt_or_fake_pdf_is_unreadable():
    with pytest.raises(UnreadableDocument):
        parse_pdf(b"%PDF-1.4 garbage", "Broken")
    with pytest.raises(UnreadableDocument):
        parse_pdf(b"not a pdf", "Fake")


def test_unsupported_format():
    with pytest.raises(UnsupportedDocument):
        parse_document(_upload("a.docx", b"PK\x03\x04", "application/octet-stream"))


def test_import_document_entry_point_returns_pack():
    doc = _upload("study.pdf", make_pdf([["Hello evidence."]]), "application/pdf", "Up")
    pack = asyncio.run(import_document(doc, None))
    assert isinstance(pack, EvidencePack)
    assert len(pack.sources) == 1 and len(pack.evidence) == 1


def test_import_document_unreadable_raises():
    doc = _upload("scan.pdf", make_pdf([[]]), "application/pdf", "Scan")
    with pytest.raises(UnreadableDocument):
        asyncio.run(import_document(doc, None))


def test_normalization_is_hash_stable():
    assert content_hash("a  b\r\n") == content_hash("a b")
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


# ---- synthetic documents and R2's fixture

def test_synthetic_baseline_pack():
    result = fixtures.build_baseline_pack()
    assert verify_pack(result) == []
    assert result.pack.synthetic is True
    assert 3 <= len(result.pack.sources) <= 5
    assert all(s.synthetic and s.type == "synthetic" and s.url is None for s in result.pack.sources)
    assert all(s.document_id is None for s in result.pack.sources)  # no fake DOIs


def test_safety_update_is_separate_and_negative():
    base, upd = fixtures.build_baseline_pack(), fixtures.build_safety_update_pack()
    assert not {s.id for s in base.pack.sources} & {s.id for s in upd.pack.sources}
    assert any("negative safety signal" in e.excerpt for e in upd.pack.evidence)
    assert not any("liver enzyme" in e.excerpt for e in base.pack.evidence)


def test_merge_adds_evidence_without_changing_old_ids():
    base = fixtures.build_baseline_pack()
    merged = base.merge(fixtures.build_safety_update_pack())
    assert {e.id for e in base.pack.evidence} <= {e.id for e in merged.pack.evidence}
    assert len(merged.pack.evidence) == len(base.pack.evidence) + 2


def test_r2_evidence_pack_fixture_is_consistent():
    pack = EvidencePack.model_validate_json(R2_FIXTURE.read_text(encoding="utf-8"))
    source_ids = {s.id for s in pack.sources}
    assert pack.synthetic and all(s.synthetic for s in pack.sources)
    assert all(e.source_id in source_ids for e in pack.evidence)
    assert len({e.id for e in pack.evidence}) == len(pack.evidence)
    