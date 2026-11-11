"""Straż wersji poglądowej: to repozytorium jest publiczne, więc test pilnuje, żeby nie wróciły do niego dane osobiste,
klucze, treści osób trzecich ani pliki, których tu nie planowano.

Wzorce są ogólne albo złożone z kawałków (np. "stock" "analysis"), żeby sam test niczego nie ujawniał i żeby nie
wyszukiwał sam siebie. Dopisując nowy katalog lub plik do repozytorium, trzeba świadomie rozszerzyć odpowiednią listę."""

import re
import subprocess
from pathlib import Path

TEKST = {".py", ".js", ".mjs", ".cjs", ".md", ".yml", ".yaml", ".toml", ".json", ".html", ".css", ".sh", ".txt", ".csv", ".sql"}

# Co może leżeć w korzeniu repozytorium i w katalogach, które mają ograniczoną zawartość.
KORZEN_DOZWOLONY = {".claude", ".editorconfig", ".gitattributes", ".github", ".gitignore", ".python-version", "LICENSE", "Makefile",
                    "README.md", "data", "docs", "projekty", "pyproject.toml", "requirements-dev.txt", "requirements-tools.txt",
                    "requirements.txt", "sql", "src", "tests", "web"}
DANE_DOZWOLONE = {"README.md", "stan-rynku", "historia", "przyklad"}
PROJEKTY_DOZWOLONE = {"037-nowa-karta-stan-rynku"}

NIEDOZWOLONE_ROZSZERZENIA = {".webm", ".mp3", ".m4a", ".mp4", ".wav", ".mov", ".pdf", ".sqlite", ".db", ".ipynb", ".zip", ".xlsx", ".docx"}
LIMIT_ROZMIARU = 1_500_000      # bajty; największe pliki to próbka łańcucha opcji (ok. 0,7 MB) i biblioteka wykresów (ok. 0,2 MB)

# Adresy e-mail dozwolone w treści: ślady asystenta i adresy zastępcze GitHuba (bez adresów prywatnych).
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_DOZWOLONY = re.compile(r"^noreply@anthropic\.com$|@users\.noreply\.github\.com$")

# Wzorce kluczy dostępowych (bez zgadywania konkretnych wartości).
KLUCZE = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"), re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"), re.compile(r"AIza[0-9A-Za-z_-]{30,}"), re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[ _-]?key|klucz|token|secret|has[lł]o|password)\W{0,12}[a-f0-9]{32,}"),
]

# Nazwy, których w tym repozytorium nie ma być (dostawcy treści i danych oraz adresy prywatnej infrastruktury).
ZAKAZANE = {
    "prywatny dostawca danych": "stock" "analysis",
    "prywatny dostawca plików": "quar" "tr",
    "dostawca transkrypcji": "supa" "data",
    "serwis z transkrypcjami": "bloom" "berg",
    "nieoficjalny klient wykresów": "tvdata" "feed",
    "adres Workera Cloudflare": "workers" ".dev",
    "nazwa prywatnego repozytorium": "c_" "economic",
}


def _sledzone(korzen: Path) -> list[str]:
    wyjscie = subprocess.check_output(["git", "ls-files", "-z"], cwd=korzen, text=True)
    return [p for p in wyjscie.split("\0") if p]


def _teksty(korzen: Path):
    for plik in _sledzone(korzen):
        sciezka = korzen / plik
        if plik != "tests/test_wersja_pogladowa.py" and sciezka.suffix.lower() in TEKST and sciezka.is_file():
            yield plik, sciezka.read_text(encoding="utf-8", errors="replace")


def test_w_korzeniu_i_w_katalogach_o_ograniczonej_zawartosci_sa_tylko_dozwolone_wpisy(korzen):
    pliki = _sledzone(korzen)
    korzenie = {p.split("/")[0] for p in pliki}
    assert korzenie <= KORZEN_DOZWOLONY, f"nowe wpisy w korzeniu: {sorted(korzenie - KORZEN_DOZWOLONY)}"
    dane = {p.split("/")[1] for p in pliki if p.startswith("data/")}
    assert dane <= DANE_DOZWOLONE, f"nowe wpisy w data/: {sorted(dane - DANE_DOZWOLONE)}"
    projekty = {p.split("/")[1] for p in pliki if p.startswith("projekty/")}
    assert projekty <= PROJEKTY_DOZWOLONE, f"nowe zadania w projekty/: {sorted(projekty - PROJEKTY_DOZWOLONE)}"


