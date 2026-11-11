"""Karta „Biblioteka" — przegląd bibliotek użytych w projekcie albo uzgodnionych do użycia.

Wzorzec pliku — patrz CLAUDE.md, „Karty: wzorzec jednoplikowy":
cała logika Pythona, fragmenty HTML i kod JS mieszkają w tym jednym pliku,
a `generuj()` wypisuje z niego `index.html` i `app.js` — tych dwóch plików
nigdy nie edytuje się ręcznie.

Źródłem treści są pliki `.md` w podkatalogach `docs/biblioteka/` (jeden plik =
jedna biblioteka): `python/`, `javascript/`, `html-css/` oraz `uslugi/` (usługi
zewnętrzne używane w pracy, np. serwisy z obrazami; pole `Język:` pokazuje się jako plakietka). To właśnie je
edytuje się, żeby dopisać bibliotekę albo zmienić jej opis — strona składa
się z nich sama po `python biblioteka.py`. Format pliku:

    # nazwa biblioteki
    Język: Python | JavaScript | HTML i CSS
    Kategoria: ...
    Status: w użyciu | historyczna (nieużywana) | uzgodniona do użycia
    Pakiet: ...
    Strona: https://...
    Gdzie w projekcie: ...
    W requirements.txt: ...

    Kilka zdań opisu: czym jest, gdzie jej używamy, jak można ją wykorzystać.

Nagłówek (linie `Klucz: wartość`) kończy się pierwszą pustą linią, reszta to
opis dzielony na akapity pustymi liniami; `kod` w odwrotnych apostrofach
trafia do <code>.

Użycie: `python src/biblioteka/biblioteka.py` (z korzenia repozytorium) regeneruje web/biblioteka/index.html i app.js.
"""

import html
from pathlib import Path
import re

KORZEN = Path(__file__).resolve().parents[2]
KATALOG = KORZEN / "docs" / "biblioteka"        # źródła treści: pliki .md w podkatalogach
SCIEZKA_HTML = KORZEN / "web" / "biblioteka" / "index.html"
SCIEZKA_JS = KORZEN / "web" / "biblioteka" / "app.js"

# Pola nagłówka pliku .md pokazywane w ramce „szczegóły" pod opisem, w tej kolejności.
POLA_SZCZEGOLOW = ["Pakiet", "Strona", "Gdzie w projekcie", "W requirements.txt"]


#===============================================================================
# magazyn funkcji
#===============================================================================

def wczytaj_biblioteke(sciezka: Path) -> dict:
    """Czyta jeden plik .md i zwraca słownik: nazwa, pola nagłówka, akapity opisu."""
    linie = sciezka.read_text(encoding="utf-8").splitlines()
    if not linie or not linie[0].startswith("# "):
        raise ValueError(f"{sciezka}: pierwsza linia musi być tytułem '# nazwa'")
    wpis = {"nazwa": linie[0][2:].strip(), "pola": {}, "akapity": [], "plik": sciezka.name}
    i = 1
    while i < len(linie) and linie[i].strip():
        klucz, sep, wartosc = linie[i].partition(":")
        if not sep:
            raise ValueError(f"{sciezka}: linia nagłówka bez dwukropka: {linie[i]!r}")
        wpis["pola"][klucz.strip()] = wartosc.strip()
        i += 1
    # opis: po pierwszej pustej linii; każda niepusta linia to osobny akapit,
    # bo pliki pisze się jednym zdaniem-akapitem na linię (czytelniej w diffie)
    wpis["akapity"] = [l.strip() for l in linie[i:] if l.strip()]
    for wymagane in ("Język", "Status"):
        if wymagane not in wpis["pola"]:
            raise ValueError(f"{sciezka}: brak pola '{wymagane}'")
    return wpis


