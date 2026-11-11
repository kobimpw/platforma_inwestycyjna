"""Pobiera próbki danych rynkowych dla trybu poglądowego kart VaR i Pozycja i zapisuje je w `data/przyklad/`.

    python src/narzedzia/pobierz_probki.py [katalog]     (albo `make probki`; domyślnie `data/przyklad/`)

W pełnej platformie karty VaR i Pozycja pytają o notowania (Yahoo Finance) i łańcuch opcji (Cboe) własny serwer
pośredniczący, bo przeglądarka nie może pytać tych źródeł wprost (ich odpowiedzi nie mają nagłówków CORS). Wersja
poglądowa nie ma takiego serwera, więc karty czytają zapisane tu próbki w **tym samym kształcie**, jaki zwracają źródła
(moduł `web/shared/probka.js`):

  quote-<TICKER>.json     odpowiedź wykresu Yahoo Finance (meta i dzienne świece z ostatnich 10 lat)
  options-<SYMBOL>.json   łańcuch opcji Cboe przycięty do najbliższych terminów i strike'ów wokół ceny (reguła niżej)
  indeks.json             spis próbek, czas pobrania i opis przycięcia

Próbki są małe, opisane jako przykładowe i nie służą do dalszej redystrybucji; zakres i warunki użycia danych wyznaczają
ich dostawcy. Skrypt używa tylko biblioteki standardowej i nie wymaga żadnych kluczy.

Uwaga: przycięty łańcuch zmienia wskaźniki liczone z CAŁEGO łańcucha (np. ekspozycję gamma), więc karta Pozycja pokazuje je
dla próbki, a nie dla pełnych danych. Opis przycięcia jest w `indeks.json` i na stronie.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[2]
DOMYSLNY_KATALOG = KORZEN / "data" / "przyklad"

YAHOO_WYKRES = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=10y&interval=1d"
CBOE_LANCUCH = "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
UA = "Mozilla/5.0 (compatible; platforma-inwestycyjna-probki/1.0)"

# Tickery, dla których karty mają próbki: ETF-y i indeksy z profili przykładowych Pozycji oraz domyślne tickery VaR.
NOTOWANIA = ["SPY", "QQQ", "^GSPC", "^NDX", "^XSP", "^XND"]
LANCUCHY = ["_XSP", "_XND"]

# Przycięcie łańcucha (pełny ma kilkanaście tysięcy opcji, a XSP ponad 7 MB):
#  - terminy do 100 dni (wystarcza na strukturę terminową 30 i 90 dni),
#  - strike'i od 88% do 112% ceny indeksu,
#  - calle od 98% do 110% ceny i do 45 dni zostają ze WSZYSTKIMI strike'ami, bo z nich generator buduje zakłady (spready),
#  - pozostałe opcje tylko na grubszej siatce strike'ów: co 5 punktów dla indeksów powyżej 400 pkt, co 2 dla pozostałych.
MAKS_DNI = 100
OKNO_STRIKE = (0.88, 1.12)
GESTE_CALLE = (0.98, 1.10)
PELNE_DO_DNI = 45

META_POLA = ["symbol", "currency", "exchangeName", "fullExchangeName", "instrumentType", "regularMarketPrice", "regularMarketTime",
             "chartPreviousClose", "previousClose", "timezone", "exchangeTimezoneName", "shortName", "longName"]
OPCJA_POLA = ["option", "bid", "bid_size", "ask", "ask_size", "iv", "open_interest", "volume", "delta", "gamma", "theta", "theo",
              "last_trade_time"]
SYMBOL_OPCJI = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def pobierz_json(url: str, timeout: int = 120):
    """Pobiera adres i zwraca zdekodowany JSON (przekierowania są obsługiwane przez urllib)."""
    zadanie = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(zadanie, timeout=timeout) as odp:
        return json.loads(odp.read().decode("utf-8"))


def nazwa_pliku(prefiks: str, klucz: str) -> str:
    """`^XSP` -> `quote-_XSP.json`: znaki spoza liter, cyfr i podkreślenia zamieniamy na podkreślenie (to samo robi probka.js)."""
    return f"{prefiks}-{re.sub(r'[^A-Za-z0-9_]', '_', klucz)}.json"


def _zaokraglij(wartosc, miejsca: int):
    return round(wartosc, miejsca) if isinstance(wartosc, float) else wartosc


def przytnij_notowania(surowe: dict) -> dict:
    """Zostawia z odpowiedzi Yahoo tylko to, co czytają karty: wybrane pola `meta` i dzienne świece (open, high, low, close)."""
    wynik = (surowe.get("chart") or {}).get("result") or []
    if not wynik or not wynik[0].get("timestamp"):
        raise RuntimeError(f"Yahoo: pusta odpowiedź ({(surowe.get('chart') or {}).get('error')})")
    r = wynik[0]
    q = (r.get("indicators") or {}).get("quote") or [{}]
    swiece = {k: [_zaokraglij(x, 4) for x in (q[0].get(k) or [])] for k in ("open", "high", "low", "close")}
    return {"chart": {"result": [{"meta": {k: r["meta"][k] for k in META_POLA if k in r["meta"]},
                                  "timestamp": r["timestamp"], "indicators": {"quote": [swiece]}}], "error": None}}


def data_migawki(znacznik_czasu: str) -> date:
    """`2026-11-11 11:01:57` -> data migawki łańcucha (część daty z pola timestamp)."""
    return date.fromisoformat(str(znacznik_czasu)[:10])


def przytnij_lancuch(surowe: dict, maks_dni: int = MAKS_DNI, okno: tuple = OKNO_STRIKE, gesty_call: tuple = GESTE_CALLE,
                     pelne_do: int = PELNE_DO_DNI) -> dict:
    """Przycina łańcuch Cboe według reguły z opisu modułu i do pól czytanych przez kartę (kształt odpowiedzi bez zmian)."""
    dane = surowe.get("data") or {}
    opcje = dane.get("options")
    cena = dane.get("current_price")
    if not isinstance(opcje, list) or not isinstance(cena, (int, float)) or cena <= 0:
        raise RuntimeError("Cboe: nieoczekiwana odpowiedź (brak data.options albo ceny indeksu)")
    dzien = data_migawki(surowe["timestamp"])
    krok = 5 if cena > 400 else 2
    zostaja = []
    for o in opcje:
        m = SYMBOL_OPCJI.match(o.get("option", ""))
        if not m:
            continue
        termin = date(2000 + int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:6]))
        strike = int(m.group(4)) / 1000
        dni = (termin - dzien).days
        if not (0 <= dni <= maks_dni and cena * okno[0] <= strike <= cena * okno[1]):
            continue
        gesty = m.group(3) == "C" and cena * gesty_call[0] <= strike <= cena * gesty_call[1] and dni <= pelne_do
        if not gesty and round(strike) % krok != 0:
            continue
        zostaja.append({k: _zaokraglij(o[k], 6) for k in OPCJA_POLA if k in o})
    if not zostaja:
        raise RuntimeError("Cboe: po przycięciu nie zostały żadne opcje")
    reszta = {k: v for k, v in dane.items() if k != "options"}
    return {"timestamp": surowe["timestamp"], "data": {**reszta, "options": zostaja}}


def zapisz_json(sciezka: Path, obiekt) -> int:
    """Zapisuje zwarty JSON (bez zbędnych spacji) i zwraca rozmiar w bajtach."""
    tekst = json.dumps(obiekt, ensure_ascii=False, separators=(",", ":"))
    sciezka.write_text(tekst + "\n", encoding="utf-8")
    return len(tekst.encode("utf-8"))


def pobierz_i_zapisz(katalog: Path, pobierz=pobierz_json, teraz: datetime | None = None) -> dict:
    """Pobiera wszystkie próbki, zapisuje je w katalogu i zwraca spis (ten sam, który trafia do indeks.json)."""
    katalog.mkdir(parents=True, exist_ok=True)
    teraz = teraz or datetime.now(timezone.utc)
    spis = {
        "wersja": 1,
        "pobrano": teraz.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "opis": "Próbki danych rynkowych dla trybu poglądowego kart VaR i Pozycja. Zapis z publicznych źródeł, nie na żywo; "
                "nie do dalszej redystrybucji. Zakres i warunki użycia danych wyznaczają ich dostawcy.",
        "zrodla": {"notowania": "Yahoo Finance, wykres dzienny (10 lat)", "lancuchy": "Cboe, opóźnione notowania opcji"},
        "przyciecie_lancuchow": {
            "maks_dni": MAKS_DNI, "okno_strike": list(OKNO_STRIKE), "gesty_zakres_callow": list(GESTE_CALLE), "pelne_do_dni": PELNE_DO_DNI,
            "opis": "Terminy do 100 dni, strike'i od 88% do 112% ceny; calle od 98% do 110% ceny i do 45 dni ze wszystkimi strike'ami, "
                    "reszta tylko na grubszej siatce (co 5 punktów, a dla indeksów poniżej 400 pkt co 2). Wskaźniki liczone z CAŁEGO "
                    "łańcucha (np. ekspozycja gamma, put/call z otwartych pozycji) mogą się przez to różnić od pełnych danych.",
        },
        "notowania": {},
        "lancuchy": {},
    }
    for ticker in NOTOWANIA:
        przyciete = przytnij_notowania(pobierz(YAHOO_WYKRES.format(ticker=urllib.parse.quote(ticker))))
        plik = nazwa_pliku("quote", ticker)
        rozmiar = zapisz_json(katalog / plik, przyciete)
        r = przyciete["chart"]["result"][0]
        ts = r["timestamp"]
        spis["notowania"][ticker] = {
            "plik": plik, "punktow": len(ts), "rozmiar_kb": round(rozmiar / 1024),
            "od": datetime.fromtimestamp(ts[0], timezone.utc).strftime("%Y-%m-%d"),
            "do": datetime.fromtimestamp(ts[-1], timezone.utc).strftime("%Y-%m-%d"),
        }
    for symbol in LANCUCHY:
        przyciety = przytnij_lancuch(pobierz(CBOE_LANCUCH.format(symbol=symbol)))
        plik = nazwa_pliku("options", symbol)
        rozmiar = zapisz_json(katalog / plik, przyciety)
        spis["lancuchy"][symbol] = {
            "plik": plik, "opcji": len(przyciety["data"]["options"]), "rozmiar_kb": round(rozmiar / 1024),
            "timestamp": przyciety["timestamp"], "cena": przyciety["data"].get("current_price"),
        }
    zapisz_json(katalog / "indeks.json", spis)
    return spis


def main(argv: list[str]) -> int:
    katalog = Path(argv[1]).resolve() if len(argv) > 1 else DOMYSLNY_KATALOG
    try:
        spis = pobierz_i_zapisz(katalog)
    except (RuntimeError, OSError, ValueError) as blad:
        print(f"BŁĄD: {blad}", file=sys.stderr)
        return 1
    for ticker, w in spis["notowania"].items():
        print(f"quote  {ticker:6s} {w['punktow']:5d} punktów {w['od']} .. {w['do']}  {w['rozmiar_kb']} KB")
    for symbol, w in spis["lancuchy"].items():
        print(f"opcje  {symbol:6s} {w['opcji']:5d} opcji, cena {w['cena']}, stan z {w['timestamp']}  {w['rozmiar_kb']} KB")
    print(f"zapisano w {katalog} (pobrano {spis['pobrano']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
