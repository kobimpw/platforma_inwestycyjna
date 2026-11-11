"""Składa statyczną stronę do publikacji na GitHub Pages w katalogu `_site/`.

    python src/narzedzia/zbuduj_strone.py [katalog]     (albo `make strona`; domyślnie `_site/` w korzeniu repozytorium)

GitHub Pages publikuje projekt pod adresem z nazwą repozytorium (`.../platforma_inwestycyjna/`), a wszystkie
odwołania w `web/` są względne, więc ten sam układ działa pod dowolną podścieżką. Układ wyjścia jest taki sam jak w
lokalnym podglądzie (`make serve`):

  _site/                    zawartość `web/`: strona startowa, karty, wspólne moduły, style
  _site/data/stan-rynku/    tylko dwa pliki, które czyta przeglądarka: stan.json i ocena.json
  _site/.nojekyll           wyłącza przetwarzanie Jekyllem (GitHub publikuje pliki bez zmian)

Zasada: do strony trafia wyłącznie to, co jest na liście dozwolonych plików poniżej, a nie „wszystko poza wyjątkami",
żeby nowy plik w `data/` albo `web/` nie trafił do publicznej strony przez przypadek.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[2]
WEB = KORZEN / "web"
DANE = KORZEN / "data"
DOMYSLNE_WYJSCIE = KORZEN / "_site"

# Pliki danych czytane przez przeglądarkę (ścieżki względem data/). Archiwa pomocnicze (put/call, opcje SPX, historia)
# służą warstwie SQL i skryptowi aktualizującemu, a strony ich nie potrzebują, więc nie są publikowane.
DANE_DLA_STRONY = ("stan-rynku/stan.json", "stan-rynku/ocena.json")

# Dozwolone typy plików w web/: kod i styl strony, dane i obrazy. Inny typ zatrzymuje budowę, żeby nikt nie opublikował
# czegoś (np. nagrania albo arkusza) bez świadomej zmiany tej listy.
ROZSZERZENIA_WEB = {".html", ".js", ".css", ".json", ".png", ".svg", ".ico", ".txt", ".webmanifest"}

# Co musi być w gotowej stronie, żeby wejście z README nie kończyło się pustym ekranem.
WYMAGANE = ("index.html", "404.html", "stan-rynku/index.html", "biblioteka/index.html", "style.css", "shared/sidebar.js",
            "data/stan-rynku/stan.json", "data/stan-rynku/ocena.json")


def zbuduj(wyjscie: Path = DOMYSLNE_WYJSCIE, web: Path = WEB, dane: Path = DANE) -> dict:
    """Buduje katalog strony od zera. Zwraca liczbę plików i rozmiar w KB; przy błędzie zgłasza RuntimeError."""
    if wyjscie.exists():
        shutil.rmtree(wyjscie)
    wyjscie.mkdir(parents=True)

    liczba = 0
    for zrodlo in sorted(web.rglob("*")):
        if not zrodlo.is_file():
            continue
        if zrodlo.suffix.lower() not in ROZSZERZENIA_WEB:
            raise RuntimeError(f"niedozwolony typ pliku w web/: {zrodlo.relative_to(web)} (dopisz rozszerzenie do ROZSZERZENIA_WEB, jeśli to zamierzone)")
        cel = wyjscie / zrodlo.relative_to(web)
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(zrodlo, cel)
        liczba += 1

    for wzgledna in DANE_DLA_STRONY:
        zrodlo = dane / wzgledna
        if not zrodlo.is_file():
            raise RuntimeError(f"brak pliku danych dla strony: data/{wzgledna}")
        cel = wyjscie / "data" / wzgledna
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(zrodlo, cel)
        liczba += 1

    (wyjscie / ".nojekyll").write_text("", encoding="utf-8")

    brakujace = [w for w in WYMAGANE if not (wyjscie / w).is_file()]
    if brakujace:
        raise RuntimeError(f"w gotowej stronie brakuje plików: {', '.join(brakujace)}")
    rozmiar = sum(p.stat().st_size for p in wyjscie.rglob("*") if p.is_file())
    return {"plikow": liczba, "rozmiar_kb": round(rozmiar / 1024)}


def main(argv: list[str]) -> int:
    wyjscie = Path(argv[1]).resolve() if len(argv) > 1 else DOMYSLNE_WYJSCIE
    try:
        wynik = zbuduj(wyjscie)
    except RuntimeError as blad:
        print(f"BŁĄD: {blad}", file=sys.stderr)
        return 1
    print(f"strona złożona w {wyjscie}: {wynik['plikow']} plików, {wynik['rozmiar_kb']} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