def wczytaj_wszystkie(katalog: Path = KATALOG) -> list:
    """Wszystkie biblioteki z podkatalogów w jednej liście, alfabetycznie po nazwie
    (język pokazuje plakietka przy nazwie, nie podział na sekcje)."""
    wpisy = [wczytaj_biblioteke(p) for p in sorted(katalog.glob("*/*.md"))]
    return sorted(wpisy, key=lambda w: w["nazwa"].lower())


def tekst_html(tekst: str) -> str:
    """Escapuje tekst i zamienia `kod` w odwrotnych apostrofach na <code>."""
    bezpieczny = html.escape(tekst, quote=False)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", bezpieczny)


def pole_html(klucz: str, wartosc: str) -> str:
    """Jedna linia ramki szczegółów; pole „Strona" z adresem http(s) staje się linkiem."""
    if klucz == "Strona" and re.match(r"https?://", wartosc):
        adres = html.escape(wartosc, quote=True)
        wartosc_html = f'<a href="{adres}" target="_blank" rel="noopener noreferrer">{html.escape(wartosc)}</a>'
    else:
        wartosc_html = tekst_html(wartosc)
    return f"<dt>{html.escape(klucz)}</dt><dd>{wartosc_html}</dd>"


def klasa_statusu(status: str) -> str:
    """Kolor plakietki statusu: w użyciu / historyczna / reszta (np. uzgodniona do użycia)."""
    s = status.lower()
    if s.startswith("w użyciu"):
        return "bib-status-uzycie"
    if s.startswith("historyczna"):
        return "bib-status-historia"
    return "bib-status-plan"


#===============================================================================
# elementy
#===============================================================================

# --- element 1: wyszukiwarka (okno 1) -----------------------------------------
# Dawny blok z tytułem strony i opisem został usunięty (zadanie 016, interfejs w
# stylu terminala). Nazwa stałej zostaje, żeby nie ruszać reszty generatora.

HTML_FRAGMENT_NAGLOWEK = """
<section class="karta t-okno t-k12">
  <header class="t-naglowek"><h2>Szukaj</h2></header>
  <div class="t-tresc bib-szukaj">
    <label for="bib-filtr">Szukaj biblioteki</label>
    <input id="bib-filtr" type="search" placeholder="np. pandas, testy, SQL…" autocomplete="off" />
    <span id="bib-licznik" class="bib-licznik" aria-live="polite"></span>
  </div>
</section>
"""

APP_JS_SZUKAJ = """
// Filtr bibliotek: ukrywa wpisy, w których nie ma wpisanej frazy (nazwa,
// język, kategoria, opis, status); sekcje bez żadnego widocznego wpisu też znikają.
function bibZastosujFiltr() {
  const fraza = document.getElementById("bib-filtr").value.trim().toLowerCase();
  let widoczne = 0;
  document.querySelectorAll(".bib-wpis").forEach((wpis) => {
    const pasuje = !fraza || wpis.dataset.szukaj.includes(fraza);
    wpis.hidden = !pasuje;
    if (pasuje) widoczne++;
  });
  document.querySelectorAll(".bib-sekcja").forEach((sekcja) => {
    sekcja.hidden = !sekcja.querySelector(".bib-wpis:not([hidden])");
  });
  const licznik = document.getElementById("bib-licznik");
  licznik.textContent = fraza ? "Znaleziono: " + widoczne : "";
}
document.getElementById("bib-filtr").addEventListener("input", bibZastosujFiltr);
"""


def element_naglowek(wpisy: list) -> str:
    return HTML_FRAGMENT_NAGLOWEK


# --- element 2: katalog bibliotek (sekcje językowe) -----------------------------
# Czysty HTML generowany z plików .md — bez własnego JS (filtr z elementu 1
# działa na klasach .bib-wpis / .bib-sekcja).

