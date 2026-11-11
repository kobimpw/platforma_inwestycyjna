"""Lokalny podgląd strony: serwer, który mapuje adresy tak samo, jak układ katalogu `_site/` składany dla GitHub Pages.

    python src/narzedzia/serwer.py [port]        (albo `make serve`; domyślnie port 8000)

Adresy zamieniane są na pliki w repozytorium według tych samych reguł co `src/narzedzia/zbuduj_strone.py`:
  /<karta>/...  ->  web/<karta>/...      strona: HTML, CSS, JS
  /data/...     ->  data/...             dane, które czyta przeglądarka (karta Stan rynku czyta data/stan-rynku/stan.json)

To wersja poglądowa: karta Stan rynku działa w całości z plików, bo rachunek robi skrypt w Pythonie, a przeglądarka tylko
czyta gotowe dane.
"""

import mimetypes
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

KORZEN = Path(__file__).resolve().parents[2]
KORZENIE = {"data": KORZEN / "data"}   # osobny korzeń obok strony
STRONA = KORZEN / "web"

mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("application/manifest+json", ".webmanifest")


def sciezka_pliku(sciezka_url: str) -> Path | None:
    """Odpowiednik `sciezkaWRepo` z bramki: adres -> plik w repozytorium (None, gdy niedozwolony)."""
    plik = unquote(urlsplit(sciezka_url).path).lstrip("/")
    if plik == "" or plik.endswith("/"):
        plik += "index.html"
    segmenty = plik.split("/")
    if ".." in segmenty or "" in segmenty or "\\" in plik:
        return None
    pierwszy, reszta = segmenty[0], segmenty[1:]
    if pierwszy in KORZENIE and reszta:
        return KORZENIE[pierwszy].joinpath(*reszta)
    return STRONA / plik


class Obsluga(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        plik = sciezka_pliku(path)
        return str(plik) if plik is not None else str(KORZEN / "__brak__")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")   # podgląd ma zawsze pokazywać aktualne pliki
        super().end_headers()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    serwer = ThreadingHTTPServer(("127.0.0.1", port), Obsluga)
    print(f"Podgląd strony: http://127.0.0.1:{port}/  (Ctrl+C kończy)")
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
