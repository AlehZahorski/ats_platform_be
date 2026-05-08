from __future__ import annotations

import zipfile
from pathlib import Path

from app.services.cv_parsing import extract_text_from_cv, parse_candidate_profile


def _write_docx(path, paragraphs: list[str]) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        {paragraphs}
      </w:body>
    </w:document>
    """.format(
        paragraphs="".join(
            f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
        )
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    </Types>
    """

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)


def test_extract_text_and_parse_profile_from_docx() -> None:
    file_path = Path.cwd() / "test_cv_parsing_resume.docx"
    if file_path.exists():
        file_path.unlink()
    try:
        _write_docx(
            file_path,
            [
                "Jane Doe",
                "Senior Python Developer",
                "jane@example.com",
                "+48 500 600 700",
                "Skills",
                "Python, FastAPI, PostgreSQL, Docker",
                "Experience",
                "Senior Backend Engineer",
                "Acme Corp",
                "2021 - Present",
                "Building APIs and platform services",
                "Education",
                "University of Warsaw",
                "Computer Science",
                "2016 - 2020",
            ],
        )

        text = extract_text_from_cv(str(file_path))
        parsed = parse_candidate_profile(text)

        assert "Jane Doe" in text
        assert parsed["first_name"] == "Jane"
        assert parsed["last_name"] == "Doe"
        assert parsed["email"] == "jane@example.com"
        assert "500" in (parsed["phone"] or "")
        assert parsed["headline"] == "Senior Python Developer"
        assert any(skill["name"] == "Python" for skill in parsed["skills"])
        assert parsed["experience"][0]["title"] == "Senior Backend Engineer"
        assert parsed["education"][0]["school"] == "University of Warsaw"
    finally:
        if file_path.exists():
            file_path.unlink()


def test_parse_europass_like_profile() -> None:
    text = "\n".join(
        [
            "Europass",
            "CURRICULUM VITAE",
            "Name",
            "Aleh Zahorski",
            "Email address",
            "aleh@example.com",
            "Phone number",
            "+48 792 495 950",
            "WORK EXPERIENCE",
            "DevOps Engineer",
            "TalentMatch",
            "2023 - Present",
            "Managing CI/CD pipelines and cloud infrastructure",
            "EDUCATION AND TRAINING",
            "Warsaw University of Technology",
            "Computer Science",
            "2018 - 2022",
            "DIGITAL SKILLS",
            "Python, Docker, Kubernetes, AWS, Terraform",
        ]
    )

    parsed = parse_candidate_profile(text)

    assert parsed["first_name"] == "Aleh"
    assert parsed["last_name"] == "Zahorski"
    assert parsed["email"] == "aleh@example.com"
    assert "792" in (parsed["phone"] or "")
    assert any(skill["name"] in {"Python", "Docker", "Kubernetes", "AWS", "Terraform"} for skill in parsed["skills"])
    assert parsed["experience"][0]["title"] == "DevOps Engineer"
    assert parsed["education"][0]["school"] == "Warsaw University of Technology"


def test_parse_polish_europass_sections() -> None:
    text = "\n".join(
        [
            "Europass",
            "Aleh Zahorski",
            "zahorski001@gmail.com",
            "+48 739 979 439",
            "DOŚWIADCZENIE ZAWODOWE",
            "01/05/2023 - OBECNIE - WARSZAWA, POLSKA",
            "SOFTWARE ENGINEER ALBEDOMARKETING",
            "Projektowanie i rozwój skalowalnych systemów webowych dla klientów enterprise.",
            "Loyalty Systems",
            "Budowa architektury aplikacji i modeli relacyjnych.",
            "EDUKACJA I ODBYTE SZKOLENIA",
            "2014 - 2018",
            "Politechnika Białostocka",
            "Inżynieria Oprogramowania",
            "Studia inżynierskie.",
            "UMIEJĘTNOŚCI",
            "PHP, Laravel, React, Docker, MySQL",
        ]
    )

    parsed = parse_candidate_profile(text)

    assert parsed["first_name"] == "Aleh"
    assert parsed["last_name"] == "Zahorski"
    assert parsed["experience"]
    assert parsed["experience"][0]["date_range"] == "01/05/2023 - OBECNIE - WARSZAWA, POLSKA"
    assert "Software Engineer" in (parsed["experience"][0]["title"] or "")
    assert parsed["education"]
    assert parsed["education"][0]["school"] == "Politechnika Białostocka"
    assert parsed["education"][0]["degree"] == "Inżynieria Oprogramowania"
    assert any(skill["name"] == "Laravel" for skill in parsed["skills"])