def wpis_html(w: dict) -> str:
    """Jedna biblioteka jako zwijana pozycja <details>: w zwiniętej widać tylko
    nazwę i plakietkę języka, reszta (status, opis, szczegóły) po rozwinięciu."""
    pola = w["pola"]
    szukaj = " ".join(
        [w["nazwa"], pola["Język"], pola.get("Kategoria", ""), pola["Status"]] + w["akapity"]
    ).lower()
    plakietki = f'<span class="bib-status {klasa_statusu(pola["Status"])}">{html.escape(pola["Status"])}</span>'
    if pola.get("Kategoria"):
        plakietki += f'<span class="bib-kategoria">{html.escape(pola["Kategoria"])}</span>'
    opis = "\n".join(f"        <p>{tekst_html(a)}</p>" for a in w["akapity"])
    szczegoly = "".join(pole_html(k, pola[k]) for k in POLA_SZCZEGOLOW if pola.get(k))
    return (
        f'    <details class="bib-wpis" data-szukaj="{html.escape(szukaj, quote=True)}">\n'
        f'      <summary><span class="bib-nazwa">{html.escape(w["nazwa"])}</span>'
        f'<span class="bib-jezyk">{html.escape(pola["Język"])}</span></summary>\n'
        f'      <div class="bib-tresc">\n'
        f'        <div class="bib-plakietki">{plakietki}</div>\n'
        f'{opis}\n'
        f'        <dl class="bib-szczegoly">{szczegoly}</dl>\n'
        f'      </div>\n'
        f'    </details>'
    )


def element_katalog(wpisy: list) -> str:
    """Jedna karta z płaską listą wszystkich bibliotek (domyślnie zwiniętych)."""
    return (
        '<section class="karta t-okno t-k12 bib-sekcja">\n'
        f'  <header class="t-naglowek"><h2>Biblioteki <span class="bib-licznik-sekcji">({len(wpisy)})</span></h2></header>\n'
        '  <div class="t-tresc">\n'
        + "\n".join(wpis_html(w) for w in wpisy)
        + "\n  </div>\n</section>"
    )


#===============================================================================
# generowanie plików
#===============================================================================

SZABLON_STRONY = """<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Biblioteka</title>
<link rel="stylesheet" href="../style.css" />
</head>
<body class="t-strona">
<script>window.SIDEBAR_ROOT = "../";</script>
<script src="../shared/sidebar.js"></script>
<script src="../shared/oznaczenia.js"></script>
<script src="../shared/okna.js"></script>
<main>
__ZAWARTOSC__
</main>
<script src="app.js"></script>
</body>
</html>
"""

NAGLOWEK_JS = (
    '"use strict";\n\n'
    "// PLIK GENEROWANY przez src/biblioteka/biblioteka.py — nie edytuj ręcznie.\n\n"
)


def _wciecie(tekst: str, n: int = 2) -> str:
    pref = " " * n
    return "\n".join(pref + l if l.strip() else l for l in tekst.splitlines())


def generuj() -> None:
    """Składa elementy (nagłówek+filtr, katalog) w index.html i zapisuje app.js."""
    wpisy = wczytaj_wszystkie()
    # Siatka okien (wspólny styl terminala): kontener otwarty i zamknięty tutaj —
    # wyjątek od zasady „nowy element = osobny fragment" (zadanie 016).
    zawartosc = (
        '<div class="t-siatka t-dol-wysoki">\n'
        + _wciecie("\n\n".join([element_naglowek(wpisy).strip("\n"), element_katalog(wpisy).strip("\n")]))
        + "\n</div>"
    )
    SCIEZKA_HTML.write_text(
        SZABLON_STRONY.replace("__ZAWARTOSC__", _wciecie(zawartosc)), encoding="utf-8"
    )
    SCIEZKA_JS.write_text(NAGLOWEK_JS + APP_JS_SZUKAJ.strip("\n") + "\n", encoding="utf-8")
    print(f"wygenerowano {SCIEZKA_HTML} i {SCIEZKA_JS} ({len(wpisy)} bibliotek)")


if __name__ == "__main__":
    generuj()
