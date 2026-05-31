"""Demo Poradnik articles — populates the public /poradnik listing.

Creates ~12 curated articles spread across the canonical categories
(CV i listy / Rozmowy / Wynagrodzenia / Kariera / Rynek), with one
flagged is_featured so the hero card renders.

Idempotent: every seed row is tagged "(demo)" in the title; --reset
deletes only those, leaving any real articles alone.

Run inside the backend container:

    docker compose exec backend python seeds/articles_demo.py
    docker compose exec backend python seeds/articles_demo.py --reset
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from textwrap import dedent

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, ".")
from app.core.config import settings

# Need every model so cross-module relationships resolve at flush time.
import app.modules.applications.models  # noqa: F401
import app.modules.articles.models  # noqa: F401
import app.modules.audit.models  # noqa: F401
import app.modules.automation.models  # noqa: F401
import app.modules.candidates.models  # noqa: F401
import app.modules.companies.models  # noqa: F401
import app.modules.consents.models  # noqa: F401
import app.modules.email_templates.models  # noqa: F401
import app.modules.forms.models  # noqa: F401
import app.modules.interviews.models  # noqa: F401
import app.modules.jobs.analysis_models  # noqa: F401
import app.modules.jobs.models  # noqa: F401
import app.modules.notes.models  # noqa: F401
import app.modules.organizer.models  # noqa: F401
import app.modules.pipeline.models  # noqa: F401
import app.modules.reviews.models  # noqa: F401
import app.modules.tags.models  # noqa: F401
import app.modules.tasks.models  # noqa: F401
import app.modules.users.models  # noqa: F401

from app.modules.articles.models import Article


SEED_TAG = "(demo)"


# ──────────────────────────────────────────────────────────────────────
# Authors — small pool, snapshotted on each article row.
# ──────────────────────────────────────────────────────────────────────

AUTHORS = {
    "JK": {"name": "Jan Kowalski",     "role": "Senior Tech Recruiter"},
    "AN": {"name": "Anna Nowak",       "role": "Head of Talent"},
    "MK": {"name": "Marek Krawczyk",   "role": "Compensation Analyst"},
    "PW": {"name": "Piotr Wójcik",     "role": "Engineering Manager"},
    "KS": {"name": "Kasia Sobczak",    "role": "Career Coach"},
    "TM": {"name": "Tomasz Mazur",     "role": "Lead Developer"},
    "EL": {"name": "Ewa Lis",          "role": "HR Business Partner"},
    "RD": {"name": "Robert Dąbrowski", "role": "Tech Lead"},
}


def cover_for(slug: str) -> str:
    """Deterministic placeholder cover image per article. picsum.photos
    seeds the noise so each slug always renders the same picture — good
    enough for demo content, swapped for real uploads via /admin later."""
    return f"https://picsum.photos/seed/{slug}/1600/900"


# ──────────────────────────────────────────────────────────────────────
# Article seed data — kept inline, treated as fixture content.
# ──────────────────────────────────────────────────────────────────────

ARTICLES: list[dict] = [
    # 1 — FEATURED
    {
        "slug": "rozmowa-techniczna-2026",
        "title": "Jak przygotować się do rozmowy technicznej w 2026",
        "excerpt": "Kompleksowy przewodnik po nowoczesnych rozmowach rekrutacyjnych: od system design po live coding.",
        "category": "rozmowy",
        "is_featured": True,
        "author_key": "JK",
        "read_time_minutes": 8,
        "days_ago": 9,
        "content": dedent("""\
            <h2>Czego się spodziewać</h2>
            <p>Rozmowy techniczne w 2026 r. wyglądają inaczej niż 5 lat temu. Algorytmy
            ustępują pytaniom o realne projekty, system design dominuje nad LeetCode,
            a pair programming często zastępuje tablicę.</p>

            <h2>Co warto przygotować</h2>
            <ul>
              <li>Krótką opowieść o trzech projektach z ostatnich 2 lat — problem, rola, efekt.</li>
              <li>Solidny szkielet system design na poziomie senior IC.</li>
              <li>Świadomość kompromisów Twojego stacka (Postgres vs Mongo, monolit vs mikroserwisy).</li>
            </ul>

            <h2>Live coding</h2>
            <p>Wbrew memom, dobre firmy nie ukrywają tematu — często dostaniesz zadanie
            z wyprzedzeniem. Nie pisz w trakcie idealnego kodu; pisz <em>czytelny</em>,
            komentuj decyzje i nie bój się przyznać, że czegoś nie wiesz.</p>
        """),
    },
    # 2
    {
        "slug": "10-bledow-w-cv",
        "title": "10 błędów w CV, które kosztują Cię ofertę",
        "excerpt": "Najczęstsze potknięcia kandydatów IT i jak ich uniknąć przy aplikacji.",
        "category": "cv",
        "author_key": "AN",
        "read_time_minutes": 5,
        "days_ago": 12,
        "content": dedent("""\
            <p>CV nadal jest pierwszą barierą wejścia. Tych dziesięć rzeczy odsiewa
            kandydatów szybciej niż brak doświadczenia.</p>
            <ol>
              <li>Brak konkretnych wyników liczbowych (np. „skrócono czas buildu z 12 → 4 min”).</li>
              <li>Lista technologii bez kontekstu projektu.</li>
              <li>Dwukolumnowy układ łamiący się w ATS.</li>
              <li>Zdjęcie ze ślubu lub wakacji.</li>
              <li>Adres e-mail w stylu <code>krzysiek1990@…</code>.</li>
            </ol>
            <p>Reszta listy — w pełnej wersji artykułu.</p>
        """),
    },
    # 3
    {
        "slug": "ile-zarabia-senior-developer",
        "title": "Ile zarabia senior developer w Polsce?",
        "excerpt": "Pełen raport płacowy 2026: stawki B2B, UoP, według stacku i miasta.",
        "category": "wynagrodzenia",
        "author_key": "MK",
        "read_time_minutes": 12,
        "days_ago": 14,
        "content": dedent("""\
            <h2>Mediana stawek senior</h2>
            <p>Według danych zebranych z 4 200 ogłoszeń w I kw. 2026:</p>
            <ul>
              <li>Backend (Go/Java/Python) — <strong>22–32 k PLN/mc B2B</strong></li>
              <li>Frontend (React/TS) — <strong>20–28 k PLN/mc B2B</strong></li>
              <li>DevOps/SRE — <strong>24–34 k PLN/mc B2B</strong></li>
              <li>Data Engineer — <strong>23–33 k PLN/mc B2B</strong></li>
            </ul>
            <p>Stawki UoP są zwykle 15–20% niższe niż widełki B2B, ale benefity
            i stabilność potrafią zrekompensować różnicę.</p>
        """),
    },
    # 4
    {
        "slug": "system-design-dla-poczatkujacych",
        "title": "System design dla początkujących",
        "excerpt": "Jak podchodzić do pytań o architekturę w rozmowach z FAANG-ami.",
        "category": "rozmowy",
        "author_key": "PW",
        "read_time_minutes": 15,
        "days_ago": 16,
        "content": dedent("""\
            <p>Tablica, marker, ty i prowadzący. „Zaprojektuj Twittera.” — co teraz?</p>
            <h2>Framework w 5 krokach</h2>
            <ol>
              <li>Wymagania funkcjonalne i niefunkcjonalne (RPS, latencja, dostępność).</li>
              <li>Szacowanie skali (DAU, storage, throughput).</li>
              <li>API design — endpointy, modele danych.</li>
              <li>Architektura wysokopoziomowa.</li>
              <li>Deep-dive w 1–2 wąskich gardłach.</li>
            </ol>
            <p>Pamiętaj — to <em>rozmowa</em>, nie egzamin. Myśl głośno.</p>
        """),
    },
    # 5
    {
        "slug": "remote-vs-hybryda-2026",
        "title": "Remote vs hybryda – co wybrać w 2026?",
        "excerpt": "Analiza trendów, plusów, minusów i wpływu na karierę długoterminowo.",
        "category": "kariera",
        "author_key": "KS",
        "read_time_minutes": 7,
        "days_ago": 19,
        "content": dedent("""\
            <p>Po pięciu latach od „wielkiego remote'u” rynek się ustabilizował.
            Pełen remote nie umarł, ale model 2+3 wygrywa w 60% nowych ogłoszeń.</p>
            <h2>Co stracisz na pełnym remote</h2>
            <ul>
              <li>Pasywną wiedzę z rozmów przy kawie.</li>
              <li>Łatwiejszy mentoring (i bycie mentorowanym).</li>
              <li>Mocniejszą relację z zespołem — przekłada się na awanse.</li>
            </ul>
            <h2>Co zyskasz</h2>
            <ul>
              <li>2–3h dziennie odzyskane z dojazdu.</li>
              <li>Większą elastyczność życia prywatnego.</li>
            </ul>
        """),
    },
    # 6
    {
        "slug": "ai-a-rynek-pracy-2026",
        "title": "AI zabiera miejsca pracy? Dane z 2026",
        "excerpt": "Twarde dane o wpływie LLM-ów na rynek IT w Polsce i Europie.",
        "category": "rynek",
        "author_key": "JK",
        "read_time_minutes": 10,
        "days_ago": 21,
        "content": dedent("""\
            <p>Krótka odpowiedź: nie tak, jak myślisz. Junior frontend dev'ów ubyło
            o 18% r/r, ale senior'ów IC wzrosło o 9%.</p>
            <h2>Co naprawdę się zmienia</h2>
            <p>Firmy nie tną zespołów — tną <strong>liczbę juniorów</strong>, którzy
            wykonywali pracę dziś robioną przez Copilota i Cursor'a. Wymagana poprzeczka
            na entry-level skoczyła.</p>
        """),
    },
    # 7
    {
        "slug": "cover-letter-ktory-otwiera-drzwi",
        "title": "Cover letter, który otwiera drzwi",
        "excerpt": "Szablony i frazy, które naprawdę działają — z przykładami.",
        "category": "cv",
        "author_key": "AN",
        "read_time_minutes": 6,
        "days_ago": 24,
        "content": dedent("""\
            <p>List motywacyjny w 2026? Tak, ale krótki. Trzy akapity, max 250 słów.</p>
            <h2>Struktura, która działa</h2>
            <ol>
              <li><strong>Hook</strong> — jedno zdanie pokazujące, że znasz firmę.</li>
              <li><strong>Most</strong> — konkretne osiągnięcie, które matchuje rolę.</li>
              <li><strong>Call</strong> — propozycja krótkiej rozmowy, konkretny termin.</li>
            </ol>
        """),
    },
    # 8
    {
        "slug": "negocjowanie-wynagrodzenia",
        "title": "Negocjowanie wynagrodzenia bez stresu",
        "excerpt": "Strategia na rozmowy o pieniądzach: kiedy mówić liczby, kiedy słuchać.",
        "category": "wynagrodzenia",
        "author_key": "MK",
        "read_time_minutes": 9,
        "days_ago": 27,
        "content": dedent("""\
            <p>Najgorzej negocjuje się, gdy padła już oferta. Najlepiej — zanim padła.</p>
            <h2>Trzy zasady</h2>
            <ul>
              <li>Nie podawaj liczby pierwszy.</li>
              <li>Jeśli musisz — podaj widełki <em>powyżej</em> swoich oczekiwań.</li>
              <li>Nigdy nie negocjuj na pierwszej rozmowie.</li>
            </ul>
        """),
    },
    # 9
    {
        "slug": "zmiana-stacka-z-junior",
        "title": "Jak zmienić stack technologiczny po roku pracy",
        "excerpt": "Praktyczne kroki dla juniorów, którzy źle wybrali pierwszą rolę.",
        "category": "kariera",
        "author_key": "KS",
        "read_time_minutes": 8,
        "days_ago": 32,
        "content": dedent("""\
            <p>Wybrałeś .NET, a chcesz robić Go? Nie panikuj — masz lepszą pozycję,
            niż myślisz, ale musisz zagrać konkretnie.</p>
            <h2>Plan na 6 miesięcy</h2>
            <ol>
              <li>1 projekt po godzinach w docelowym stacku, deploy do prod.</li>
              <li>Wkład w open source w docelowym stacku (małe PR'y wystarczą).</li>
              <li>Networking — meetup, Discord, Twitter.</li>
            </ol>
        """),
    },
    # 10
    {
        "slug": "ranking-it-bootcampow-2026",
        "title": "Ranking bootcampów IT 2026 — co warto, czego unikać",
        "excerpt": "Niezależna analiza: które programy realnie kończą się ofertą pracy.",
        "category": "rynek",
        "author_key": "JK",
        "read_time_minutes": 11,
        "days_ago": 38,
        "content": dedent("""\
            <p>Boom bootcampowy z lat 2018–2022 minął. Dziś tylko 31% absolwentów
            dostaje rolę w IT w ciągu 6 miesięcy. Wybór szkoły ma znaczenie większe
            niż kiedykolwiek.</p>
        """),
    },
    # 11
    {
        "slug": "pierwszy-rok-w-it-checklist",
        "title": "Pierwszy rok w IT — checklist juniora",
        "excerpt": "Co zrobić w pierwszych 12 miesiącach, żeby drugi rok nie był zmarnowany.",
        "category": "kariera",
        "author_key": "PW",
        "read_time_minutes": 7,
        "days_ago": 44,
        "content": dedent("""\
            <p>Trafiłeś do firmy. Co dalej?</p>
            <h2>Miesiąc 1–3</h2>
            <ul>
              <li>Naucz się <em>jak</em> firma deployuje, monitoruje, testuje.</li>
              <li>Nie próbuj wprowadzać rewolucji — najpierw zrozum.</li>
            </ul>
            <h2>Miesiąc 4–12</h2>
            <ul>
              <li>Weź jeden „brudny” problem, którego nikt nie chce.</li>
              <li>Ucz się mentoringu juniora młodszego od siebie.</li>
            </ul>
        """),
    },
    # 12
    {
        "slug": "rozmowa-z-hr-czego-nie-mowic",
        "title": "Rozmowa z HR — czego nie mówić",
        "excerpt": "Pytania, które brzmią niewinnie, a kosztują ofertę.",
        "category": "rozmowy",
        "author_key": "AN",
        "read_time_minutes": 6,
        "days_ago": 50,
        "content": dedent("""\
            <p>HR to nie wróg, ale też nie przyjaciel. Pamiętaj — to filtr.</p>
            <h2>Trzy rzeczy, których nigdy nie mów</h2>
            <ul>
              <li>„Zależy mi przede wszystkim na pieniądzach.” — nawet jeśli to prawda.</li>
              <li>„Nie wiem, dlaczego odszedłem z poprzedniej firmy.” — przygotuj odpowiedź.</li>
              <li>„Aktualny szef to idiota.” — żadne <em>nigdy</em>.</li>
            </ul>
        """),
    },
    # 13
    {
        "slug": "portfolio-na-githubie",
        "title": "Portfolio na GitHubie — co tam wrzucić, czego unikać",
        "excerpt": "GitHub bywa drugim CV. Pokazujemy, co rekruterzy naprawdę otwierają.",
        "category": "cv",
        "author_key": "TM",
        "read_time_minutes": 7,
        "days_ago": 55,
        "content": dedent("""\
            <p>Recruiter klika w GitHub <em>średnio raz na trzy CV</em>, ale jeśli już
            kliknie — wystarczy 30 sekund, żeby wyrobił sobie opinię.</p>
            <h2>Co działa</h2>
            <ul>
              <li>3–5 repo z README po angielsku, sekcje „Why", „How to run", „Tech".</li>
              <li>Jeden projekt z aktywnym commit historyem ostatnich 6 miesięcy.</li>
              <li>Pinned repos ułożone od najmocniejszego.</li>
            </ul>
            <h2>Co odpycha</h2>
            <ul>
              <li>Forks tutoriali bez własnych commitów.</li>
              <li>50 repo „learn-X" z tygodnia w bootcampie.</li>
              <li>Puste README albo „TODO: add description".</li>
            </ul>
        """),
    },
    # 14
    {
        "slug": "feedback-po-odrzuceniu",
        "title": "Jak prosić o feedback po odrzuceniu (i go dostać)",
        "excerpt": "Większość firm milczy po „dziękujemy”. Pokazujemy, jak skłonić ich do konkretu.",
        "category": "rozmowy",
        "author_key": "EL",
        "read_time_minutes": 5,
        "days_ago": 62,
        "content": dedent("""\
            <p>„Dziękujemy, zdecydowaliśmy się na innego kandydata" — i tyle? Można
            wycisnąć więcej, jeśli zapytasz <em>konkretnie</em>.</p>
            <h2>Szablon wiadomości</h2>
            <blockquote>
              Cześć [imię], dziękuję za decyzję. Bardzo mi zależy na rozwoju —
              gdybyś mógł(a) wskazać jeden obszar, który zważył na decyzji,
              byłaby to dla mnie bardzo cenna informacja.
            </blockquote>
            <p>Działa, bo: krótkie, konkretne, daje wymówkę na odpowiedź jednym zdaniem.</p>
        """),
    },
    # 15
    {
        "slug": "b2b-czy-uop-2026",
        "title": "B2B czy UoP w 2026 — kalkulator i pułapki",
        "excerpt": "Realne porównanie netto z benefitami, urlopem i ZUS-em.",
        "category": "wynagrodzenia",
        "author_key": "MK",
        "read_time_minutes": 14,
        "days_ago": 70,
        "content": dedent("""\
            <p>W 2026 r. B2B na rynku IT to nadal dominanta, ale różnica netto przy
            podobnym <em>total compensation</em> jest mniejsza, niż się wydaje.</p>
            <h2>Realny kalkulator</h2>
            <p>Przykład: oferta 22 k UoP brutto vs. 25 k B2B na fakturze.</p>
            <ul>
              <li>UoP netto: ~15 600 zł, 26 dni urlopu, L4 płatne, ZUS gotowy.</li>
              <li>B2B netto (ryczałt 12%): ~21 100 zł, 0 dni urlopu, własny ZUS, własna księgowa.</li>
            </ul>
            <p>Różnica „w kieszeni": ~5 500 zł, ale koszty B2B (ZUS, urlop „za swoje",
            księgowa, ubezpieczenie zdrowotne, brak L4) zjadają realnie 2 500–3 500 zł.</p>
            <h2>Kiedy B2B się opłaca</h2>
            <ul>
              <li>Kiedy nie planujesz dziecka w najbliższych 24 m-cach.</li>
              <li>Kiedy masz oszczędności na 3 miesiące „bez pracy".</li>
              <li>Kiedy lubisz prowadzić swoje finanse.</li>
            </ul>
        """),
    },
    # 16
    {
        "slug": "promocja-na-seniora",
        "title": "Awans na seniora — co tak naprawdę liczy menedżer",
        "excerpt": "Lata pracy to nie wszystko. Pokazujemy, co realnie przesuwa kandydata o szczebel.",
        "category": "kariera",
        "author_key": "PW",
        "read_time_minutes": 9,
        "days_ago": 78,
        "content": dedent("""\
            <p>„Mam 5 lat doświadczenia, kiedy awans na seniora?" — pytanie złe.
            Senior to nie kalendarz, to <strong>zakres</strong>.</p>
            <h2>Cztery oznaki seniora</h2>
            <ol>
              <li>Bierze problem niejasny i wraca z propozycją rozwiązania.</li>
              <li>Robi mentoring juniorów bez bycia o to proszonym.</li>
              <li>Wpływa na decyzje techniczne <em>poza</em> swoim taskiem.</li>
              <li>Jego absencja wstrzymuje zespół.</li>
            </ol>
            <p>Brak choć jednego z tych elementów — promocja czeka.</p>
        """),
    },
    # 17
    {
        "slug": "tech-stack-trendy-2026",
        "title": "Tech stack trendy 2026 — co rośnie, co umiera",
        "excerpt": "Analiza 8 000 ogłoszeń: które technologie zyskują, które tracą na wartości.",
        "category": "rynek",
        "author_key": "RD",
        "read_time_minutes": 11,
        "days_ago": 85,
        "content": dedent("""\
            <h2>Top 5 rośnie</h2>
            <ul>
              <li><strong>Rust</strong> — +84% r/r w ogłoszeniach senior backend.</li>
              <li><strong>Go</strong> — utrzymuje wzrost, stabilne +30% r/r.</li>
              <li><strong>TypeScript</strong> — frontend bez TS to już ewenement.</li>
              <li><strong>Bun / Deno</strong> — pojawiają się w job postings, ale niszowe.</li>
              <li><strong>Tailwind</strong> — niemal monopolista CSS w nowych projektach.</li>
            </ul>
            <h2>Top 5 spada</h2>
            <ul>
              <li><strong>jQuery</strong> — tylko legacy maintenance.</li>
              <li><strong>AngularJS (v1)</strong> — wymarły, ale ogłoszeń jeszcze trochę.</li>
              <li><strong>Ruby on Rails</strong> — wolno, ale konsekwentnie maleje.</li>
              <li><strong>PHP &lt; 8.0</strong> — modernizacje gniją w długim ogonie.</li>
              <li><strong>Windows Server stack</strong> — chmury wyparły lokalne IIS-y.</li>
            </ul>
        """),
    },
    # 18
    {
        "slug": "praca-zdalna-z-zagranicy",
        "title": "Praca zdalna dla polskiej firmy z zagranicy — podatki, ZUS, mit nomady",
        "excerpt": "Wyjeżdżasz na trzy miesiące do Hiszpanii? Sprawdź, zanim spakujesz laptop.",
        "category": "kariera",
        "author_key": "MK",
        "read_time_minutes": 13,
        "days_ago": 92,
        "content": dedent("""\
            <p>183 dni — magiczna liczba, której większość „nomadów" nie zna.
            Tyle dni poza Polską w roku kalendarzowym zmienia <em>rezydencję podatkową</em>.</p>
            <h2>Trzy scenariusze</h2>
            <ol>
              <li><strong>Krótki wyjazd (do 90 dni)</strong> — bez konsekwencji, pracujesz normalnie.</li>
              <li><strong>Średni (90–183 dni)</strong> — wymaga uzgodnienia z firmą, czasem zmiany formy umowy.</li>
              <li><strong>Długi (>183 dni)</strong> — zmieniasz rezydencję, niemal zawsze potrzebujesz lokalnego wehikułu.</li>
            </ol>
            <p>Większość polskich firm w 2026 r. dopuszcza scenariusz 1 i 2 (z gwiazdką).
            Scenariusz 3 — praktycznie zawsze trzeba <em>zmienić</em> umowę albo rozstać się.</p>
        """),
    },
    # 19
    {
        "slug": "kobiety-w-it-statystyki",
        "title": "Kobiety w polskim IT — raport 2026",
        "excerpt": "Twarde liczby: udział, role, luka płacowa. Bez ideologii, tylko dane.",
        "category": "rynek",
        "author_key": "EL",
        "read_time_minutes": 10,
        "days_ago": 100,
        "content": dedent("""\
            <h2>Liczby z 2026</h2>
            <ul>
              <li>Kobiety stanowią <strong>18%</strong> stanowisk inżynierskich w PL.</li>
              <li>W rolach product/design — <strong>47%</strong>.</li>
              <li>W rolach C-level w startupach IT — <strong>11%</strong>.</li>
            </ul>
            <h2>Luka płacowa</h2>
            <p>Na podobnym senioritcie i stacku — 6–9% różnicy. Pięć lat temu było 14%.</p>
            <h2>Co się zmienia</h2>
            <p>Bootcampy raportują kobiet 38% — pipeline rośnie. Pytanie o retencję
            i awanse — to wąskie gardło.</p>
        """),
    },
    # 20
    {
        "slug": "pierwsza-praca-bez-doswiadczenia",
        "title": "Pierwsza praca w IT bez doświadczenia — co realnie działa w 2026",
        "excerpt": "Studia, bootcamp, samouk? Patrzymy, kto faktycznie znajduje robotę.",
        "category": "kariera",
        "author_key": "KS",
        "read_time_minutes": 8,
        "days_ago": 110,
        "content": dedent("""\
            <p>Krótka odpowiedź: <strong>portfolio + sieć kontaktów</strong> ważą więcej
            niż dyplom czy bootcamp.</p>
            <h2>Top 3 sposoby na pierwszą rolę</h2>
            <ol>
              <li>Praktyki / staż w firmie, którą wcześniej znałeś (meetup, OSS, klient).</li>
              <li>Programy stażowe topowych firm (CD Projekt, Allegro, Brainly).</li>
              <li>Junior role z polecenia — nadal 40% pierwszych ofert.</li>
            </ol>
            <p>Cold apply przez LinkedIn? Działa tylko jeśli masz <em>coś konkretnego</em>
            do pokazania (projekt, blog, OSS).</p>
        """),
    },
]


async def main(reset: bool = False) -> None:
    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        if reset:
            print(f"⚠ Wiping articles tagged '{SEED_TAG}'…")
            await db.execute(text(f"DELETE FROM articles WHERE title LIKE '%{SEED_TAG}%'"))
            await db.commit()

        created = 0
        backfilled = 0
        for raw in ARTICLES:
            slug = raw["slug"]
            cover = cover_for(slug)
            existing_row = (await db.execute(
                select(Article).where(Article.slug == slug)
            )).scalar_one_or_none()

            if existing_row:
                # Idempotent re-run: top up the cover if a previous seed
                # run created the article before we started shipping covers.
                if not existing_row.cover_image_url:
                    existing_row.cover_image_url = cover
                    backfilled += 1
                    print(f"  ↻ {slug} — backfilled cover")
                else:
                    print(f"  · {slug} — already present, skipping")
                continue

            author = AUTHORS[raw["author_key"]]
            published = datetime.now(UTC) - timedelta(days=raw["days_ago"])
            article = Article(
                slug=slug,
                title=f"{raw['title']} {SEED_TAG}",
                excerpt=raw.get("excerpt"),
                content=raw["content"],
                cover_image_url=cover,
                category=raw["category"],
                is_featured=raw.get("is_featured", False),
                is_published=True,
                author_name=author["name"],
                author_role=author["role"],
                author_avatar_url=None,
                read_time_minutes=raw.get("read_time_minutes"),
                published_at=published,
            )
            db.add(article)
            created += 1
            print(f"  ✓ {slug}")

        await db.commit()
        print(f"Done — {created} created, {backfilled} updated with cover.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
