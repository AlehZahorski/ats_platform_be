"""CV parsing keyword data — section aliases, skill lists, role/education vocabulary."""

SECTION_ALIASES: dict[str, set[str]] = {
    "skills": {
        "skills", "skill set", "skillset", "technical skills", "hard skills",
        "soft skills", "core skills", "key skills", "professional skills",
        "digital skills", "language skills", "job related skills", "job-related skills",
        "relevant skills", "skills and competencies", "competencies", "core competencies",
        "key competencies", "areas of expertise", "expertise", "technical expertise",
        "professional competencies", "capabilities", "strengths", "proficiencies",
        "tools", "tools and technologies", "technologies", "technology stack",
        "tech stack", "stack", "frameworks", "libraries", "platforms", "software",
        "systems", "programming languages", "languages", "known languages",
        "spoken languages", "language proficiency", "it skills", "computer skills",
        "engineering skills", "development skills", "product skills",
        "umiejetnosci", "umiejętności", "umiejetnosci techniczne",
        "umiejętności techniczne", "umiejetnosci miękkie", "umiejętności miękkie",
        "kompetencje", "kompetencje zawodowe", "kompetencje techniczne",
        "kompetencje cyfrowe", "kluczowe kompetencje", "kluczowe umiejętności",
        "umiejętności kluczowe", "obszary kompetencji", "obszary specjalizacji",
        "specjalizacje", "ekspertyza", "technologie", "stack technologiczny",
        "stos technologiczny", "narzedzia", "narzędzia", "narzędzia i technologie",
        "frameworki", "biblioteki", "platformy", "oprogramowanie", "systemy",
        "jezyki programowania", "języki programowania", "jezyki", "języki",
        "znajomosc jezykow", "znajomość języków", "znajomosc technologii",
        "znajomość technologii", "umiejętności komputerowe", "umiejętności informatyczne",
    },
    "experience": {
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "career history", "professional background",
        "career", "job experience", "relevant experience", "industry experience",
        "practical experience", "experience summary", "work background", "positions held",
        "roles", "career progression", "employment record", "job history",
        "project experience", "project work", "projects", "selected projects",
        "professional journey",
        "doswiadczenie", "doświadczenie", "doswiadczenie zawodowe",
        "doświadczenie zawodowe", "przebieg zatrudnienia", "historia zatrudnienia",
        "kariera zawodowa", "kariera", "praktyka zawodowa", "praktyka",
        "doświadczenie praktyczne", "stanowiska", "zajmowane stanowiska",
        "rola", "role", "projekty", "projekty zawodowe", "wybrane projekty",
        "doświadczenie projektowe", "ścieżka kariery", "przebieg kariery",
        "dotychczasowe doświadczenie", "historia pracy",
    },
    "education": {
        "education", "education and training", "education & training",
        "academic background", "academic history", "academic qualifications",
        "qualifications", "formal education", "higher education", "degree", "degrees",
        "university education", "studies", "field of study", "certifications",
        "certificates", "licenses", "courses", "training", "professional training",
        "continuing education", "additional education", "learning",
        "learning and development",
        "wyksztalcenie", "wykształcenie", "edukacja", "edukacja i szkolenia",
        "wykształcenie i szkolenia", "wykształcenie i odbyte szkolenia",
        "wyksztalcenie i odbyte szkolenia", "WYKSZTAŁCENIE I ODBYTE SZKOLENIA",
        "wykształcenie formalne", "wyksztalcenie formalne", "wykształcenie wyższe",
        "studia", "kierunek studiów", "kierunek", "kwalifikacje",
        "kwalifikacje zawodowe", "certyfikaty", "certyfikaty zawodowe",
        "licencje", "uprawnienia", "szkolenia", "kursy", "kursy i szkolenia",
        "odbyte szkolenia", "dokształcanie", "rozwój", "rozwój zawodowy",
    },
}

PERSONAL_INFO_ALIASES: frozenset[str] = frozenset({
    "curriculum vitae", "europass", "personal information", "informacje osobiste",
    "additional information", "dodatkowe informacje", "contact", "kontakt",
    "summary", "podsumowanie", "profile", "profil",
})

SKILL_KEYWORDS: frozenset[str] = frozenset({
    "python", "java", "javascript", "typescript", "react", "next.js", "nextjs",
    "node.js", "nodejs", "fastapi", "django", "flask", "sql", "postgresql", "mysql",
    "mongodb", "redis", "docker", "kubernetes", "aws", "azure", "gcp", "terraform",
    "git", "linux", "html", "css", "tailwind", "graphql", "rest", "c#", ".net",
    "php", "laravel", "vue", "angular", "figma", "salesforce",
})

ROLE_WORDS: frozenset[str] = frozenset({
    "engineer", "developer", "architect", "manager", "specialist", "consultant",
    "analyst", "lead", "administrator", "designer", "tester", "programmer",
    "inżynier", "inzynier", "programista", "konsultant", "specjalista",
    "analityk", "kierownik", "lider",
})

EDUCATION_WORDS: frozenset[str] = frozenset({
    "university", "academy", "college", "school", "politechnika", "uniwersytet",
    "akademia", "szkoła", "szkola", "liceum", "technikum",
})

DEGREE_WORDS: frozenset[str] = frozenset({
    "computer science", "engineering", "bachelor", "master", "mgr",
    "licencjat", "magister", "inżynier", "inzynier",
})

PRESENT_WORDS: tuple[str, ...] = ("present", "current", "now", "obecnie", "aktualnie")
