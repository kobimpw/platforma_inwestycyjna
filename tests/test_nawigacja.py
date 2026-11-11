"""Nawigacja i listy kart: odnośniki prowadzą do istniejących stron, a listy kart w modułach wspólnych są ze sobą zgodne.

W tej wersji poglądowej są tylko dwie karty (Stan rynku i Biblioteka), ale nazwy kart są wpisane w kilku miejscach:
w nawigacji (sidebar.js), w rozpoznawaniu bloków (oznaczenia.js), w liście kart modułu zapisu (projekty.js) i w mapie
kodu (mapa_kodu.py). Rozjazd tych list objawiałby się dopiero w przeglądarce, np. martwym linkiem albo pustą zakładką
„Kod", więc pilnuje ich test."""

import re

import mapa_kodu


def _tekst(korzen, sciezka):
    return (korzen / sciezka).read_text(encoding="utf-8")


def _odnosniki_nawigacji(korzen) -> list[str]:
    blok = re.search(r"const STRONY = \[(.*?)\n\];", _tekst(korzen, "web/shared/sidebar.js"), re.S).group(1)
    return re.findall(r'href: "([^"]*)"', blok)


def _karty_z_nawigacji(korzen) -> set[str]:
    return {h.strip("/") for h in _odnosniki_nawigacji(korzen) if h and not h.startswith("http")}


def test_kazdy_odnosnik_nawigacji_prowadzi_do_istniejacej_strony(korzen):
    odnosniki = _odnosniki_nawigacji(korzen)
    assert "" in odnosniki, "nawigacja musi mieć stronę startową"
    for href in odnosniki:
        assert (korzen / "web" / href / "index.html").is_file(), f"brak strony dla odnośnika {href!r}"


def test_listy_kart_w_modulach_wspolnych_zgadzaja_sie_z_nawigacja(korzen):
    karty = _karty_z_nawigacji(korzen)
    assert karty, "nawigacja nie ma żadnej karty"
    oznaczenia = set(re.findall(r'"([a-zA-Z-]+)"', re.search(r"const OZNACZENIA_KARTY = \[(.*?)\];", _tekst(korzen, "web/shared/oznaczenia.js"), re.S).group(1)))
    projekty = set(re.findall(r'\["([a-zA-Z-]+)", "', re.search(r"const KARTY = \[(.*?)\n  \];", _tekst(korzen, "web/shared/projekty.js"), re.S).group(1)))
    assert oznaczenia == karty, "lista OZNACZENIA_KARTY w oznaczenia.js nie zgadza się z nawigacją"
    assert projekty == karty, "lista KARTY w projekty.js nie zgadza się z nawigacją"
    assert set(mapa_kodu.KARTY) == karty, "lista KARTY w mapa_kodu.py nie zgadza się z nawigacją"


def test_strony_kart_ustawiaja_poprawny_korzen_nawigacji(korzen):
    """Strona startowa leży w korzeniu (`./`), a karty piętro niżej (`../`): od tego zależą linki w pasku bocznym."""
    assert 'window.SIDEBAR_ROOT = "./"' in _tekst(korzen, "web/index.html")
    for karta in _karty_z_nawigacji(korzen):
        assert 'window.SIDEBAR_ROOT = "../"' in _tekst(korzen, f"web/{karta}/index.html"), karta


def test_odwolania_w_stronach_sa_wzgledne_wiec_dzialaja_pod_podsciezka_pages(korzen):
    """GitHub Pages publikuje projekt pod adresem z nazwą repozytorium, więc odwołanie zaczynające się od `/` by się zepsuło.

    Jedyny wyjątek to strona 404, którą serwer pokazuje pod dowolnym adresem i która sama wylicza link do startu."""
    bezwzgledne = re.compile(r"""(?:href|src|action)=["']/[^/"']|fetch\(["'`]/[^/]""")
    zle = []
    for plik in sorted((korzen / "web").rglob("*")):
        if plik.suffix in {".html", ".js"} and plik.name != "404.html":
            zle += [f"{plik.relative_to(korzen)}: {m.group(0)}" for m in bezwzgledne.finditer(plik.read_text(encoding="utf-8"))]
    assert zle == []
