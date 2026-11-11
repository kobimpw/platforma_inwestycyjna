"""Buduje `web/shared/mapa-kodu.json` — mapę „numerek bloku -> fragmenty kodu”.

Skrypt czyta gotowe pliki wszystkich kart w `docs/` (`index.html`, `app.js`,
`style.css`) i dla każdego numerowanego bloku strony (tego samego, który
`web/shared/oznaczenia.js` oznacza numerkiem w lewym górnym rogu) wyszukuje:

  * HTML   — linie `index.html`, z których składa się blok,
  * JS     — funkcje i stałe z `app.js`, które sięgają po elementy tego bloku
             (po `id` i po klasach występujących tylko w tym bloku), oraz
             funkcje przez nie wywoływane (do trzech poziomów w głąb),
  * CSS    — reguły z `style.css`, których selektory dotykają tych samych
             klas i identyfikatorów.

Dla kart GENEROWANYCH z jednego pliku `.py` (VaR, ETF sektorowe, News, Zajęcie
pozycji, Projekty i uwagi) każdy fragment dostaje też adres w pliku
generatora — tam się go edytuje, bo `index.html` i `app.js` są wtedy
tylko wynikiem `python <karta>.py`. Dla kart pisanych ręcznie (Opcje,
Earnings, Technical Analyst) edytuje się wprost `index.html` / `app.js`.

To jest PRZYBLIŻENIE zbudowane heurystyką (dopasowanie nazw), nie analiza
programu: funkcja wywoływana dynamicznie albo przez nazwę składaną z kawałków
tekstu może się nie znaleźć w mapie, a nazwa `id` użyta w niepowiązanym
miejscu może dodać fałszywy trafiony fragment. Dymek pokazuje ją jako
„automatyczne przybliżenie”.

MAPĘ TRZEBA PRZEBUDOWAĆ po każdej zmianie kodu karty (numery linii się
przesuwają): `python src/narzedzia/mapa_kodu.py` z korzenia repozytorium. Przy
kartach generowanych najpierw uruchom generator karty (`python <karta>.py`).
"""

import ast
import bisect
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

# ===========================================================================
# magazyn funkcji
# ===========================================================================
KORZEN = Path(__file__).resolve().parents[2]
WEB = KORZEN / "web"        # strona: index.html, app.js, style.css
SRC = KORZEN / "src"        # generatory kart (.py)
WYJSCIE = WEB / "shared" / "mapa-kodu.json"

# id karty (to samo, co rozpoznaje oznaczenia.js) -> pliki, z których się składa.
# `gen` = plik generatora .py (None = HTML i JS pisane ręcznie),
# `blizniak` = pythonowy wzorzec rachunku, którego strona nie uruchamia.
KARTY = {
    "biblioteka": {"html": "biblioteka/index.html", "js": "biblioteka/app.js", "gen": "biblioteka/biblioteka.py", "blizniak": None},
    "stan-rynku": {"html": "stan-rynku/index.html", "js": "stan-rynku/app.js", "gen": "stan_rynku/stan_rynku.py", "blizniak": None},
}

MAX_LINII_FRAGMENTU = 70          # dłuższy fragment jest przycinany w mapie
MAX_JS_BEZPOSREDNIO = 12
MAX_JS_POZNIEJ = 10
MAX_CSS = 14
GLEBOKOSC_WYWOLAN = 3

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def _linie(sciezka: Path) -> list[str]:
    return sciezka.read_text(encoding="utf-8").split("\n")


def _rel(sciezka: Path) -> str:
    return sciezka.resolve().relative_to(KORZEN).as_posix()