def test_nie_ma_nagran_baz_notatnikow_ani_duzych_plikow(korzen):
    zle = []
    for plik in _sledzone(korzen):
        sciezka = korzen / plik
        if sciezka.suffix.lower() in NIEDOZWOLONE_ROZSZERZENIA:
            zle.append(f"{plik}: niedozwolony typ pliku")
        elif sciezka.is_file() and sciezka.stat().st_size > LIMIT_ROZMIARU:
            zle.append(f"{plik}: {sciezka.stat().st_size // 1024} KB, ponad limit")
    assert zle == []


def test_w_tresci_nie_ma_prywatnych_adresow_e_mail(korzen):
    zle = []
    for plik, tekst in _teksty(korzen):
        zle += [f"{plik}: {m.group(0)}" for m in EMAIL.finditer(tekst) if not EMAIL_DOZWOLONY.search(m.group(0))]
    assert zle == [], "prywatne adresy e-mail w repozytorium:\n  " + "\n  ".join(zle[:10])


def test_w_tresci_nie_ma_kluczy_dostepowych(korzen):
    zle = []
    for plik, tekst in _teksty(korzen):
        for wzorzec in KLUCZE:
            zle += [f"{plik}: dopasowanie wzorca {wzorzec.pattern[:28]}…" for _ in wzorzec.finditer(tekst)]
        if not plik.startswith("data/") and plik != "web/shared/mapa-kodu.json":
            zle += [f"{plik}: ciąg 32 znaków szesnastkowych (możliwy klucz)" for _ in re.finditer(r"\b[a-f0-9]{32}\b", tekst)]
    assert zle == [], "możliwe klucze w repozytorium:\n  " + "\n  ".join(zle[:10])


def test_w_tresci_nie_ma_zakazanych_nazw(korzen):
    zle = []
    for plik, tekst in _teksty(korzen):
        male = tekst.lower()
        zle += [f"{plik}: {opis}" for opis, nazwa in ZAKAZANE.items() if nazwa in male]
    assert zle == [], "zakazane nazwy w repozytorium:\n  " + "\n  ".join(zle[:10])


# Liczba jednostek i cena kupna w profilach demonstracyjnych karty Pozycja: okrągłe liczby, jawnie fikcyjne.
PRZYKLADOWE_WARTOSCI_POZYCJI = {"ilosc": {0, 100}, "cenaKupna": {0, 700, 770}}


def test_wartosci_pozycji_w_kodzie_sa_zerowe_albo_przykladowe_i_nie_ma_pliku_ustawien(korzen):
    """Liczba jednostek i cena kupna to dane finansowe użytkownika. W kodzie wolno mieć tylko zera i okrągłe, fikcyjne
    wartości profili demonstracyjnych z listy wyżej; każda inna liczba przy tych polach zatrzymuje test, żeby nie wróciła
    prawdziwa pozycja. Pliku ustawień z profilami w repozytorium też nie ma."""
    zle = [p for p in _sledzone(korzen) if p.startswith("ustawienia/")]
    for plik, tekst in _teksty(korzen):
        zle += [f"{plik}: {m.group(0)}" for m in re.finditer(r'id="f-(?:ilosc-akcji|cena-kupna)"[^>]*value="[1-9]', tekst)]
        for m in re.finditer(r"""["']?(ilosc|cenaKupna)["']?\s*:\s*(\d+(?:\.\d+)?)\b""", tekst):
            if float(m.group(2)) not in PRZYKLADOWE_WARTOSCI_POZYCJI[m.group(1)]:
                zle.append(f"{plik}: {m.group(0)}")
    assert zle == []
