"""Spójność ścieżek: każde odwołanie do pliku repozytorium w kodzie, workflowach i dokumentach ma wskazywać plik,
który istnieje.

Układ repozytorium (src/, web/, data/, docs/) rozdziela dawny katalog docs/, a odwołań do plików jest kilkaset
(kod Pythona, JS stron, workflowy, instrukcje nocnych zadań, dokumentacja). Ten test jest siatką bezpieczeństwa
przy każdym przenoszeniu lub zmianie nazwy pliku: zostawione stare odwołanie kończy się czerwonym testem, a nie
błędem znalezionym dopiero w nocy."""

import re
import subprocess
from pathlib import Path

KATALOGI = ("docs", "src", "web", "data", "projekty", "ustawienia", ".github", ".claude")
TEKST = {".py", ".js", ".mjs", ".cjs", ".md", ".yml", ".yaml", ".toml", ".json", ".html", ".css", ".sh", ".txt"}

# Zapisy historyczne opisują stan z chwili powstania (dzienniki zadań, specyfikacje), więc nie poprawiamy w nich ścieżek.
HISTORYCZNE = ("projekty/", "docs/specyfikacja/")
# W tej wersji poglądowej nie ma katalogów z treściami (posty, transkrypcje, artykuły), więc lista jest pusta.
TRESCI = ()
# Pliki generowane z kodu: sprawdzamy ich źródła (.py, .md), a zgodność z wynikiem generatora pilnuje test_regeneracja_kart.
GENEROWANE = re.compile(r"^web/(?:biblioteka|pozycja|stan-rynku|VaR)/(?:index\.html|app\.js)$|^web/shared/mapa-kodu\.json$")
# Testy zawierają celowo nieistniejące ścieżki jako dane wejściowe.
POMIJANE = ("tests/",)

# Odwołania, które celowo nie wskazują pliku w repozytorium (powód przy każdym).
WYJATKI = {
    "ustawienia/stan-rynku-przestrzen.json": "w pełnej platformie plik powstaje przy zapisie układu ze strony; w wersji pokazowej katalogu ustawienia/ nie ma",
    "ustawienia/uklad-stan-rynku.json": "dawne ustawienie, z którego pochodzi układ domyślny; w wersji pokazowej katalogu ustawienia/ nie ma",
    "ustawienia/pozycja.json": "profile karty Pozycja; w pełnej platformie plik powstaje przy zapisie ze strony, w wersji pokazowej katalogu ustawienia/ nie ma",
    "ustawienia/pozycja-przestrzen.json": "układ okien karty Pozycja; jak wyżej, powstaje dopiero przy zapisie ze strony",
    "ustawienia/uklad-pozycja.json": "dawne ustawienie, z którego pochodzi układ domyślny Pozycji; w wersji pokazowej katalogu ustawienia/ nie ma",
    "ustawienia/historia-zakladow.csv": "historia zakładów karty Pozycja; w pełnej platformie zapisuje ją strona przez token GitHub, tu jej nie ma",
    "data/platforma.sqlite": "baza pochodna budowana poleceniem `make db`, poza repozytorium (.gitignore)",
}

WZORZEC = re.compile(r"(?<![\w/.\-])((?:%s)/[\w.@/\-]*[\w/\-])" % "|".join(re.escape(k) for k in KATALOGI))
SYMBOL_ZASTEPCZY = re.compile(r"[*<>{}$%]|NNN|RRRR|MM-DD|\.\.\.")


def _tracked(korzen: Path) -> list[str]:
    wyjscie = subprocess.check_output(["git", "ls-files", "-z"], cwd=korzen, text=True)
    return [p for p in wyjscie.split("\0") if p]


def _brakujace_odwolania(korzen: Path) -> list[str]:
    zle = []
    for plik in _tracked(korzen):
        if plik.startswith(HISTORYCZNE + TRESCI + POMIJANE) or GENEROWANE.match(plik) or Path(plik).suffix.lower() not in TEKST:
            continue
        if plik.startswith("data/") and plik != "data/README.md":
            continue          # dane zapisują potoki i zadania, a ich teksty nie są odwołaniami z kodu (słownik data/README.md sprawdzamy)
        sciezka = korzen / plik
        if not sciezka.is_file():
            continue
        for nr, linia in enumerate(sciezka.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in WZORZEC.finditer(linia):
                token = m.group(1).rstrip(".,:;)")
                nastepny = linia[m.end(): m.end() + 1]
                if token.endswith("-") or nastepny in ("*", "<", "{") or SYMBOL_ZASTEPCZY.search(token):
                    continue          # początek nazwy z wzorcem (np. projekty/014-*) albo symbol zastępczy
                if token.rstrip("/") in WYJATKI or (korzen / token).exists():
                    continue
                zle.append(f"{plik}:{nr}: {token}")
    return zle


def test_kazde_odwolanie_do_pliku_wskazuje_istniejacy_plik(korzen):
    zle = _brakujace_odwolania(korzen)
    assert zle == [], "odwołania do nieistniejących plików:\n  " + "\n  ".join(zle[:40])


def test_stare_miejsca_po_przeniesieniu_nie_istnieja(korzen):
    """Po rozdzieleniu docs/ w katalogu zostaje wyłącznie dokumentacja: pliki .md i zrzuty ekranu do README."""
    dozwolone = lambda p: p.endswith(".md") or p.startswith("docs/obrazy/")   # noqa: E731
    obce = [p for p in _tracked(korzen) if p.startswith("docs/") and not dozwolone(p)]
    assert obce == [], "w docs/ mają zostać tylko pliki dokumentacji; kod, stronę i dane trzymają src/, web/ i data/"


def test_kod_pythona_lezy_tylko_w_src_i_narzedziach(korzen):
    """Pliki .py poza src/ i tests/ to wyjątki. Jedyny dozwolony: załączniki zadań w projekty/<NNN>-<slug>/pliki/ (zapis procesu pracy)."""
    zalacznik = lambda p: p.startswith("projekty/") and "/pliki/" in p   # noqa: E731
    spoza = [p for p in _tracked(korzen) if p.endswith(".py") and not p.startswith(("src/", "tests/")) and not zalacznik(p)]
    assert spoza == []