# ---------------------------------------------------------------- HTML -> drzewo
class Wezel:
    def __init__(self, tag: str, attrs: dict, start: int):
        self.tag = tag
        self.attrs = attrs
        self.start = start
        self.end = start
        self.dzieci: list["Wezel"] = []
        self.tekst: list[str] = []

    def klasy(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def caly_tekst(self) -> str:
        czesci = list(self.tekst)
        for d in self.dzieci:
            czesci.append(d.caly_tekst())
        return " ".join(" ".join(czesci).split())

    def potomkowie(self):
        yield self
        for d in self.dzieci:
            yield from d.potomkowie()


class ParserHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.korzen = Wezel("root", {}, 1)
        self.stos = [self.korzen]

    def handle_starttag(self, tag, attrs):
        w = Wezel(tag, dict(attrs), self.getpos()[0])
        w.end = w.start
        self.stos[-1].dzieci.append(w)
        if tag not in VOID:
            self.stos.append(w)

    def handle_startendtag(self, tag, attrs):
        w = Wezel(tag, dict(attrs), self.getpos()[0])
        self.stos[-1].dzieci.append(w)

    def handle_endtag(self, tag):
        for i in range(len(self.stos) - 1, 0, -1):
            if self.stos[i].tag == tag:
                for w in self.stos[i:]:
                    w.end = self.getpos()[0]
                del self.stos[i:]
                return

    def handle_data(self, dane):
        if dane.strip() and self.stos[-1].tag not in ("script", "style"):
            self.stos[-1].tekst.append(dane.strip())


def _znajdz(w: Wezel, tag: str):
    for x in w.potomkowie():
        if x.tag == tag:
            return x
    return None


def _jest_karta(w: Wezel) -> bool:
    return "karta" in w.klasy()


def _ma_karte_bezposrednio(w: Wezel) -> bool:
    return any(_jest_karta(d) for d in w.dzieci)


def _warstwa_ukladu(w: Wezel) -> bool:
    """Lustro `jestWarstwaUkladu` z web/shared/oznaczenia.js."""
    if _jest_karta(w):
        return False
    dzieci = [d for d in w.dzieci if d.tag not in ("script", "style")]
    return bool(dzieci) and all(_jest_karta(d) or _ma_karte_bezposrednio(d) for d in dzieci)


def zbierz_bloki(main: Wezel):
    """Lustro `zbierzBlokiDoOznaczenia`: (lista bloków, {litera: [numery bloków]})."""
    bloki: list[Wezel] = []
    grupy: dict[str, list[int]] = {}
    for dziecko in main.dzieci:
        if dziecko.tag in ("script", "style") or "hidden" in dziecko.attrs:
            continue
        if _warstwa_ukladu(dziecko):
            litera = chr(65 + len(grupy) % 26)
            numery = []
            for wnuk in dziecko.dzieci:
                if wnuk.tag in ("script", "style"):
                    continue
                karta = wnuk if _jest_karta(wnuk) else next((d for d in wnuk.dzieci if _jest_karta(d)), None)
                bloki.append(karta or wnuk)
                numery.append(len(bloki))
            grupy[litera] = numery
        else:
            bloki.append(dziecko)
    return bloki, grupy


# ---------------------------------------------------------------- JS -> jednostki
def jednostki_js(linie: list[str]) -> list[dict]:
    """Dzieli plik JS na jednostki najwyższego poziomu (funkcja, stała, blok kodu).

    Podział po liniach: nowa jednostka zaczyna się od linii bez wcięcia, która
    nie zamyka poprzedniej (`}`, `)`, `]`) i nie jest komentarzem; komentarz
    stykający się bezpośrednio z taką linią należy do niej. Wnętrze literałów
    szablonowych (backticki) jest pomijane.
    """
    starty: list[int] = []
    w_szablonie = False
    komentarz_od = None
    for nr, l in enumerate(linie, 1):
        if not w_szablonie:
            if not l.strip():
                komentarz_od = None
            elif l[0] not in " \t":
                if l.startswith(("//", "/*")):
                    if komentarz_od is None:
                        komentarz_od = nr
                elif l[0] not in "}])":
                    starty.append(komentarz_od or nr)
                    komentarz_od = None
                else:
                    komentarz_od = None
        if len(re.findall(r"(?<!\\)`", l)) % 2 == 1:
            w_szablonie = not w_szablonie
    jednostki = []
    for i, s in enumerate(starty):
        koniec = (starty[i + 1] - 1) if i + 1 < len(starty) else len(linie)
        while koniec > s and not linie[koniec - 1].strip():
            koniec -= 1
        tekst = "\n".join(linie[s - 1:koniec])
        pierwsza = next((l for l in linie[s - 1:koniec] if l and not l.startswith(("//", "/*", " *"))), linie[s - 1])
        m = re.match(r"\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", pierwsza)
        if m:
            nazwa = f"{m.group(1)}()"
            klucz = m.group(1)
        else:
            m = re.match(r"\s*(?:const|let|var)\s+(\w+)", pierwsza)
            nazwa = klucz = m.group(1) if m else ""
            if not m:
                nazwa = pierwsza.strip()[:48]
        jednostki.append({"nazwa": nazwa, "klucz": klucz, "od": s, "do": koniec, "tekst": tekst})
    return jednostki


# ---------------------------------------------------------------- CSS -> reguły
def reguly_css(zrodlo: str) -> list[dict]:
    bez_komentarzy = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), zrodlo, flags=re.S)
    poczatki = [0]
    for m in re.finditer(r"\n", bez_komentarzy):
        poczatki.append(m.end())
    nr = lambda poz: bisect.bisect_right(poczatki, poz)
    wynik = []
    for m in re.finditer(r"([^{}@;]+?)\{([^{}]*)\}", bez_komentarzy):
        selektor = " ".join(m.group(1).split())
        if not selektor or selektor.startswith(("from", "to")) or re.fullmatch(r"[\d.%\s,]+", selektor):
            continue
        poz_start = m.start(1) + (len(m.group(1)) - len(m.group(1).lstrip()))
        wynik.append({"selektor": selektor, "od": nr(poz_start), "do": nr(m.end() - 1)})
    return wynik


