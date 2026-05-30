from __future__ import annotations

import zipfile

from app.services.cv_parsing import CVProfileParser, CVTextExtractor

# Public API moved to classes (CVTextExtractor / CVProfileParser); these thin
# wrappers keep the tests focused on behaviour rather than construction.
_extract = CVTextExtractor().extract
_parse = CVProfileParser().parse


def _write_docx(path, paragraphs: list[str]) -> None:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
        + "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)


def test_extract_text_from_docx(tmp_path):
    target = tmp_path / "cv.docx"
    _write_docx(target, ["Jan Kowalski", "Senior Python Developer"])
    text = _extract(str(target))
    assert "Jan Kowalski" in text
    assert "Senior Python Developer" in text


def test_parse_candidate_profile_basic():
    raw = "Jan Kowalski\nPython, Django\nDoświadczenie: 5 lat"
    profile = _parse(raw)
    assert "Jan" in (profile.get("first_name") or "")
    assert isinstance(profile.get("skills"), list)


def test_parse_candidate_profile_skills_dedup():
    raw = "Python, Python, Django"
    profile = _parse(raw)
    skills = [s["name"] if isinstance(s, dict) else s for s in profile.get("skills", [])]
    assert len(skills) == len(set(skills))


def test_extract_unsupported_type_raises(tmp_path):
    # Only PDF/DOCX are supported; anything else must raise a clear error.
    target = tmp_path / "cv.txt"
    target.write_text("irrelevant", encoding="utf-8")
    try:
        _extract(str(target))
        raised = False
    except ValueError:
        raised = True
    assert raised