# ---------------------------------------------------------------- .py generatora
def stale_z_py(sciezka: Path):
    """Zwraca (lista (nazwa, od, do) stałych tekstowych, funkcja generuj lub None)."""
    drzewo = ast.parse(sciezka.read_text(encoding="utf-8"))
    stale, generuj = [], None
    for w in drzewo.body:
        if isinstance(w, ast.Assign) and len(w.targets) == 1 and isinstance(w.targets[0], ast.Name):
            if isinstance(w.value, ast.Constant) and isinstance(w.value.value, str):
                stale.append((w.targets[0].id, w.lineno, w.end_lineno))
            else:
                stale.append((w.targets[0].id, w.lineno, w.end_lineno))
        if isinstance(w, ast.FunctionDef) and w.name == "generuj":
            generuj = (w.lineno, w.end_lineno)
    return stale, generuj


def _norm_py(l: str) -> str:
    return l.strip().replace("\\\\", "\\")


def znajdz_w_py(fragment: list[str], py: list[str], stale: list[tuple]):
    """Szuka w pliku generatora dokładnie tych linii (po obcięciu wcięć).

    Zwraca (od, do, nazwa stałej) albo None. Linia w linię — stąd działa dla
    napisów wielolinijkowych (potrójny cudzysłów), ale nie dla sklejanych z
    wielu literałów.
    """
    if not fragment:
        return None
    for pierwszy, l in enumerate(fragment):
        if l.strip():
            break
    cel = [x.strip() for x in fragment]
    zakresy = [(n, a, b) for n, a, b in stale]
    for p in range(len(py)):
        if _norm_py(py[p]) != cel[pierwszy] and py[p].strip() != cel[pierwszy]:
            continue
        start = p - pierwszy
        if start < 0 or start + len(cel) > len(py):
            continue
        ok = True
        for k, c in enumerate(cel):
            if _norm_py(py[start + k]) != c and py[start + k].strip() != c:
                ok = False
                break
        if not ok:
            continue
        for nazwa, a, b in zakresy:
            if a <= start + 1 and start + len(cel) <= b:
                return start + 1, start + len(cel), nazwa
    return None


def znajdz_poczatek_w_py(fragment: list[str], py: list[str], stale: list[tuple], minimum: int = 3):
    """Zapas dla bloku złożonego w generuj() z kilku stałych (np. panel „Płynność”
    wstawiany do okna „Zakłady”): najdłuższy początek bloku, który leży w całości
    w jednej stałej. Dopasowanie początku jest monotoniczne (krótszy początek
    pasuje, jeśli pasuje dłuższy), więc wystarcza wyszukiwanie połówkowe.
    """
    lewy, prawy, najlepszy = minimum, len(fragment) - 1, None
    while lewy <= prawy:
        srodek = (lewy + prawy) // 2
        znaleziono = znajdz_w_py(fragment[:srodek], py, stale)
        if znaleziono:
            najlepszy, lewy = znaleziono, srodek + 1
        else:
            prawy = srodek - 1
    return najlepszy


# ---------------------------------------------------------------- składanie mapy
def _kod(linie: list[str], od: int, do: int) -> tuple[str, int]:
    """Tekst fragmentu przycięty do MAX_LINII_FRAGMENTU; zwraca (tekst, ile linii pominięto)."""
    fragment = linie[od - 1:do]
    pominieto = max(0, len(fragment) - MAX_LINII_FRAGMENTU)
    return "\n".join(fragment[:MAX_LINII_FRAGMENTU]), pominieto


def zbuduj_karte(id_karty: str, opis: dict) -> dict:
    sciezka_html = WEB / opis["html"]
    sciezka_js = WEB / opis["js"]
    linie_html, linie_js = _linie(sciezka_html), _linie(sciezka_js)
    linie_css = _linie(WEB / "style.css")

    parser = ParserHTML()
    parser.feed(sciezka_html.read_text(encoding="utf-8"))
    main = _znajdz(parser.korzen, "main")
    body = _znajdz(parser.korzen, "body")
    zakres_strony = f"body#{body.attrs['id']}" if body is not None and body.attrs.get("id") else None
    bloki, grupy = zbierz_bloki(main)

    py_linie, stale, generuj = ([], [], None)
    if opis["gen"]:
        sciezka_py = SRC / opis["gen"]
        py_linie = _linie(sciezka_py)
        stale, generuj = stale_z_py(sciezka_py)

    jednostki = jednostki_js(linie_js)
    css = reguly_css("\n".join(linie_css))

    # identyfikatory i klasy każdego bloku
    ids, klasy = [], []
    for b in bloki:
        i, k = set(), set()
        for x in b.potomkowie():
            if x.attrs.get("id"):
                i.add(x.attrs["id"])
            k.update(x.klasy())
        ids.append(i)
        klasy.append(k)
    licznik_klas: dict[str, int] = {}
    for k in klasy:
        for c in k:
            licznik_klas[c] = licznik_klas.get(c, 0) + 1

    def zrodlo(plik_gen_linie, od, do, linie_wyniku):
        if not py_linie:
            return None
        fragment = linie_wyniku[od - 1:do]
        znaleziono = znajdz_w_py(fragment, py_linie, stale) or znajdz_poczatek_w_py(fragment, py_linie, stale)
        if not znaleziono:
            return None
        a, b, nazwa = znaleziono
        return {"plik": _rel(SRC / opis["gen"]), "od": a, "do": b, "nazwa": nazwa}

    wynik_bloki = {}
    for numer, blok in enumerate(bloki, 1):
        segmenty = []
        # --- HTML
        od, do = blok.start, max(blok.end, blok.start)
        kod, pominieto = _kod(linie_html, od, do)
        segmenty.append({
            "rola": "HTML", "nazwa": f"<{blok.tag}{(' class=' + chr(34) + ' '.join(blok.klasy()) + chr(34)) if blok.klasy() else ''}>",
            "plik": _rel(sciezka_html), "od": od, "do": do, "poziom": 0,
            "zrodlo": zrodlo(None, od, do, linie_html), "kod": kod, "pominieto": pominieto,
        })

        # --- JS: bezpośrednio + wywoływane
        wlasne_klasy = {c for c in klasy[numer - 1] if licznik_klas[c] == 1 and len(c) >= 4}
        wzorce = [re.compile(r"""["'`#]%s(?![\w-])""" % re.escape(i)) for i in ids[numer - 1]]
        wzorce += [re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(c)) for c in wlasne_klasy]
        wybrane: dict[int, int] = {}
        for idx, j in enumerate(jednostki):
            if j["nazwa"].startswith(("//", "/*")):
                continue
            if any(w.search(j["tekst"]) for w in wzorce):
                wybrane[idx] = 1
        poziom = 1
        biezace = [i for i, p in wybrane.items() if p == 1]
        while poziom < GLEBOKOSC_WYWOLAN and biezace:
            poziom += 1
            nastepne = []
            teksty = "\n".join(jednostki[i]["tekst"] for i in biezace)
            for idx, j in enumerate(jednostki):
                if idx in wybrane or not j["klucz"] or len(j["klucz"]) < 4:
                    continue
                if re.search(r"(?<![\w.$])%s\b" % re.escape(j["klucz"]), teksty):
                    wybrane[idx] = poziom
                    nastepne.append(idx)
            biezace = nastepne
        posortowane = sorted(wybrane.items(), key=lambda x: (x[1], x[0]))
        bezposrednie = [x for x in posortowane if x[1] == 1][:MAX_JS_BEZPOSREDNIO]
        dalsze = [x for x in posortowane if x[1] > 1][:MAX_JS_POZNIEJ]
        for idx, p in sorted(bezposrednie + dalsze, key=lambda x: x[0]):
            j = jednostki[idx]
            kod, pominieto = _kod(linie_js, j["od"], j["do"])
            segmenty.append({
                "rola": "JS", "nazwa": j["nazwa"], "plik": _rel(sciezka_js), "od": j["od"], "do": j["do"],
                "poziom": p - 1, "zrodlo": zrodlo(None, j["od"], j["do"], linie_js), "kod": kod, "pominieto": pominieto,
            })

        # --- CSS: klasy występujące tylko w tym bloku i identyfikatory; klasy
        # wspólne dla kilku bloków liczą się tylko w regułach objętych zakresem
        # tej samej strony (`body#pg-...`), żeby ogólne `.status` z całego pliku
        # nie zaśmiecały każdego bloku.
        unikalne = {c for c in klasy[numer - 1] if licznik_klas[c] == 1 and len(c) >= 3}
        wzorce_css = [re.compile(r"\.%s(?![\w-])" % re.escape(c)) for c in unikalne]
        wzorce_css += [re.compile(r"#%s(?![\w-])" % re.escape(i)) for i in ids[numer - 1]]
        wszystkie_css = [re.compile(r"\.%s(?![\w-])" % re.escape(c)) for c in klasy[numer - 1] if len(c) >= 3]

        def trafia(selektor: str) -> bool:
            inna_strona = re.match(r"body#pg-\w+", selektor) and not (zakres_strony and selektor.startswith(zakres_strony))
            if inna_strona:
                return False
            # style karty zadania / dymka (dopisane do wspólnego style.css) nie dotyczą innych kart
            if id_karty != "projekty-i-uwagi" and re.search(r"body\.pu|\.z-|\.pu-|\.md-|\.t-podzad|\.oznaczenie", selektor):
                return False
            if any(w.search(selektor) for w in wzorce_css):
                return True
            return bool(zakres_strony and selektor.startswith(zakres_strony) and any(w.search(selektor) for w in wszystkie_css))

        trafione = [r for r in css if trafia(r["selektor"])][:MAX_CSS]
        for r in trafione:
            kod, pominieto = _kod(linie_css, r["od"], r["do"])
            segmenty.append({
                "rola": "CSS", "nazwa": r["selektor"][:70], "plik": "web/style.css", "od": r["od"], "do": r["do"],
                "poziom": 0, "zrodlo": None, "kod": kod, "pominieto": pominieto,
            })

        etykieta = ""
        for x in blok.potomkowie():
            if x.tag in ("h1", "h2", "h3"):
                etykieta = x.caly_tekst()[:60]
                break
        wynik_bloki[str(numer)] = {"etykieta": etykieta, "segmenty": segmenty}

    pliki = []
    if opis["gen"]:
        pliki.append({"sciezka": _rel(SRC / opis["gen"]), "rola": "generator — tu edytujesz kod karty", "linii": len(py_linie)})
    pliki.append({"sciezka": _rel(sciezka_html), "rola": "wygenerowany HTML (nie edytuj ręcznie)" if opis["gen"] else "HTML pisany ręcznie — edytujesz go wprost", "linii": len(linie_html)})
    pliki.append({"sciezka": _rel(sciezka_js), "rola": "wygenerowany JS (nie edytuj ręcznie)" if opis["gen"] else "JS pisany ręcznie — edytujesz go wprost", "linii": len(linie_js)})
    pliki.append({"sciezka": "web/style.css", "rola": "wspólne style", "linii": len(linie_css)})
    if opis["blizniak"]:
        sciezka_b = SRC / opis["blizniak"]
        pliki.append({"sciezka": _rel(sciezka_b), "rola": "pythonowy wzorzec rachunku (strona go nie uruchamia)", "linii": len(_linie(sciezka_b))})

    return {
        "pliki": pliki,
        "generuj": {"plik": _rel(SRC / opis["gen"]), "od": generuj[0], "do": generuj[1]} if generuj else None,
        "grupy": grupy,
        "bloki": wynik_bloki,
    }


def zbuduj() -> dict:
    return {
        "wersja": 1,
        "wygenerowano": date.today().isoformat(),
        "uwaga": "Automatyczne przybliżenie (dopasowanie nazw), szczegóły w src/narzedzia/mapa_kodu.py.",
        "karty": {id_karty: zbuduj_karte(id_karty, opis) for id_karty, opis in KARTY.items()},
    }


# ===========================================================================
# elementy
# ===========================================================================
def generuj_mape() -> None:
    mapa = zbuduj()
    WYJSCIE.write_text(json.dumps(mapa, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    for id_karty, karta in mapa["karty"].items():
        licznosc = {n: len(b["segmenty"]) for n, b in karta["bloki"].items()}
        zrodel = sum(1 for b in karta["bloki"].values() for s in b["segmenty"] if s["zrodlo"])
        print(f"{id_karty:20} bloków: {len(licznosc):2}  segmentów: {sum(licznosc.values()):3}  z adresem w generatorze: {zrodel}")
    print(f"zapisano {WYJSCIE} ({WYJSCIE.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    generuj_mape()
