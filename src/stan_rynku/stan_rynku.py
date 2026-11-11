"""Karta „Stan rynku" (zadanie 037): statystyczny stan rynku USA z punktu widzenia inwestora
indeksowego S&P 500, w trzech grupach wskaźników (makro, rynek, technika), z jednym sygnałem
rynku, indeksem nastrojów, historią sygnału i sprawdzeniem jego skuteczności na danych od 2008 r.

Wzorzec jednoplikowy (CLAUDE.md, „Karty: wzorzec jednoplikowy"): cały kod karty mieszka
w tym pliku. Inaczej niż na kartach liczonych w przeglądarce, tutaj rachunek robi Python raz
dziennie (w pełnej platformie jako workflow GitHub Actions), a przeglądarka tylko czyta
gotowe `data/stan-rynku/stan.json` i pisany przez rutynę Claude `data/stan-rynku/ocena.json`.

Okna stoją w przestrzeni roboczej (zadanie 041): użytkownik łączy kilka elementów w jednym
oknie jako zakładki, dodaje i zamyka okna, zmienia ich rozmiar i kolejność (wspólny moduł
web/shared/przestrzen.js; w wersji pokazowej układ zapamiętuje tylko przeglądarka).

Polecenia (z korzenia repozytorium):
  python src/stan_rynku/stan_rynku.py              generuje index.html i app.js
  python src/stan_rynku/stan_rynku.py aktualizuj   pobiera dane, liczy wskaźniki, zapisuje data/stan-rynku/
  python src/stan_rynku/stan_rynku.py sprawdz      sprawdza data/stan-rynku/ocena.json (pisze ją rutyna Claude)

Źródła danych (bez płatnych usług):
  - FRED (Fed z St. Louis): makro, stopy, spready. Klucz API ze zmiennej FRED_API_KEY (sekret
    repozytorium); bez klucza skrypt bierze te same serie z publicznych plików CSV FRED.
  - Cboe: dzienne statystyki opcji (put/call całej giełdy, archiwum od 7.10.2019 w
    data/stan-rynku/cboe-putcall.json), historia VIX i łańcuch opcji SPX (gamma, skośność, otwarte pozycje).
  - Yahoo Finance przez własne proxy, np. Cloudflare Worker (trasa /quote; adres w zmiennej PROXY_URL,
    proxy nie jest częścią wersji pokazowej): S&P 500, VIX3M, MOVE, ETF-y.
  - VaR: funkcja oblicz_var_kroczaco() z src/var/var.py (kod karty VaR, której strony nie ma w wersji
    pokazowej), parametry domyślne: SPY, 99%, okna 756 sesji, horyzonty 1 i 21 sesji.

Progi i wagi to pierwsza kalibracja opisana w specyfikacji
projekty/037-nowa-karta-stan-rynku/pliki/specyfikacja-stan-rynku.md: zmieniaj je razem z nią.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[2]
KATALOG = KORZEN / "web" / "stan-rynku"      # strona karty
DANE = KORZEN / "data" / "stan-rynku"
SCIEZKA_STAN = DANE / "stan.json"
SCIEZKA_PUTCALL = DANE / "cboe-putcall.json"
SCIEZKA_OPCJE = DANE / "opcje-spx.json"
SCIEZKA_OCENA = DANE / "ocena.json"
SCIEZKA_HTML = KATALOG / "index.html"
SCIEZKA_JS = KATALOG / "app.js"
SCIEZKA_VAR = KORZEN / "src" / "var" / "var.py"

# Własne proxy do Yahoo Finance (np. Cloudflare Worker z trasami /quote, /cboe-statystyki i /options). Nie jest częścią
# wersji pokazowej, więc adres podaje się w zmiennej środowiskowej PROXY_URL. Bez niego `aktualizuj` się nie uruchomi
# (Yahoo nie odpowiada wprost), a Cboe i FRED działają bez proxy.
WORKER_URL = os.environ.get("PROXY_URL", "").rstrip("/")
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
CBOE_STATYSTYKI = "https://cdn.cboe.com/data/us/options/market_statistics/daily"
CBOE_VIX_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
CBOE_OPCJE = "https://cdn.cboe.com/api/global/delayed_quotes/options"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# FRED (API i pliki CSV) wstrzymuje odpowiedź, gdy nagłówek udaje przeglądarkę, a połączenie
# jej nie przypomina (sprawdzone 1.11.2026: zapytanie z UA „Mozilla/5.0" wisiało do limitu
# czasu, a z uczciwym opisem programu wraca w 0,1 s), więc do FRED idzie osobny nagłówek.
UA_FRED = "platforma_inwestycyjna stan-rynku/1.0 (github.com/kobimpw/platforma_inwestycyjna)"

# Pierwszy dzień, za który Cboe publikuje dzienne statystyki opcji w formacie JSON.
PUTCALL_OD = date(2019, 10, 7)
# Wagi grup w sygnale (suma 1). Makro zmienia się wolno i z opóźnieniem, więc waży mniej.
WAGI_GRUP = {"makro": 0.30, "rynek": 0.35, "technika": 0.35}
NAZWY_GRUP = {"makro": "Makro", "rynek": "Rynek", "technika": "Technika"}
# Poziomy sygnału: (dolna granica wyniku, klucz, etykieta). Wynik od -100 do +100.
POZIOMY = [
    (40, "silnie-pozytywny", "Silnie pozytywny"),
    (15, "pozytywny", "Pozytywny"),
    (-15, "neutralny", "Neutralny"),
    (-40, "negatywny", "Negatywny"),
    (-1000, "silnie-negatywny", "Silnie negatywny"),
]
# Indeks nastrojów 0-100 (strach -> chciwość).
POZIOMY_NASTROJOW = [
    (75, "skrajna-chciwosc", "Skrajna chciwość"),
    (55, "chciwosc", "Chciwość"),
    (45, "neutralnie", "Neutralnie"),
    (25, "strach", "Strach"),
    (-1, "skrajny-strach", "Skrajny strach"),
]
LAT_HISTORII_DZIENNEJ = 3
LAT_HISTORII_WSKAZNIKA = 3


# ===========================================================================
# magazyn funkcji
# ===========================================================================
# Wszystkie zwykłe funkcje pomocnicze: pobieranie, formatowanie, wskaźniki techniczne,
# analiza łańcucha opcji, punktacja i sygnał. pandas i numpy importują się dopiero w
# funkcjach liczących, żeby samo generowanie strony (`python stan_rynku.py`) ich nie wymagało.


# ---------------------------------------------------------------------------
# Pobieranie (sieć)
# ---------------------------------------------------------------------------
def _bez_klucza(tekst: str) -> str:
    """Usuwa klucz FRED z komunikatów błędów (adresy zapytań API go zawierają)."""
    klucz = os.environ.get("FRED_API_KEY", "").strip()
    return tekst.replace(klucz, "***") if klucz else tekst


def pobierz_bajty(url: str, timeout: int = 60, proby: int = 3, ua: str = UA) -> bytes:
    """GET z kilkoma próbami; 403 i 404 nie są ponawiane (Cboe odpowiada 403 na dzień bez sesji)."""
    ostatni: Exception | None = None
    for proba in range(proby):
        try:
            zapytanie = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urllib.request.urlopen(zapytanie, timeout=timeout) as odp:
                return odp.read()
        except urllib.error.HTTPError as blad:
            if blad.code in (403, 404):
                raise
            ostatni = blad
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as blad:
            ostatni = blad
        time.sleep(1.5 * (proba + 1))
    raise RuntimeError(_bez_klucza(f"{url.split('?')[0]}: {ostatni}"))


def pobierz_fred(seria: str, od: str = "2000-01-01"):
    """Seria FRED jako pandas.Series (indeks: data obserwacji). Zwraca (seria, sposób).

    Najpierw API z kluczem (FRED_API_KEY), a bez klucza albo przy błędzie publiczny plik
    CSV FRED (te same dane, bez klucza). Brakujące wartości (święta) są pomijane.
    """
    import pandas as pd

    klucz = os.environ.get("FRED_API_KEY", "").strip()
    if klucz:
        try:
            url = f"{FRED_API}?series_id={seria}&api_key={klucz}&file_type=json&observation_start={od}"
            obserwacje = json.loads(pobierz_bajty(url, timeout=30, proby=2, ua=UA_FRED))["observations"]
            s = pd.Series({o["date"]: o["value"] for o in obserwacje}, dtype=object)
            return _seria_liczb(s), "API"
        except Exception as blad:  # noqa: BLE001 (każdy błąd API kończy się próbą CSV)
            print(f"  FRED API {seria}: {_bez_klucza(str(blad))}; próbuję pliku CSV", file=sys.stderr)
    tekst = pobierz_bajty(f"{FRED_CSV}?id={seria}&cosd={od}", timeout=30, proby=2, ua=UA_FRED).decode("utf-8")
    wiersze = list(csv.reader(io.StringIO(tekst)))[1:]
    s = pd.Series({w[0]: w[1] for w in wiersze if len(w) >= 2}, dtype=object)
    return _seria_liczb(s), "CSV"


def _seria_liczb(s):
    import pandas as pd

    s = s.replace({".": None, "": None})
    wynik = pd.to_numeric(s, errors="coerce").dropna().astype(float)
    wynik.index = pd.to_datetime(wynik.index)
    return wynik.sort_index()


def pobierz_yahoo(ticker: str, zakres: str = "30y"):
    """Dzienne notowania z Yahoo Finance przez Worker: DataFrame [open, high, low, close, adjclose].

    `close` to cena surowa (tak jak na karcie VaR), `adjclose` skorygowana o dywidendy (do
    porównań ETF-ów). Zakres liczbowy, nie „max": przy „max" Yahoo oddaje świece miesięczne.
    """
    import pandas as pd

    if not WORKER_URL:
        raise RuntimeError("brak adresu proxy do Yahoo Finance: ustaw zmienną środowiskową PROXY_URL")
    url = f"{WORKER_URL}/quote?ticker={urllib.parse.quote(ticker)}&range={zakres}&interval=1d"
    dane = json.loads(pobierz_bajty(url, timeout=120))
    wynik = (dane.get("chart") or {}).get("result") or []
    if not wynik or not wynik[0].get("timestamp"):
        raise RuntimeError(f"Yahoo {ticker}: {(dane.get('chart') or {}).get('error')}")
    r = wynik[0]
    q = r["indicators"]["quote"][0]
    adj = ((r["indicators"].get("adjclose") or [{}])[0] or {}).get("adjclose")
    indeks = pd.to_datetime(r["timestamp"], unit="s").normalize()
    df = pd.DataFrame(
        {"open": q.get("open"), "high": q.get("high"), "low": q.get("low"), "close": q.get("close"),
         "adjclose": adj if adj else q.get("close")},
        index=indeks,
    ).astype(float)
    df = df.dropna(subset=["close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for kol in ["open", "high", "low"]:
        df[kol] = df[kol].fillna(df["close"])
    df["adjclose"] = df["adjclose"].fillna(df["close"])
    return df


def pobierz_vix():
    """Historia VIX od 1990 z Cboe (oficjalny plik CSV); zapasowo Yahoo ^VIX."""
    import pandas as pd

    try:
        tekst = pobierz_bajty(CBOE_VIX_CSV, timeout=90).decode("utf-8")
        df = pd.read_csv(io.StringIO(tekst))
        s = pd.Series(df["CLOSE"].astype(float).to_numpy(), index=pd.to_datetime(df["DATE"], format="%m/%d/%Y"))
        return s[~s.index.duplicated(keep="last")].sort_index(), "Cboe (VIX_History.csv)"
    except Exception as blad:  # noqa: BLE001
        print(f"  VIX z Cboe: {blad}; biorę Yahoo ^VIX", file=sys.stderr)
        return pobierz_yahoo("^VIX")["close"], "Yahoo ^VIX"


def pobierz_statystyki_cboe(dzien: date) -> dict | None:
    """Dzienne statystyki opcji Cboe za dany dzień (put/call ratio i wolumeny) albo None.

    Cboe odpowiada 403, gdy dnia nie ma (weekend, święto, jeszcze nieopublikowany), więc
    przy błędzie bezpośredniego zapytania próbujemy jeszcze przez Worker (trasa
    /cboe-statystyki), na wypadek blokady adresów serwerów GitHub Actions.
    """
    adresy = [f"{CBOE_STATYSTYKI}/{dzien.isoformat()}_daily_options"]
    if WORKER_URL:
        adresy.append(f"{WORKER_URL}/cboe-statystyki?data={dzien.isoformat()}")
    for url in adresy:
        try:
            dane = json.loads(pobierz_bajty(url, timeout=30, proby=2))
            if isinstance(dane, dict) and dane.get("ratios"):
                return dane
        except Exception:  # noqa: BLE001 (brak dnia albo blokada: próbujemy następnego adresu)
            continue
    return None


def wiersz_putcall(dzien: date, dane: dict) -> list:
    """Jeden wiersz archiwum put/call z dziennych statystyk Cboe."""

    def liczba(t):
        try:
            return float(t)
        except (TypeError, ValueError):
            return None

    ratio = {r.get("name"): liczba(r.get("value")) for r in dane.get("ratios", [])}

    def wolumen(klucz, strona):
        for w in dane.get(klucz) or []:
            if w.get("name") == "VOLUME":
                return int(w.get(strona) or 0)
        return None

    return [
        dzien.isoformat(),
        ratio.get("TOTAL PUT/CALL RATIO"),
        ratio.get("INDEX PUT/CALL RATIO"),
        ratio.get("EXCHANGE TRADED PRODUCTS PUT/CALL RATIO"),
        ratio.get("EQUITY PUT/CALL RATIO"),
        ratio.get("SPX + SPXW PUT/CALL RATIO"),
        wolumen("EQUITY OPTIONS", "call"),
        wolumen("EQUITY OPTIONS", "put"),
        wolumen("INDEX OPTIONS", "call"),
        wolumen("INDEX OPTIONS", "put"),
    ]


KOLUMNY_PUTCALL = ["data", "calkowity", "indeksy", "etp", "akcje", "spx", "akcjeCall", "akcjePut", "indeksyCall", "indeksyPut"]


def aktualizuj_archiwum_putcall(dzis: date) -> dict:
    """Dopisuje do data/stan-rynku/cboe-putcall.json brakujące dni (od ostatniego zapisanego do dziś).

    Pierwsze uruchomienie pobiera całość od 7.10.2019 (ok. 1800 plików, równolegle); kolejne
    tylko nowe dni robocze. Dni bez sesji Cboe pomija (odpowiedź 403).
    """
    archiwum = {"kolumny": KOLUMNY_PUTCALL, "wiersze": []}
    if SCIEZKA_PUTCALL.exists():
        archiwum = json.loads(SCIEZKA_PUTCALL.read_text(encoding="utf-8"))
    znane = {w[0] for w in archiwum["wiersze"]}
    start = PUTCALL_OD
    if archiwum["wiersze"]:
        start = date.fromisoformat(max(znane)) + timedelta(days=1)
    dni = []
    d = start
    while d <= dzis:
        if d.weekday() < 5 and d.isoformat() not in znane:
            dni.append(d)
        d += timedelta(days=1)
    nowe = []
    if dni:
        with ThreadPoolExecutor(max_workers=8 if len(dni) > 20 else 2) as pula:
            for dzien, dane in zip(dni, pula.map(pobierz_statystyki_cboe, dni)):
                if dane:
                    nowe.append(wiersz_putcall(dzien, dane))
    archiwum["wiersze"] = sorted(archiwum["wiersze"] + nowe, key=lambda w: w[0])
    archiwum["kolumny"] = KOLUMNY_PUTCALL
    archiwum["zrodlo"] = "Cboe, dzienne statystyki opcji (cdn.cboe.com/data/us/options/market_statistics/daily)"
    archiwum["zaktualizowano"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    SCIEZKA_PUTCALL.write_text(_json_zwarty(archiwum), encoding="utf-8")
    print(f"  put/call Cboe: {len(nowe)} nowych dni, razem {len(archiwum['wiersze'])}")
    return archiwum


def pobierz_lancuch(symbol: str = "_SPX") -> dict:
    """Łańcuch opcji z Cboe (notowania z opóźnieniem): najpierw wprost, zapasowo przez Worker."""
    ostatni: Exception | None = None
    adresy = [f"{CBOE_OPCJE}/{symbol}.json"] + ([f"{WORKER_URL}/options?symbol={symbol}"] if WORKER_URL else [])
    for url in adresy:
        try:
            return json.loads(pobierz_bajty(url, timeout=180))
        except Exception as blad:  # noqa: BLE001
            ostatni = blad
    raise RuntimeError(f"łańcuch {symbol}: {ostatni}")


def zaladuj_var():
    """Moduł karty VaR (src/var/var.py): ta sama metoda liczenia VaR co na karcie."""
    spec = importlib.util.spec_from_file_location("karta_var", SCIEZKA_VAR)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# ---------------------------------------------------------------------------
# Formatowanie liczb i dat po polsku (teksty trafiają do karty gotowe)
# ---------------------------------------------------------------------------
NBSP = " "
MIESIACE = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]


def _skonczona(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(float(v))


def pl(v, miejsca: int = 1) -> str:
    """Liczba po polsku: przecinek dziesiętny, spacja tysięcy od 10 000 (jak pl-PL)."""
    if not _skonczona(v):
        return "–"
    v = float(v)
    if round(v, miejsca) == 0:
        v = 0.0
    tekst = f"{abs(v):.{miejsca}f}"
    calk, _, ulamek = tekst.partition(".")
    if len(calk) >= 5:
        grupy = []
        while calk:
            grupy.insert(0, calk[-3:])
            calk = calk[:-3]
        calk = NBSP.join(grupy)
    return ("-" if v < 0 else "") + calk + ("," + ulamek if ulamek else "")


def plz(v, miejsca: int = 1) -> str:
    """Jak pl(), ze znakiem plus przy wartościach dodatnich."""
    if not _skonczona(v):
        return "–"
    return ("+" if round(float(v), miejsca) > 0 else "") + pl(v, miejsca)


def data_pl(t) -> str:
    return f"{t.day:02d}.{t.month:02d}.{t.year}"


def okres_pl(t, czestotliwosc: str) -> str:
    """Opis okresu obserwacji: dzień, tydzień, miesiąc albo kwartał."""
    if czestotliwosc == "kwartalna":
        return f"{['I', 'II', 'III', 'IV'][(t.month - 1) // 3]} kw. {t.year}"
    if czestotliwosc == "miesięczna":
        return f"{MIESIACE[t.month - 1]} {t.year}"
    if czestotliwosc == "tygodniowa":
        return f"tydz. do {data_pl(t)}"
    return data_pl(t)


def _json_zwarty(obiekt) -> str:
    return json.dumps(obiekt, ensure_ascii=False, separators=(",", ":")) + "\n"


# ---------------------------------------------------------------------------
# Szeregi czasowe: punkt w czasie, percentyle, progi
# ---------------------------------------------------------------------------
# Opóźnienie publikacji (dni od daty obserwacji), żeby historia sygnału nie korzystała z
# danych, których w danym dniu jeszcze nie znano. Dane miesięczne FRED mają datę 1. dnia
# miesiąca, kwartalne 1. dnia kwartału, tygodniowe ostatniego dnia tygodnia.
OPOZNIENIA = {
    "A191RL1Q225SBEA": 120, "GDPNOW": 120, "UNRATE": 35, "SAHMREALTIME": 35, "IC4WSA": 5,
    "CCSA": 12, "PAYEMS": 35, "CPIAUCSL": 45, "PCEPILFE": 60, "CFNAIMA3": 55, "UMCSENT": 30,
    "NFCI": 5, "WALCL": 1,
}


def na_sesje(seria, sesje, opoznienie: int = 1):
    """Seria o dowolnej częstotliwości -> wartość znana na koniec każdej sesji S&P 500.

    Każda obserwacja „pojawia się" `opoznienie` dni po swojej dacie i obowiązuje do
    następnej. Ostatnia obserwacja pojawia się najpóźniej w ostatniej sesji (nowcasty jak
    GDPNow są znane od razu, choć ich kwartał jeszcze trwa).
    """
    import pandas as pd

    s = seria.dropna()
    if s.empty:
        return pd.Series(float("nan"), index=sesje)
    dostepna = s.index + pd.Timedelta(days=opoznienie)
    dostepna = dostepna.where(dostepna <= sesje[-1], sesje[-1])
    s = pd.Series(s.to_numpy(), index=dostepna)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(sesje.union(s.index)).ffill().reindex(sesje)


def percentyl_kroczacy(seria, okno: int, min_okres: int | None = None):
    """Percentyl (0-100) bieżącej wartości wśród `okno` ostatnich obserwacji."""
    return seria.rolling(okno, min_periods=min_okres or max(20, okno // 2)).rank(pct=True) * 100


def percentyl_ostatniej(seria, lat: float) -> float | None:
    """Percentyl ostatniej wartości serii (natywnej częstotliwości) w ostatnich `lat` latach."""
    import pandas as pd

    s = seria.dropna()
    if len(s) < 8:
        return None
    s = s[s.index >= s.index[-1] - pd.DateOffset(days=int(lat * 365.25))]
    return float((s <= s.iloc[-1]).mean() * 100)


def progi(seria, granice: list[float], punkty: list[int]):
    """Punkty według przedziałów: wartość poniżej granice[0] -> punkty[0], od granice[0] do
    granice[1] -> punkty[1] … od ostatniej granicy -> punkty[-1]. NaN zostaje NaN."""
    import numpy as np
    import pandas as pd

    wartosci = seria.to_numpy(dtype=float)
    idx = np.searchsorted(np.array(granice, dtype=float), wartosci, side="right")
    wynik = np.array(punkty, dtype=float)[np.clip(idx, 0, len(punkty) - 1)]
    wynik[np.isnan(wartosci)] = np.nan
    return pd.Series(wynik, index=seria.index)


def co_tydzien(seria, lat: int):
    """Ostatnie `lat` lat serii; dane dzienne przerzedzone do jednego punktu na tydzień."""
    import pandas as pd

    s = seria.dropna()
    if s.empty:
        return s
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=lat)]
    if len(s) > 400:
        ostatni = s.iloc[[-1]]
        s = s.resample("W-FRI").last().dropna()
        s = pd.concat([s[s.index < ostatni.index[0]], ostatni])
    return s


def lista_punktow(seria, miejsca: int = 4) -> list:
    return [[t.strftime("%Y-%m-%d"), round(float(v), miejsca)] for t, v in seria.dropna().items()]


# ---------------------------------------------------------------------------
# Wskaźniki techniczne (S&P 500, notowania dzienne)
# ---------------------------------------------------------------------------
def sma(seria, n: int):
    return seria.rolling(n).mean()


def ema(seria, n: int):
    return seria.ewm(span=n, adjust=False).mean()


def srednia_wildera(seria, n: int):
    """Średnia Wildera (RMA): zasiew średnią z pierwszych n wartości, dalej (pop·(n-1)+x)/n.
    Ta sama metoda co na karcie analizy technicznej w pełnej platformie."""
    import numpy as np
    import pandas as pd

    wartosci = seria.to_numpy(dtype=float)
    wynik = np.full(len(wartosci), np.nan)
    start = 0
    while start < len(wartosci) and np.isnan(wartosci[start]):
        start += 1
    if start + n > len(wartosci):
        return pd.Series(wynik, index=seria.index)
    wynik[start + n - 1] = np.nanmean(wartosci[start:start + n])
    for i in range(start + n, len(wartosci)):
        x = wartosci[i] if not np.isnan(wartosci[i]) else 0.0
        wynik[i] = (wynik[i - 1] * (n - 1) + x) / n
    return pd.Series(wynik, index=seria.index)


def rsi_wildera(zamkniecia, n: int = 14):
    delta = zamkniecia.diff()
    zysk = srednia_wildera(delta.clip(lower=0), n)
    strata = srednia_wildera((-delta).clip(lower=0), n)
    rsi = 100 - 100 / (1 + zysk / strata)
    rsi[(strata == 0) & (zysk > 0)] = 100.0
    rsi[(strata == 0) & (zysk == 0)] = 50.0
    return rsi


def wstegi_bollingera(zamkniecia, n: int = 20, k: float = 2.0):
    """(środek, góra, dół, %B, szerokość w % środka); odchylenie populacyjne jak w TradingView."""
    srodek = sma(zamkniecia, n)
    odch = zamkniecia.rolling(n).std(ddof=0)
    gora, dol = srodek + k * odch, srodek - k * odch
    return srodek, gora, dol, (zamkniecia - dol) / (gora - dol), (gora - dol) / srodek * 100


def adx_wildera(gora, dol, zamkniecia, n: int = 14):
    """(ADX, +DI, -DI) według Wildera."""
    import numpy as np
    import pandas as pd

    ruch_gora = gora.diff()
    ruch_dol = -dol.diff()
    plus_dm = pd.Series(np.where((ruch_gora > ruch_dol) & (ruch_gora > 0), ruch_gora, 0.0), index=gora.index)
    minus_dm = pd.Series(np.where((ruch_dol > ruch_gora) & (ruch_dol > 0), ruch_dol, 0.0), index=gora.index)
    poprzednie = zamkniecia.shift(1)
    tr = pd.concat([gora - dol, (gora - poprzednie).abs(), (dol - poprzednie).abs()], axis=1).max(axis=1)
    for s in (plus_dm, minus_dm, tr):
        s.iloc[0] = np.nan
    atr = srednia_wildera(tr, n)
    plus_di = 100 * srednia_wildera(plus_dm, n) / atr
    minus_di = 100 * srednia_wildera(minus_dm, n) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return srednia_wildera(dx, n), plus_di, minus_di, atr


def macd(zamkniecia, szybka: int = 12, wolna: int = 26, sygnal: int = 9):
    linia = ema(zamkniecia, szybka) - ema(zamkniecia, wolna)
    syg = ema(linia, sygnal)
    return linia, syg, linia - syg


def zmiennosc_zrealizowana(zamkniecia, n: int = 21):
    """Roczna zmienność zrealizowana (%) z n dziennych zwrotów logarytmicznych."""
    import numpy as np

    zwroty = np.log(zamkniecia / zamkniecia.shift(1))
    return zwroty.rolling(n).std(ddof=1) * math.sqrt(252) * 100


# ---------------------------------------------------------------------------
# Łańcuch opcji SPX (Cboe): ekspozycja gamma, skośność, otwarte pozycje
# ---------------------------------------------------------------------------
RE_OPCJA = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def analizuj_lancuch(dane: dict) -> dict:
    """Liczby z pełnego łańcucha opcji SPX (ok. 20 tys. kontraktów, notowania z opóźnieniem).

    - GEX: suma gamma × otwarte kontrakty × 100 × S² × 1%, calle dodatnio, puty ujemnie
      (uproszczone założenie, że animatorzy rynku mają kupione calle i sprzedane puty; ta sama
      konwencja co wskaźnik 8 karty Pozycja). W mld USD na 1% ruchu indeksu.
    - Skośność 25 delta: IV puta z deltą ok. -0,25 minus IV calla z deltą ok. 0,25, termin
      najbliższy 30 dniom (co najmniej 7 dni), w punktach procentowych zmienności.
    - Put/call z otwartych pozycji w terminach do 60 dni.
    - IV przy cenie dla terminów ok. 30 i 90 dni.
    """
    d = dane["data"]
    S = float(d.get("current_price") or d.get("close") or 0)
    znacznik = str(dane.get("timestamp", ""))[:10]
    dzis = date.fromisoformat(znacznik) if znacznik else date.today()
    opcje = []
    for o in d.get("options", []):
        m = RE_OPCJA.match(o.get("option", ""))
        if not m:
            continue
        _, wyg, typ, k = m.groups()
        termin = date(2000 + int(wyg[:2]), int(wyg[2:4]), int(wyg[4:]))
        opcje.append({
            "dni": (termin - dzis).days, "typ": typ, "strike": int(k) / 1000,
            "iv": float(o.get("iv") or 0), "delta": float(o.get("delta") or 0), "gamma": float(o.get("gamma") or 0),
            "oi": float(o.get("open_interest") or 0), "bid": float(o.get("bid") or 0), "ask": float(o.get("ask") or 0),
        })
    if not opcje or S <= 0:
        raise RuntimeError("pusty łańcuch opcji")
    gex = sum((1 if o["typ"] == "C" else -1) * o["gamma"] * o["oi"] * 100 * S * S * 0.01 for o in opcje)

    def termin_blisko(cel: int, minimum: int):
        terminy = sorted({o["dni"] for o in opcje if o["dni"] >= minimum})
        return min(terminy, key=lambda x: abs(x - cel)) if terminy else None

    def iv_przy_cenie(dni: int):
        calle = {o["strike"]: o for o in opcje if o["dni"] == dni and o["typ"] == "C" and o["iv"] > 0 and o["bid"] > 0}
        puty = {o["strike"]: o for o in opcje if o["dni"] == dni and o["typ"] == "P" and o["iv"] > 0 and o["bid"] > 0}
        wspolne = [k for k in calle if k in puty]
        if not wspolne:
            return None
        k = min(wspolne, key=lambda x: abs(x - S))
        return (calle[k]["iv"] + puty[k]["iv"]) / 2

    t30 = termin_blisko(30, 7)
    skos = None
    if t30 is not None:
        kw = [o for o in opcje if o["dni"] == t30 and o["iv"] > 0 and o["bid"] > 0]
        puty = [o for o in kw if o["typ"] == "P" and -0.5 < o["delta"] < -0.05]
        calle = [o for o in kw if o["typ"] == "C" and 0.05 < o["delta"] < 0.5]
        if puty and calle:
            p25 = min(puty, key=lambda o: abs(o["delta"] + 0.25))
            c25 = min(calle, key=lambda o: abs(o["delta"] - 0.25))
            skos = {"wartosc": (p25["iv"] - c25["iv"]) * 100, "put": p25["strike"], "call": c25["strike"],
                    "ivPut": p25["iv"] * 100, "ivCall": c25["iv"] * 100, "dni": t30}
    oi_p = sum(o["oi"] for o in opcje if o["typ"] == "P" and o["dni"] <= 60)
    oi_c = sum(o["oi"] for o in opcje if o["typ"] == "C" and o["dni"] <= 60)
    t90 = termin_blisko(90, 60)
    return {
        "data": znacznik, "S": S, "gex": gex / 1e9, "skos": skos,
        "pcOi": oi_p / oi_c if oi_c else None, "oiPut": oi_p, "oiCall": oi_c,
        "iv30": (iv_przy_cenie(t30) or 0) * 100 or None, "iv90": (iv_przy_cenie(t90) or 0) * 100 if t90 else None,
        "dni30": t30, "dni90": t90, "kontraktow": len(opcje),
    }


def aktualizuj_archiwum_opcji(analiza: dict | None, sesja: str) -> list:
    """Dopisuje dzienny odczyt z łańcucha SPX do data/stan-rynku/opcje-spx.json (historia do kalibracji)."""
    wiersze = json.loads(SCIEZKA_OPCJE.read_text(encoding="utf-8"))["wiersze"] if SCIEZKA_OPCJE.exists() else []
    if analiza:
        skos = (analiza.get("skos") or {}).get("wartosc")
        wiersz = [sesja, round(analiza["gex"], 3), round(skos, 2) if skos is not None else None,
                  round(analiza["pcOi"], 3) if analiza.get("pcOi") else None,
                  round(analiza["iv30"], 2) if analiza.get("iv30") else None,
                  round(analiza["iv90"], 2) if analiza.get("iv90") else None, round(analiza["S"], 2)]
        wiersze = [w for w in wiersze if w[0] != sesja] + [wiersz]
        wiersze.sort(key=lambda w: w[0])
        SCIEZKA_OPCJE.write_text(_json_zwarty({
            "kolumny": ["data", "gexMldUsd", "skos25d", "pcOi60", "iv30", "iv90", "spx"],
            "zrodlo": "Cboe, łańcuch opcji SPX (cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json)",
            "wiersze": wiersze,
        }), encoding="utf-8")
    return wiersze


# ---------------------------------------------------------------------------
# Definicje wskaźników: metadane (nazwa, waga, opis, reguła, źródło) i funkcje liczące
# ---------------------------------------------------------------------------
# Każda funkcja liczaca dostaje kontekst `k` (pobrane serie) i zwraca słownik:
#   seria   - wartość wskaźnika znana na koniec każdej sesji (pandas.Series),
#   punkty  - punkty oceny na każdą sesję (None dla wskaźników informacyjnych),
#   natywna - seria w naturalnej częstotliwości (do wykresiku i poprzedniej wartości),
#   tekst, pod, zmiana - gotowe napisy do karty, data - data ostatniej obserwacji.
def _fred_url(seria: str) -> dict:
    return {"nazwa": f"FRED {seria}", "url": f"https://fred.stlouisfed.org/series/{seria}"}


YAHOO_URL = "https://finance.yahoo.com/quote/{}"
ZRODLO_CBOE_PC = {"nazwa": "Cboe, dzienne statystyki opcji", "url": "https://www.cboe.com/markets/us/options/market-statistics/daily"}
ZRODLO_CBOE_SPX = {"nazwa": "Cboe, łańcuch opcji SPX", "url": "https://www.cboe.com/delayed_quotes/spx/quote_table"}
ZRODLO_VAR = {"nazwa": "Rachunek VaR (SPY, notowania Yahoo)", "url": YAHOO_URL.format("SPY")}


def _yahoo_zrodlo(ticker: str, nazwa: str | None = None) -> dict:
    return {"nazwa": nazwa or f"Yahoo {ticker}", "url": YAHOO_URL.format(urllib.parse.quote(ticker))}


DEFINICJE: list[dict] = [
    # ----------------------------------------------------------------- MAKRO
    {"id": "pkb", "grupa": "makro", "nazwa": "PKB USA (ostatni kwartał)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "kwartalna", "zrodlo": _fred_url("A191RL1Q225SBEA"),
     "opis": "Tempo wzrostu realnego PKB USA w ostatnim opublikowanym kwartale, przeliczone na skalę roku (tak podaje je urząd BEA). PKB to wartość wszystkiego, co wytworzyła gospodarka, więc jego wzrost oznacza rosnące przychody firm i zyski spółek z indeksu. Odczyt pojawia się około miesiąca po końcu kwartału, więc opisuje przeszłość.",
     "regula": "od 3%: +2; od 2 do 3%: +1; od 1 do 2%: 0; od 0 do 1%: -1; poniżej 0: -2"},
    {"id": "gdpnow", "grupa": "makro", "nazwa": "GDPNow (bieżący kwartał)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "kwartalna", "zrodlo": _fred_url("GDPNOW"),
     "opis": "Szacunek wzrostu PKB w trwającym kwartale (w skali roku), liczony na bieżąco przez Fed z Atlanty z napływających danych o sprzedaży, produkcji i handlu. Działa jak prognoza pogody dla gospodarki: nie czeka na oficjalny odczyt, więc wcześniej pokazuje zwolnienie albo przyspieszenie.",
     "regula": "od 3%: +2; od 2 do 3%: +1; od 1 do 2%: 0; od 0 do 1%: -1; poniżej 0: -2"},
    {"id": "bezrobocie", "grupa": "makro", "nazwa": "Stopa bezrobocia", "waga": 1.0, "maks": 2,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("UNRATE"),
     "opis": "Odsetek osób aktywnych zawodowo, które szukają pracy i jej nie mają (BLS, co miesiąc). Ocena patrzy na zmianę w ciągu roku, a nie na sam poziom: rosnące bezrobocie to pierwszy objaw słabnącej gospodarki i spadku wydatków konsumentów, które tworzą około dwóch trzecich PKB USA.",
     "regula": "zmiana r/r: poniżej -0,2 pkt proc.: +1; od -0,2 do +0,2: 0; od +0,2 do +0,5: -1; od +0,5: -2"},
    {"id": "sahm", "grupa": "makro", "nazwa": "Reguła Sahm (alarm recesji)", "waga": 1.5, "maks": 2,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("SAHMREALTIME"),
     "opis": "O ile trzymiesięczna średnia stopy bezrobocia wzrosła ponad swoje minimum z poprzednich 12 miesięcy (wskaźnik Claudii Sahm). Wzrost o 0,5 pkt proc. w przeszłości towarzyszył początkom recesji w USA, choć w 2024 r. reguła zadziałała bez recesji, więc traktuj ją jako alarm, a nie wyrok.",
     "regula": "poniżej 0,2: +1; od 0,2 do 0,35: 0; od 0,35 do 0,5: -1; od 0,5: -2"},
    {"id": "wnioski", "grupa": "makro", "nazwa": "Wnioski o zasiłek (średnia 4 tyg.)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "tygodniowa", "zrodlo": _fred_url("IC4WSA"),
     "opis": "Nowe wnioski o zasiłek dla bezrobotnych w tygodniu, uśrednione z 4 tygodni, żeby wygładzić szum. To najszybszy, cotygodniowy sygnał z rynku pracy: gdy firmy zaczynają zwalniać, wnioski rosną, zanim zmieni się miesięczna stopa bezrobocia. Ocena porównuje poziom z tym sprzed roku.",
     "regula": "zmiana r/r: poniżej -5%: +1; od -5 do +10%: 0; od +10 do +20%: -1; od +20%: -2"},
    {"id": "zatrudnienie", "grupa": "makro", "nazwa": "Nowe etaty (NFP, średnia 3 mies.)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("PAYEMS"),
     "opis": "Ile miejsc pracy poza rolnictwem przybywa co miesiąc (raport BLS z pierwszego piątku miesiąca), średnio z ostatnich trzech miesięcy. Więcej etatów to większe dochody i wydatki gospodarstw domowych. Przy mniejszej imigracji gospodarce wystarcza mniejszy przyrost niż dawniej, więc progi są wstępne.",
     "regula": "od 150 tys.: +1; od 50 do 150 tys.: 0; od 0 do 50 tys.: -1; poniżej 0: -2"},
    {"id": "cpi", "grupa": "makro", "nazwa": "Inflacja CPI r/r", "waga": 1.0, "maks": 2,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("CPIAUCSL"),
     "opis": "Zmiana cen koszyka konsumenta w ciągu roku (BLS). Wysoka inflacja zmusza Fed do trzymania wysokich stóp, a wyższa stopa obniża dzisiejszą wartość przyszłych zysków spółek, czyli ich wyceny. Inflacja blisko celu 2% daje bankowi centralnemu swobodę obniżek.",
     "regula": "poniżej 2,5%: +1; od 2,5 do 3,5%: 0; od 3,5 do 5%: -1; od 5%: -2"},
    {"id": "pce", "grupa": "makro", "nazwa": "Inflacja bazowa PCE r/r", "waga": 0, "maks": 0,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("PCEPILFE"),
     "opis": "Miara inflacji, na którą patrzy Fed przy decyzjach o stopach: ceny wydatków konsumpcyjnych bez żywności i energii (BEA), rok do roku. „Bazowa” znaczy bez najbardziej zmiennych składników, więc lepiej pokazuje trwały trend cen; cel Fed to 2%. Bez oceny: w danych od 2000 r. nie odróżniała lepszych i gorszych kwartałów S&P 500, a inflację w ocenie reprezentuje CPI."},
    {"id": "fed", "grupa": "makro", "nazwa": "Stopa Fed (kierunek 6 mies.)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("DFEDTARU"),
     "opis": "Przedział docelowy stopy funduszy federalnych, czyli podstawowej stopy procentowej w USA, i jej zmiana w ciągu 6 miesięcy. Obniżki tanią kredyt, podwyżki go drożą. Bez oceny, bo kierunek stóp działa w obie strony: obniżki w kryzysie (2008, 2020) były reakcją na złe wieści i po nich przychodziły głębsze spadki niż po podwyżkach; stopy procentowe w ocenie reprezentuje rentowność 10-letnia."},
    {"id": "rentownosc10", "grupa": "makro", "nazwa": "Rentowność obligacji 10-letnich", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("DGS10"),
     "opis": "Oprocentowanie 10-letnich obligacji skarbu USA: punkt odniesienia dla kredytów hipotecznych i dla wyceny akcji, bo z nim inwestorzy porównują zyski spółek. Szybki wzrost w ciągu 3 miesięcy albo poziom od 4,75% to presja na wyceny, zwłaszcza drogich spółek technologicznych. Wskaźnik tylko ostrzega: spadek rentowności nie dostaje plusa, bo w kryzysach jest ucieczką do bezpiecznych obligacji.",
     "regula": "zmiana 3 mies. od +0,75 pkt proc.: -2; od +0,4 pkt proc. albo poziom od 4,75%: -1; w pozostałych przypadkach 0"},
    {"id": "krzywa", "grupa": "makro", "nazwa": "Krzywa rentowności 10 lat minus 3 mies.", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("T10Y3M"),
     "opis": "Różnica oprocentowania obligacji 10-letnich i 3-miesięcznych. Normalnie dłuższa pożyczka jest droższa (różnica dodatnia); odwrócona krzywa (ujemna) znaczy, że rynek spodziewa się obniżek stóp z powodu spowolnienia, i poprzedzała recesje z wyprzedzeniem od kilku miesięcy do dwóch lat. Bez oceny, bo w horyzoncie 1–3 miesięcy akcje przy odwróconej krzywej zwykle rosły (2006–2007, 2019, 2023–2024); to tło dla oceny ryzyka recesji, a nie sygnał na najbliższe tygodnie."},
    {"id": "cfnai", "grupa": "makro", "nazwa": "Aktywność gospodarcza (CFNAI, 3 mies.)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("CFNAIMA3"),
     "opis": "Indeks Fed z Chicago zbudowany z 85 miesięcznych danych o produkcji, zatrudnieniu, konsumpcji i sprzedaży. Zero oznacza wzrost w tempie historycznej średniej; średnia z 3 miesięcy poniżej -0,7 w przeszłości zwykle oznaczała recesję.",
     "regula": "od +0,2: +1; od -0,35 do +0,2: 0; od -0,7 do -0,35: -1; poniżej -0,7: -2"},
    {"id": "krzywa2", "grupa": "makro", "nazwa": "Krzywa 10 lat minus 2 lata", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("T10Y2Y"),
     "opis": "Druga popularna miara nachylenia krzywej rentowności. Obligacje 2-letnie silnie reagują na oczekiwania wobec Fed, więc różnica 10 lat minus 2 lata pokazuje, czy rynek widzi długi okres wysokich stóp (spłaszczenie) czy ich obniżki (stromienie). Informacyjnie, bez oceny, bo ocenę dostaje krzywa 10 lat minus 3 mies."},
    {"id": "rentownosc2", "grupa": "makro", "nazwa": "Rentowność obligacji 2-letnich", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("DGS2"),
     "opis": "Oprocentowanie 2-letnich obligacji USA, bardzo wrażliwe na oczekiwane decyzje Fed. Rentowność wyraźnie poniżej stopy Fed znaczy, że rynek liczy na obniżki; powyżej, że spodziewa się podwyżek."},
    {"id": "realna10", "grupa": "makro", "nazwa": "Realna rentowność 10 lat (TIPS)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("DFII10"),
     "opis": "Oprocentowanie obligacji indeksowanych inflacją, czyli zysk ponad inflację. Wysoka realna rentowność czyni bezpieczne obligacje konkurencyjnymi wobec akcji i zwykle ciąży wycenom spółek wzrostowych."},
    {"id": "oczekiwania", "grupa": "makro", "nazwa": "Oczekiwania inflacyjne 10 lat", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("T10YIE"),
     "opis": "Inflacja, jaką na najbliższe 10 lat wyceniają inwestorzy (różnica rentowności zwykłych obligacji i obligacji indeksowanych inflacją). Stabilne oczekiwania blisko 2–2,5% oznaczają, że rynek wierzy w cel Fed."},
    {"id": "wnioski_kont", "grupa": "makro", "nazwa": "Wnioski kontynuowane", "waga": 0, "maks": 0,
     "czestotliwosc": "tygodniowa", "zrodlo": _fred_url("CCSA"),
     "opis": "Liczba osób, które nadal pobierają zasiłek. Rośnie, gdy zwolnionym trudniej znaleźć nową pracę, więc dopełnia obraz z nowych wniosków."},
    {"id": "konsumenci", "grupa": "makro", "nazwa": "Nastroje konsumentów (U. Michigan)", "waga": 0, "maks": 0,
     "czestotliwosc": "miesięczna", "zrodlo": _fred_url("UMCSENT"),
     "opis": "Ankieta Uniwersytetu Michigan o nastrojach gospodarstw domowych. Bez oceny, bo jako sygnał dla akcji działa raczej przekornie: najgorsze nastroje zdarzały się blisko dołków rynku."},
    {"id": "bilans_fed", "grupa": "makro", "nazwa": "Bilans Fed (zmiana 3 mies.)", "waga": 0, "maks": 0,
     "czestotliwosc": "tygodniowa", "zrodlo": _fred_url("WALCL"),
     "opis": "Suma aktywów Rezerwy Federalnej. Rosnący bilans (skup obligacji) dodaje płynności rynkom, malejący (zacieśnianie ilościowe) ją wycofuje."},
    # ----------------------------------------------------------------- RYNEK
    {"id": "pc_akcje", "grupa": "rynek", "nazwa": "Put/call akcji (Cboe, 10 sesji)", "waga": 1.0, "maks": 1,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_CBOE_PC,
     "opis": "Stosunek wolumenu opcji sprzedaży (put, zabezpieczenie przed spadkiem) do opcji kupna (call, zakład na wzrost) na akcjach spółek, z dziennych statystyk giełdy Cboe, średnio z 10 sesji. Podręcznikowo działa przekornie (masowy strach bywa dnem), ale w danych Cboe z lat 2020–2026 górny decyl roku poprzedzał słabsze wyniki i głębsze spadki S&P 500 w kolejnych 2–12 tygodniach, bo trwały wysoki popyt na zabezpieczenia towarzyszył bessie 2022 r. Dlatego ocena traktuje go jako ostrzeżenie, a beztroska (dolny decyl) nie dostaje punktów.",
     "regula": "percentyl z roku od 90: -1 (rynek się masowo zabezpiecza); poniżej 90: 0"},
    {"id": "vix_percentyl", "grupa": "rynek", "nazwa": "Percentyl zmienności (VIX, 1 rok)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": {"nazwa": "Cboe, historia VIX", "url": "https://www.cboe.com/tradable_products/vix/vix_historical_data/"},
     "opis": "VIX to zmienność S&P 500 na najbliższe 30 dni wyceniana przez rynek opcji, w procentach w skali roku (tzw. indeks strachu). Percentyl mówi, jaka część sesji z ostatniego roku miała niższy VIX niż dziś, a IV rank pokazuje położenie między rocznym minimum a maksimum. Wysoki percentyl to rynek nerwowy i drogie zabezpieczenia.",
     "regula": "percentyl poniżej 25: +1; od 25 do 75: 0; od 75 do 90: -1; od 90: -2"},
    {"id": "premia_zmiennosci", "grupa": "rynek", "nazwa": "Premia za ryzyko (VIX minus realna zmienność)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": {"nazwa": "Cboe VIX i Yahoo ^GSPC", "url": "https://www.cboe.com/tradable_products/vix/"},
     "opis": "Różnica między zmiennością, jaką wyceniają opcje (VIX), a tą, którą S&P 500 faktycznie miał w ostatnich 21 sesjach. Zwykle jest dodatnia, bo kupujący zabezpieczenia płacą premię, jak za ubezpieczenie. Ujemna premia (rynek rusza się mocniej, niż wyceniano) to stan kryzysowy; bardzo wysoka premia po wyprzedaży to strach, za który rynek historycznie wynagradzał kupujących akcje.",
     "regula": "poniżej -2 pkt: -2; od -2 do 0: -1; od 0 do 6: 0; od 6: +1"},
    {"id": "struktura_vix", "grupa": "rynek", "nazwa": "Struktura terminowa (VIX / VIX3M)", "waga": 1.5, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^VIX3M", "Yahoo ^VIX i ^VIX3M"),
     "opis": "Stosunek zmienności oczekiwanej na 30 dni (VIX) do oczekiwanej na 3 miesiące (VIX3M). W spokojnym rynku bliższy termin jest tańszy (wynik poniżej 1). Wynik powyżej 1 znaczy, że rynek boi się najbliższych tygodni bardziej niż dalszych, co zdarza się w trakcie gwałtownych wyprzedaży.",
     "regula": "poniżej 0,88: +1; od 0,88 do 0,97: 0; od 0,97 do 1,05: -1; od 1,05: -2"},
    {"id": "spread_baa", "grupa": "rynek", "nazwa": "Spread kredytowy (Baa minus 10 lat)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("BAA10Y"),
     "opis": "O ile więcej płacą za pożyczkę firmy z ratingiem Baa (najniższy szczebel inwestycyjny) niż skarb USA. Rynek obligacji często pierwszy wyczuwa kłopoty firm: rosnący spread oznacza, że inwestorzy żądają wyższej premii za ryzyko bankructwa. Szybki wzrost w ciągu 3 miesięcy to sygnał ostrzegawczy dla akcji.",
     "regula": "zmiana 3 mies. od +0,5 pkt proc.: -2; od +0,25: -1; w pozostałych przypadkach percentyl z 5 lat poniżej 30: +1, wyżej 0"},
    {"id": "nfci", "grupa": "rynek", "nazwa": "Warunki finansowe (NFCI)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "tygodniowa", "zrodlo": _fred_url("NFCI"),
     "opis": "Indeks Fed z Chicago łączący ponad 100 miar rynku pieniężnego, kredytowego i akcji. Wartość ujemna oznacza warunki luźniejsze od średniej (łatwy dostęp do finansowania), dodatnia ciaśniejsze. Ciasne warunki dławią inwestycje i zwykle towarzyszą bessom.",
     "regula": "poniżej -0,35: +1; od -0,35 do 0: 0; od 0 do 0,5: -1; od 0,5: -2"},
    {"id": "move", "grupa": "rynek", "nazwa": "Zmienność obligacji (MOVE)", "waga": 0.5, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^MOVE"),
     "opis": "Odpowiednik VIX dla obligacji skarbowych USA: oczekiwana zmienność rentowności wyceniana w opcjach. Wysoki MOVE to niepewność co do stóp procentowych, która zwykle przelewa się na akcje (droższy kapitał, większe wahania wycen).",
     "regula": "poniżej 80: +1; od 80 do 120: 0; od 120 do 150: -1; od 150: -2"},
    {"id": "szerokosc", "grupa": "rynek", "nazwa": "Szerokość rynku (RSP / SPY, 3 mies.)", "waga": 0.5, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("RSP", "Yahoo RSP i SPY"),
     "opis": "Porównanie S&P 500 z równymi wagami (fundusz RSP, każda spółka po ok. 0,2%) z klasycznym S&P 500 ważonym kapitalizacją (SPY), zmiana z 3 miesięcy. Gdy RSP traci względem SPY, indeks ciągnie wąska grupa gigantów, a przeciętna spółka słabnie; taki rynek jest wrażliwszy na złe wieści z kilku firm.",
     "regula": "od +2%: +1; od -3 do +2%: 0; od -6 do -3%: -1; poniżej -6%: -2"},
    {"id": "apetyt", "grupa": "rynek", "nazwa": "Apetyt na ryzyko (XLY / XLP, 3 mies.)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("XLY", "Yahoo XLY i XLP"),
     "opis": "Spółki dóbr cyklicznych (fundusz XLY: samochody, handel, rozrywka) względem dóbr podstawowych (XLP: żywność, kosmetyki), zmiana z 3 miesięcy. Gdy inwestorzy wierzą w gospodarkę, kupują cykliczne; gdy się boją, uciekają do defensywnych. Spadek relacji to ucieczka od ryzyka.",
     "regula": "od +3%: +1; od -3 do +3%: 0; od -8 do -3%: -1; poniżej -8%: -2"},
    {"id": "przystan", "grupa": "rynek", "nazwa": "Akcje kontra obligacje (SPY minus IEF, 20 sesji)", "waga": 0.5, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("IEF", "Yahoo SPY i IEF"),
     "opis": "Różnica zwrotów z akcji (SPY) i 7–10-letnich obligacji skarbowych (IEF) w ostatnich 20 sesjach. Gdy obligacje wyraźnie wygrywają, kapitał ucieka do bezpiecznej przystani. To jeden ze składników znanego indeksu strachu i chciwości.",
     "regula": "od +3 pkt proc.: +1; od -3 do +3: 0; od -6 do -3: -1; poniżej -6: -2"},
    {"id": "pc_calkowity", "grupa": "rynek", "nazwa": "Put/call całkowity (Cboe)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_CBOE_PC,
     "opis": "Put/call ze wszystkich opcji na giełdzie Cboe (akcje, indeksy, fundusze), średnio z 10 sesji. Szersza, ale bardziej zaszumiona miara niż put/call akcji, bo zawiera zabezpieczenia instytucji na indeksach."},
    {"id": "pc_spx", "grupa": "rynek", "nazwa": "Put/call SPX (Cboe)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_CBOE_PC,
     "opis": "Put/call z wolumenu opcji na indeks S&P 500 (SPX i tygodniowe SPXW), średnio z 10 sesji. Na indeksie putów jest zawsze więcej, bo instytucje nimi zabezpieczają portfele; ważna jest zmiana względem własnej historii, a nie sam poziom."},
    {"id": "pc_oi_spx", "grupa": "rynek", "nazwa": "Put/call z otwartych pozycji SPX (do 60 dni)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_CBOE_SPX,
     "opis": "Otwarte kontrakty put podzielone przez otwarte kontrakty call na SPX w terminach do 60 dni, policzone z pełnego łańcucha opcji Cboe. Pokazuje stan zabezpieczeń, a nie jednodniowy obrót. Historia zbiera się od listopada 2026, więc na razie bez oceny."},
    {"id": "gex", "grupa": "rynek", "nazwa": "Ekspozycja gamma dealerów (SPX)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_CBOE_SPX,
     "opis": "Suma gamma × otwarte kontrakty × 100 × kurs² × 1% z łańcucha SPX, z callami dodatnio i putami ujemnie (uproszczone założenie, że animatorzy rynku mają kupione calle i sprzedane puty). Dodatnia wartość: zabezpieczając się, animatorzy kupują w spadkach i sprzedają we wzrostach, co tłumi ruchy. Ujemna: ruchy przyspieszają w obie strony. Bez oceny, dopóki nie zbierze się historia."},
    {"id": "skos", "grupa": "rynek", "nazwa": "Skośność 25 delta (SPX, ok. 30 dni)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_CBOE_SPX,
     "opis": "Zmienność implikowana puta z deltą ok. -0,25 minus calla z deltą ok. 0,25 dla terminu najbliższego 30 dniom, w punktach procentowych. Im wyższa, tym drożej rynek wycenia ochronę przed spadkiem względem udziału we wzroście, czyli tym większy popyt na zabezpieczenia."},
    {"id": "spread_hy", "grupa": "rynek", "nazwa": "Spread obligacji śmieciowych (HY)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _fred_url("BAMLH0A0HYM2"),
     "opis": "Premia za ryzyko obligacji firm z ratingiem poniżej inwestycyjnego (indeks ICE BofA, ponad oprocentowanie obligacji skarbowych). Czulszy od spreadu Baa, ale FRED udostępnia go tylko za ostatnie 3 lata, więc w ocenie liczy się spread Baa, a ten jest informacją."},
    {"id": "skew", "grupa": "rynek", "nazwa": "Indeks SKEW (Cboe)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^SKEW"),
     "opis": "Wycena ryzyka bardzo dużego spadku (tzw. czarnego łabędzia) z dalekich putów SPX; 100 oznacza brak dodatkowej premii, typowo 120–150. Słaby sygnał krótkoterminowy, przydatny jako tło."},
    {"id": "vvix", "grupa": "rynek", "nazwa": "Zmienność VIX (VVIX)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^VVIX"),
     "opis": "Zmienność samego VIX wyceniana w opcjach na VIX. Wysoki VVIX przy niskim VIX oznacza, że rynek płaci za ochronę przed nagłym skokiem strachu."},
    {"id": "vix9d", "grupa": "rynek", "nazwa": "Krótki strach (VIX9D / VIX)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^VIX9D"),
     "opis": "Zmienność oczekiwana na 9 dni względem 30 dni. Powyżej 1 rynek boi się najbliższych dni, np. przed ważnym wydarzeniem (posiedzenie Fed, dane o inflacji, wyniki największych spółek)."},
    {"id": "dolar", "grupa": "rynek", "nazwa": "Dolar (DXY)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("DX-Y.NYB"),
     "opis": "Kurs dolara względem koszyka sześciu walut. Silny dolar obniża zagraniczne przychody amerykańskich spółek po przeliczeniu i zaostrza warunki finansowe na świecie."},
    {"id": "ropa", "grupa": "rynek", "nazwa": "Ropa Brent", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("BZ=F"),
     "opis": "Cena ropy Brent (kontrakt najbliższy). Gwałtowne zwyżki ropy działają jak podatek dla konsumentów i podbijają inflację; w przeszłości poprzedzały kilka recesji."},
    {"id": "zloto", "grupa": "rynek", "nazwa": "Złoto", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("GC=F"),
     "opis": "Cena złota (kontrakt najbliższy). Silne zwyżki często oznaczają ucieczkę od ryzyka, obawy o inflację albo spadek zaufania do walut."},
    # -------------------------------------------------------------- TECHNIKA
    {"id": "trend200", "grupa": "technika", "nazwa": "Trend długoterminowy (średnia 200 sesji)", "waga": 2.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Położenie S&P 500 względem średniej ceny z 200 ostatnich sesji (ok. 10 miesięcy) i kierunek tej średniej (porównanie z wartością sprzed 20 sesji). Indeks nad rosnącą średnią to hossa, pod spadającą to bessa. To jeden z najstarszych i najodporniejszych filtrów trendu, dlatego ma podwójną wagę.",
     "regula": "nad średnią, średnia rośnie: +2; nad, średnia spada: +1; pod, średnia rośnie: -1; pod, średnia spada: -2"},
    {"id": "krzyz", "grupa": "technika", "nazwa": "Średnie 50 i 200 sesji", "waga": 1.0, "maks": 1,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Porównanie średniej z 50 sesji (trend kilkumiesięczny) ze średnią z 200 sesji. Średnia 50 nad 200 (tzw. złoty krzyż) oznacza, że średnioterminowy trend wspiera długoterminowy; pod nią (krzyż śmierci) to sygnał słabości.",
     "regula": "średnia 50 nad 200: +1; pod: -1"},
    {"id": "rsi", "grupa": "technika", "nazwa": "RSI (14 sesji, Wilder)", "waga": 0.5, "maks": 1,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Wskaźnik siły względnej: porównuje średnie wzrosty i spadki z 14 sesji w skali 0–100 (ta sama metoda co na karcie Technical Analyst). Powyżej 70 rynek jest wykupiony, bo urósł szybko i często łapie oddech; poniżej 30 wyprzedany i często odbija. Mówi o skrajnościach, a nie o kierunku trendu.",
     "regula": "od 70: -1; poniżej 30: +1; pomiędzy: 0"},
    {"id": "bollinger", "grupa": "technika", "nazwa": "Wstęgi Bollingera (20 sesji, 2σ)", "waga": 0.5, "maks": 1,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Wstęgi rysowane 2 odchylenia standardowe nad i pod średnią z 20 sesji; obejmują większość zwykłych wahań. %B mówi, gdzie jest kurs: 0 to dolna wstęga, 1 górna. Wyjście ponad górną wstęgę to przegrzanie, pod dolną wyprzedanie. Szerokość wstęg w % średniej pokazuje, czy rynek się uspokaja; mocny ścisk często zapowiada większy ruch.",
     "regula": "%B powyżej 1: -1; poniżej 0: +1; pomiędzy: 0"},
    {"id": "adx", "grupa": "technika", "nazwa": "ADX (siła trendu, 14 sesji)", "waga": 1.0, "maks": 1,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "ADX mierzy siłę trendu bez względu na kierunek w skali 0–100: powyżej 25 trend jest wyraźny, poniżej 20 rynek chodzi bokiem. Kierunek wskazują linie +DI (presja wzrostowa) i -DI (presja spadkowa).",
     "regula": "ADX od 25 i +DI nad -DI: +1; ADX od 25 i -DI nad +DI: -1; ADX poniżej 25: 0"},
    {"id": "macd", "grupa": "technika", "nazwa": "MACD (12, 26, 9)", "waga": 1.0, "maks": 1,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Różnica średnich wykładniczych z 12 i 26 sesji (MACD) i jej średnia z 9 sesji (linia sygnału). MACD nad sygnałem i nad zerem to rosnący impet wzrostów, pod sygnałem i pod zerem rosnący impet spadków. Reaguje szybciej niż średnia 200 sesji, ale daje więcej fałszywych sygnałów.",
     "regula": "MACD nad sygnałem i nad zerem: +1; pod sygnałem i pod zerem: -1; w pozostałych przypadkach 0"},
    {"id": "obsuniecie", "grupa": "technika", "nazwa": "Spadek od szczytu (52 tygodnie)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "O ile S&P 500 jest poniżej najwyższego zamknięcia z ostatniego roku. Do 5% to zwykłe wahania w trendzie, 10% to umowna korekta, 20% umowna bessa.",
     "regula": "spadek mniejszy niż 5%: +1; od 5 do 10%: 0; od 10 do 20%: -1; od 20%: -2"},
    {"id": "var_przekroczenia", "grupa": "technika", "nazwa": "Przekroczenia VaR 99% (63 sesje)", "waga": 1.0, "maks": 2,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_VAR,
     "opis": "VaR (Value at Risk) z karty VaR: dzienna strata SPY, której przy zmienności z ostatnich 3 lat nie powinno się przekroczyć z prawdopodobieństwem 99% (metoda parametryczna, okno 756 sesji). Liczymy, ile razy w ostatnich 63 sesjach (kwartał) rzeczywista strata była większa. Oczekiwane jest mniej niż jedno przekroczenie na kwartał; dwa i więcej oznaczają, że rynek wszedł w okres ryzyka większego niż w historii, z której liczono VaR.",
     "regula": "0 albo 1 przekroczenie: 0; 2 przekroczenia: -1; od 3: -2"},
    {"id": "var_dzienny", "grupa": "technika", "nazwa": "VaR 1 sesja, 99% (karta VaR, SPY)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_VAR,
     "opis": "Wartość zagrożona z karty VaR na najbliższą sesję: strata jednego udziału SPY, której z prawdopodobieństwem 99% nie powinno się przekroczyć (metoda parametryczna bez korekty o trend, odchylenie z 756 sesji), w USD i w % ceny, oraz kurs, poniżej którego SPY nie powinien zejść jutro. Percentyl porównuje dzisiejszy VaR w % ceny z ostatnimi 5 latami."},
    {"id": "var_21", "grupa": "technika", "nazwa": "Próg VaR na 21 sesji (z korektą o trend)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": ZRODLO_VAR,
     "opis": "Z karty VaR: kurs SPY, poniżej którego z prawdopodobieństwem 99% nie powinien spaść w ciągu najbliższych 21 sesji, z uwzględnieniem średniego rocznego zwrotu (metoda parametryczna z korektą o trend). Odległość od bieżącej ceny pokazuje, jak duży miesięczny spadek mieści się w normie."},
    {"id": "zmiennosc", "grupa": "technika", "nazwa": "Zmienność zrealizowana (21 sesji)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Jak mocno S&P 500 faktycznie się wahał w ostatnich 21 sesjach: odchylenie dziennych zwrotów w skali roku, w procentach. Długoterminowa średnia to około 15%."},
    {"id": "atr", "grupa": "technika", "nazwa": "Średni dzienny zakres (ATR 14)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Średni zakres ruchu S&P 500 w ciągu sesji (z uwzględnieniem luk między sesjami) z 14 dni, w punktach i w % kursu. Pomaga dobrać odległość zleceń i strike'ów do bieżącej zmienności."},
    {"id": "zwrot3m", "grupa": "technika", "nazwa": "Zwrot S&P 500 (3 mies.)", "waga": 0, "maks": 0,
     "czestotliwosc": "dzienna", "zrodlo": _yahoo_zrodlo("^GSPC"),
     "opis": "Zmiana kursu S&P 500 w ciągu 63 sesji. Tło dla pozostałych wskaźników: jak daleko rynek już zaszedł."},
]
DEF = {d["id"]: d for d in DEFINICJE}


# ---------------------------------------------------------------------------
# Funkcje liczące wskaźniki (każda zwraca słownik opisany wyżej)
# ---------------------------------------------------------------------------
def _ostatnia(seria):
    s = seria.dropna()
    return (s.index[-1], float(s.iloc[-1])) if not s.empty else (None, None)


def _poprzednia(seria):
    s = seria.dropna()
    return (s.index[-2], float(s.iloc[-2])) if len(s) >= 2 else (None, None)


def _wynik(seria, punkty=None, natywna=None, tekst="", pod="", zmiana="", data=None, czestotliwosc="dzienna", **reszta):
    natywna = seria if natywna is None else natywna
    if data is None:
        t, _ = _ostatnia(natywna)
        data = okres_pl(t, czestotliwosc) if t is not None else ""
    return {"seria": seria, "punkty": punkty, "natywna": natywna, "tekst": tekst, "pod": pod,
            "zmiana": zmiana, "data": data, **reszta}


def _makro_poziom(k, seria_id, wartosc, granice, punkty, czest, jednostka="%", miejsca=1, opis_zmiany=None):
    """Wskaźnik makro oceniany po poziomie (np. PKB, Sahm, CFNAI)."""
    s = wartosc
    dzienna = na_sesje(s, k["sesje"], OPOZNIENIA.get(seria_id, 1))
    t, v = _ostatnia(s)
    _, vp = _poprzednia(s)
    zmiana = f"{plz(v - vp, miejsca + (1 if jednostka == '' else 0))} {opis_zmiany or 'od poprzedniego odczytu'}" if vp is not None else ""
    return _wynik(dzienna, progi(dzienna, granice, punkty), s, f"{pl(v, miejsca)}{jednostka}", "", zmiana,
                  czestotliwosc=czest)


def licz_pkb(k):
    return _makro_poziom(k, "A191RL1Q225SBEA", k["fred"]["A191RL1Q225SBEA"], [0, 1, 2, 3], [-2, -1, 0, 1, 2],
                         "kwartalna", opis_zmiany="pkt proc. kw/kw")


def licz_gdpnow(k):
    w = _makro_poziom(k, "GDPNOW", k["fred"]["GDPNOW"], [0, 1, 2, 3], [-2, -1, 0, 1, 2], "kwartalna",
                      opis_zmiany="pkt proc. wobec poprzedniego kwartału")
    t, _ = _ostatnia(k["fred"]["GDPNOW"])
    w["pod"] = f"szacunek dla {okres_pl(t, 'kwartalna')}, w skali roku"
    return w


def licz_bezrobocie(k):
    s = k["fred"]["UNRATE"]
    zmiana_rr = s - s.shift(12)
    dzienna = na_sesje(zmiana_rr, k["sesje"], OPOZNIENIA["UNRATE"])
    poziom = na_sesje(s, k["sesje"], OPOZNIENIA["UNRATE"])
    _, v = _ostatnia(s)
    _, vp = _poprzednia(s)
    _, rr = _ostatnia(zmiana_rr)
    return _wynik(poziom, progi(dzienna, [-0.2, 0.2, 0.5], [1, 0, -1, -2]), s, f"{pl(v, 1)}%",
                  f"r/r {plz(rr, 1)} pkt proc.", f"{plz(v - vp, 1)} pkt proc. m/m", czestotliwosc="miesięczna")


def licz_sahm(k):
    w = _makro_poziom(k, "SAHMREALTIME", k["fred"]["SAHMREALTIME"], [0.2, 0.35, 0.5], [1, 0, -1, -2],
                      "miesięczna", jednostka=" pkt proc.", miejsca=2, opis_zmiany="m/m")
    w["pod"] = "alarm od 0,5"
    return w


def licz_wnioski(k):
    s = k["fred"]["IC4WSA"]
    rr = (s / s.shift(52) - 1) * 100
    dzienna = na_sesje(rr, k["sesje"], OPOZNIENIA["IC4WSA"])
    poziom = na_sesje(s, k["sesje"], OPOZNIENIA["IC4WSA"])
    _, v = _ostatnia(s)
    _, vp = _poprzednia(s)
    _, vrr = _ostatnia(rr)
    return _wynik(poziom, progi(dzienna, [-5, 10, 20], [1, 0, -1, -2]), s, f"{pl(v / 1000, 1)} tys.",
                  f"r/r {plz(vrr, 1)}%", f"{plz((v - vp) / 1000, 1)} tys. w/w", czestotliwosc="tygodniowa")


def licz_zatrudnienie(k):
    s = k["fred"]["PAYEMS"]
    srednia3 = (s - s.shift(3)) / 3
    dzienna = na_sesje(srednia3, k["sesje"], OPOZNIENIA["PAYEMS"])
    _, v = _ostatnia(srednia3)
    _, mm = _ostatnia(s - s.shift(1))
    return _wynik(dzienna, progi(dzienna, [0, 50, 150], [-2, -1, 0, 1]), srednia3, f"{plz(v, 0)} tys.",
                  f"ostatni miesiąc {plz(mm, 0)} tys.", "średnio na miesiąc", czestotliwosc="miesięczna")


def _inflacja(k, seria_id, granice):
    s = k["fred"][seria_id]
    rr = (s / s.shift(12) - 1) * 100
    dzienna = na_sesje(rr, k["sesje"], OPOZNIENIA[seria_id])
    _, v = _ostatnia(rr)
    _, vp = _poprzednia(rr)
    mm = (s / s.shift(1) - 1) * 100
    _, vmm = _ostatnia(mm)
    return _wynik(dzienna, progi(dzienna, granice, [1, 0, -1, -2]), rr, f"{pl(v, 1)}%", f"m/m {plz(vmm, 1)}%",
                  f"{plz(v - vp, 1)} pkt proc. od poprzedniego odczytu", czestotliwosc="miesięczna")


def licz_cpi(k):
    return _inflacja(k, "CPIAUCSL", [2.5, 3.5, 5])


def licz_pce(k):
    return _inflacja(k, "PCEPILFE", [2.3, 3.0, 4.0])


def licz_fed(k):
    gora = na_sesje(k["fred"]["DFEDTARU"], k["sesje"])
    dol = na_sesje(k["fred"]["DFEDTARL"], k["sesje"])
    efektywna = k["fred"]["DFF"]
    zmiana6 = gora - gora.shift(126)
    _, g = _ostatnia(gora)
    _, d = _ostatnia(dol)
    _, ef = _ostatnia(efektywna)
    _, z6 = _ostatnia(zmiana6)
    opis = "bez zmian" if abs(z6 or 0) < 0.01 else ("obniżki " if z6 < 0 else "podwyżki ") + f"{pl(abs(z6), 2)} pkt proc."
    return _wynik(gora, progi(zmiana6, [-0.1, 0.1], [1, 0, -1]), gora, f"{pl(d, 2)}–{pl(g, 2)}%",
                  f"efektywna {pl(ef, 2)}%", f"6 mies.: {opis}")


def licz_rentownosc10(k):
    s = na_sesje(k["fred"]["DGS10"], k["sesje"])
    zmiana3 = s - s.shift(63)
    import numpy as np
    import pandas as pd

    pkt = pd.Series(np.where(zmiana3 >= 0.75, -2, np.where((zmiana3 >= 0.4) | (s >= 4.75), -1, 0)), index=s.index, dtype=float)
    pkt[s.isna() | zmiana3.isna()] = np.nan
    _, v = _ostatnia(s)
    _, z = _ostatnia(zmiana3)
    _, z1 = _ostatnia(s - s.shift(21))
    return _wynik(s, pkt, k["fred"]["DGS10"], f"{pl(v, 2)}%", f"3 mies. {plz(z, 2)} pkt proc.",
                  f"{plz(z1, 2)} pkt proc. w miesiąc")


def _dzienna_fred(k, seria_id, granice, punkty, miejsca=2, jednostka=" pkt proc.", podpis=""):
    s = na_sesje(k["fred"][seria_id], k["sesje"])
    _, v = _ostatnia(s)
    _, z1 = _ostatnia(s - s.shift(21))
    pkt = progi(s, granice, punkty) if granice else None
    return _wynik(s, pkt, k["fred"][seria_id], f"{pl(v, miejsca)}{jednostka}", podpis,
                  f"{plz(z1, miejsca)} w miesiąc")


def licz_krzywa(k):
    return _dzienna_fred(k, "T10Y3M", [-0.5, 0, 1], [-2, -1, 0, 1], podpis="ujemna = krzywa odwrócona")


def licz_cfnai(k):
    w = _makro_poziom(k, "CFNAIMA3", k["fred"]["CFNAIMA3"], [-0.7, -0.35, 0.2], [-2, -1, 0, 1],
                      "miesięczna", jednostka="", miejsca=2, opis_zmiany="m/m")
    w["pod"] = "0 = tempo średnie, recesja zwykle poniżej -0,7"
    return w


def licz_krzywa2(k):
    return _dzienna_fred(k, "T10Y2Y", None, None)


def licz_rentownosc2(k):
    return _dzienna_fred(k, "DGS2", None, None, jednostka="%")


def licz_realna10(k):
    return _dzienna_fred(k, "DFII10", None, None, jednostka="%")


def licz_oczekiwania(k):
    return _dzienna_fred(k, "T10YIE", None, None, jednostka="%")


def licz_wnioski_kont(k):
    s = k["fred"]["CCSA"]
    _, v = _ostatnia(s)
    rr = (s / s.shift(52) - 1) * 100
    _, vrr = _ostatnia(rr)
    return _wynik(na_sesje(s, k["sesje"], OPOZNIENIA["CCSA"]), None, s, f"{pl(v / 1e6, 2)} mln", f"r/r {plz(vrr, 1)}%",
                  "", czestotliwosc="tygodniowa")


def licz_konsumenci(k):
    s = k["fred"]["UMCSENT"]
    _, v = _ostatnia(s)
    _, vp = _poprzednia(s)
    return _wynik(na_sesje(s, k["sesje"], OPOZNIENIA["UMCSENT"]), None, s, pl(v, 1), "",
                  f"{plz(v - vp, 1)} m/m", czestotliwosc="miesięczna")


def licz_bilans_fed(k):
    s = k["fred"]["WALCL"]
    zmiana = (s / s.shift(13) - 1) * 100
    _, v = _ostatnia(s)
    _, z = _ostatnia(zmiana)
    return _wynik(na_sesje(s, k["sesje"], OPOZNIENIA["WALCL"]), None, s, f"{pl(v / 1e6, 2)} bln USD",
                  "", f"{plz(z, 1)}% w 3 mies.", czestotliwosc="tygodniowa")


def _putcall(k, kolumna):
    pc = k["putcall"][kolumna].dropna()
    srednia10 = pc.rolling(10, min_periods=7).mean()
    dzienna = srednia10.reindex(k["sesje"]).ffill(limit=5)
    return pc, srednia10, dzienna


def licz_pc_akcje(k):
    pc, srednia10, dzienna = _putcall(k, "akcje")
    pct = percentyl_kroczacy(srednia10, 252, 120).reindex(k["sesje"]).ffill(limit=5)
    _, v = _ostatnia(srednia10)
    _, dzis = _ostatnia(pc)
    _, p = _ostatnia(pct)
    t, _ = _ostatnia(pc)
    return _wynik(dzienna, progi(pct, [90], [0, -1]), srednia10, pl(v, 2),
                  f"ostatnia sesja {pl(dzis, 2)} · percentyl z roku {pl(p, 0)}", "",
                  data=data_pl(t) if t is not None else "", percentyl=p, oknoPercentyla="1 rok")


def _pc_info(k, kolumna):
    pc, srednia10, dzienna = _putcall(k, kolumna)
    _, v = _ostatnia(srednia10)
    _, dzis = _ostatnia(pc)
    t, _ = _ostatnia(pc)
    return _wynik(dzienna, None, srednia10, pl(v, 2), f"ostatnia sesja {pl(dzis, 2)}", "",
                  data=data_pl(t) if t is not None else "")


def licz_pc_calkowity(k):
    return _pc_info(k, "calkowity")


def licz_pc_spx(k):
    return _pc_info(k, "spx")


def licz_vix_percentyl(k):
    vix = k["vix"].reindex(k["sesje"]).ffill(limit=3)
    pct = percentyl_kroczacy(vix, 252, 200)
    rmin = vix.rolling(252, min_periods=200).min()
    rmax = vix.rolling(252, min_periods=200).max()
    rank = (vix - rmin) / (rmax - rmin) * 100
    _, v = _ostatnia(vix)
    _, p = _ostatnia(pct)
    _, r = _ostatnia(rank)
    _, z = _ostatnia(vix - vix.shift(21))
    return _wynik(pct, progi(pct, [25, 75, 90], [1, 0, -1, -2]), pct, f"{pl(p, 0)}",
                  f"VIX {pl(v, 2)} · IV rank {pl(r, 0)}", f"VIX {plz(z, 2)} pkt w miesiąc",
                  percentyl=p, oknoPercentyla="1 rok")


def licz_premia_zmiennosci(k):
    vix = k["vix"].reindex(k["sesje"]).ffill(limit=3)
    rv = zmiennosc_zrealizowana(k["gspc"]["close"], 21)
    premia = vix - rv
    _, v = _ostatnia(premia)
    _, vv = _ostatnia(vix)
    _, vr = _ostatnia(rv)
    _, z = _ostatnia(premia - premia.shift(21))
    return _wynik(premia, progi(premia, [-2, 0, 6], [-2, -1, 0, 1]), premia, f"{plz(v, 1)} pkt",
                  f"VIX {pl(vv, 1)} · zrealizowana {pl(vr, 1)}", f"{plz(z, 1)} pkt w miesiąc")


def licz_struktura_vix(k):
    vix = k["vix"].reindex(k["sesje"]).ffill(limit=3)
    vix3m = k["yahoo"]["^VIX3M"]["close"].reindex(k["sesje"]).ffill(limit=3)
    iloraz = vix / vix3m
    _, v = _ostatnia(iloraz)
    _, a = _ostatnia(vix)
    _, b = _ostatnia(vix3m)
    _, z = _ostatnia(iloraz - iloraz.shift(21))
    return _wynik(iloraz, progi(iloraz, [0.88, 0.97, 1.05], [1, 0, -1, -2]), iloraz, pl(v, 3),
                  f"VIX {pl(a, 2)} · VIX3M {pl(b, 2)}", f"{plz(z, 3)} w miesiąc")


def licz_spread_baa(k):
    import numpy as np
    import pandas as pd

    s = na_sesje(k["fred"]["BAA10Y"], k["sesje"])
    zmiana3 = s - s.shift(63)
    pct5 = percentyl_kroczacy(s, 1260, 500)
    pkt = pd.Series(np.where(zmiana3 >= 0.5, -2, np.where(zmiana3 >= 0.25, -1, np.where(pct5 < 30, 1, 0))),
                    index=s.index, dtype=float)
    pkt[s.isna() | zmiana3.isna() | pct5.isna()] = np.nan
    _, v = _ostatnia(s)
    _, z = _ostatnia(zmiana3)
    _, p = _ostatnia(pct5)
    return _wynik(s, pkt, k["fred"]["BAA10Y"], f"{pl(v, 2)} pkt proc.",
                  f"3 mies. {plz(z, 2)} · percentyl 5 lat {pl(p, 0)}", "", percentyl=p, oknoPercentyla="5 lat")


def licz_nfci(k):
    s = k["fred"]["NFCI"]
    dzienna = na_sesje(s, k["sesje"], OPOZNIENIA["NFCI"])
    _, v = _ostatnia(s)
    _, vp = _poprzednia(s)
    return _wynik(dzienna, progi(dzienna, [-0.35, 0, 0.5], [1, 0, -1, -2]), s, pl(v, 3),
                  "ujemny = warunki luźniejsze od średniej", f"{plz(v - vp, 3)} w tydzień", czestotliwosc="tygodniowa")


def _yahoo_close(k, ticker, kolumna="close"):
    return k["yahoo"][ticker][kolumna].reindex(k["sesje"]).ffill(limit=3)


def licz_move(k):
    s = _yahoo_close(k, "^MOVE")
    _, v = _ostatnia(s)
    _, z = _ostatnia(s - s.shift(21))
    return _wynik(s, progi(s, [80, 120, 150], [1, 0, -1, -2]), s, pl(v, 1), "", f"{plz(z, 1)} w miesiąc")


def _relacja(k, licznik, mianownik, sesji):
    a = _yahoo_close(k, licznik, "adjclose")
    b = _yahoo_close(k, mianownik, "adjclose")
    rel = a / b
    return rel, (rel / rel.shift(sesji) - 1) * 100


def licz_szerokosc(k):
    rel, zm = _relacja(k, "RSP", "SPY", 63)
    _, v = _ostatnia(zm)
    _, z1 = _ostatnia((rel / rel.shift(21) - 1) * 100)
    return _wynik(zm, progi(zm, [-6, -3, 2], [-2, -1, 0, 1]), zm, f"{plz(v, 1)}%",
                  "RSP względem SPY w 3 mies.", f"{plz(z1, 1)}% w miesiąc")


def licz_apetyt(k):
    rel, zm = _relacja(k, "XLY", "XLP", 63)
    _, v = _ostatnia(zm)
    _, z1 = _ostatnia((rel / rel.shift(21) - 1) * 100)
    return _wynik(zm, progi(zm, [-8, -3, 3], [-2, -1, 0, 1]), zm, f"{plz(v, 1)}%",
                  "XLY względem XLP w 3 mies.", f"{plz(z1, 1)}% w miesiąc")


def licz_przystan(k):
    spy = _yahoo_close(k, "SPY", "adjclose")
    ief = _yahoo_close(k, "IEF", "adjclose")
    roznica = ((spy / spy.shift(20) - 1) - (ief / ief.shift(20) - 1)) * 100
    _, v = _ostatnia(roznica)
    _, a = _ostatnia((spy / spy.shift(20) - 1) * 100)
    _, b = _ostatnia((ief / ief.shift(20) - 1) * 100)
    return _wynik(roznica, progi(roznica, [-6, -3, 3], [-2, -1, 0, 1]), roznica, f"{plz(v, 1)} pkt proc.",
                  f"SPY {plz(a, 1)}% · IEF {plz(b, 1)}%", "")


def _z_lancucha(k, klucz, tekst, pod, miejsca=2):
    import pandas as pd

    arch = k["opcje_arch"]
    if arch is None or arch.empty or klucz not in arch:
        return _wynik(pd.Series(dtype=float), None, None, "brak danych", "łańcuch SPX niedostępny", "")
    s = arch[klucz].dropna()
    dzienna = s.reindex(k["sesje"]).ffill(limit=3)
    t, v = _ostatnia(s)
    p = percentyl_ostatniej(s, 1) if len(s) >= 60 else None
    return _wynik(dzienna, None, s, tekst(v), pod(v), f"historia od {data_pl(s.index[0])} ({len(s)} sesji)",
                  data=data_pl(t) if t is not None else "", percentyl=p, oknoPercentyla="1 rok" if p is not None else None)


def licz_pc_oi_spx(k):
    a = k.get("lancuch") or {}
    return _z_lancucha(k, "pcOi60", lambda v: pl(v, 2),
                       lambda v: f"{pl(a.get('oiPut', 0) / 1e6, 2)} mln putów · {pl(a.get('oiCall', 0) / 1e6, 2)} mln calli")


def licz_gex(k):
    return _z_lancucha(k, "gexMldUsd", lambda v: f"{plz(v, 2)} mld USD",
                       lambda v: "na 1% ruchu indeksu · " + ("tłumi ruchy" if v > 0 else "przyspiesza ruchy"))


def licz_skos(k):
    a = (k.get("lancuch") or {}).get("skos") or {}
    return _z_lancucha(k, "skos25d", lambda v: f"{pl(v, 1)} pkt proc.",
                       lambda v: (f"put {pl(a.get('put'), 0)} {pl(a.get('ivPut'), 1)}% · call {pl(a.get('call'), 0)} {pl(a.get('ivCall'), 1)}% · {a.get('dni')} dni" if a else ""))


def licz_spread_hy(k):
    s = k["fred"]["BAMLH0A0HYM2"]
    w = _dzienna_fred(k, "BAMLH0A0HYM2", None, None)
    p = percentyl_ostatniej(s, 3)
    w["pod"] = f"percentyl z 3 lat {pl(p, 0)}"
    w["percentyl"] = p
    w["oknoPercentyla"] = "3 lata"
    return w


def _yahoo_info(k, ticker, miejsca=2, jednostka="", procent=True):
    s = _yahoo_close(k, ticker)
    _, v = _ostatnia(s)
    zm = (s / s.shift(21) - 1) * 100 if procent else s - s.shift(21)
    _, z = _ostatnia(zm)
    return _wynik(s, None, k["yahoo"][ticker]["close"], f"{pl(v, miejsca)}{jednostka}", "",
                  f"{plz(z, 1)}{'%' if procent else ''} w miesiąc")


def licz_skew(k):
    return _yahoo_info(k, "^SKEW", 1, procent=False)


def licz_vvix(k):
    return _yahoo_info(k, "^VVIX", 1, procent=False)


def licz_vix9d(k):
    vix = k["vix"].reindex(k["sesje"]).ffill(limit=3)
    s = _yahoo_close(k, "^VIX9D") / vix
    _, v = _ostatnia(s)
    _, a = _ostatnia(_yahoo_close(k, "^VIX9D"))
    return _wynik(s, None, s, pl(v, 3), f"VIX9D {pl(a, 2)}", "")


def licz_dolar(k):
    return _yahoo_info(k, "DX-Y.NYB", 2)


def licz_ropa(k):
    return _yahoo_info(k, "BZ=F", 2, " USD")


def licz_zloto(k):
    return _yahoo_info(k, "GC=F", 0, " USD")


def licz_trend200(k):
    import numpy as np
    import pandas as pd

    c = k["gspc"]["close"]
    s200 = sma(c, 200)
    nachylenie = s200 - s200.shift(20)
    nad = c > s200
    rosnie = nachylenie > 0
    pkt = pd.Series(np.where(nad, np.where(rosnie, 2, 1), np.where(rosnie, -1, -2)), index=c.index, dtype=float)
    pkt[s200.isna() | nachylenie.isna()] = np.nan
    odl = (c / s200 - 1) * 100
    _, v = _ostatnia(odl)
    _, sv = _ostatnia(s200)
    _, n = _ostatnia(nachylenie)
    return _wynik(odl, pkt, odl, f"{plz(v, 1)}%", f"średnia {pl(sv, 0)} · {'rośnie' if (n or 0) > 0 else 'spada'}",
                  "odległość kursu od średniej")


def licz_krzyz(k):
    import numpy as np
    import pandas as pd

    c = k["gspc"]["close"]
    s50, s200 = sma(c, 50), sma(c, 200)
    roznica = (s50 / s200 - 1) * 100
    pkt = pd.Series(np.where(s50 > s200, 1, -1), index=c.index, dtype=float)
    pkt[s200.isna()] = np.nan
    _, v = _ostatnia(roznica)
    _, a = _ostatnia(s50)
    _, b = _ostatnia(s200)
    return _wynik(roznica, pkt, roznica, f"{plz(v, 1)}%", f"średnia 50: {pl(a, 0)} · 200: {pl(b, 0)}",
                  "średnia 50 względem 200")


def licz_rsi(k):
    r = rsi_wildera(k["gspc"]["close"], 14)
    _, v = _ostatnia(r)
    _, z = _ostatnia(r - r.shift(5))
    return _wynik(r, progi(r, [30, 70], [1, 0, -1]), r, pl(v, 1), "30 wyprzedanie · 70 wykupienie",
                  f"{plz(z, 1)} w tydzień")


def licz_bollinger(k):
    c = k["gspc"]["close"]
    _, gora, dol, pb, szer = wstegi_bollingera(c)
    pct_szer = percentyl_kroczacy(szer, 252, 200)
    _, v = _ostatnia(pb)
    _, g = _ostatnia(gora)
    _, d = _ostatnia(dol)
    _, sz = _ostatnia(szer)
    _, ps = _ostatnia(pct_szer)
    return _wynik(pb, progi(pb, [0, 1], [1, 0, -1]), pb, f"%B {pl(v, 2)}",
                  f"wstęgi {pl(d, 0)}–{pl(g, 0)} · szerokość {pl(sz, 1)}% (percentyl {pl(ps, 0)})", "")


def licz_adx(k):
    import numpy as np
    import pandas as pd

    g = k["gspc"]
    a, pdi, mdi, _ = adx_wildera(g["high"], g["low"], g["close"], 14)
    pkt = pd.Series(np.where(a >= 25, np.where(pdi > mdi, 1, -1), 0), index=a.index, dtype=float)
    pkt[a.isna()] = np.nan
    _, v = _ostatnia(a)
    _, p = _ostatnia(pdi)
    _, m = _ostatnia(mdi)
    return _wynik(a, pkt, a, pl(v, 1), f"+DI {pl(p, 1)} · -DI {pl(m, 1)}",
                  "trend " + ("wyraźny" if (v or 0) >= 25 else "słaby" if (v or 0) < 20 else "umiarkowany"))


def licz_macd(k):
    import numpy as np
    import pandas as pd

    linia, syg, hist = macd(k["gspc"]["close"])
    pkt = pd.Series(np.where((linia > syg) & (linia > 0), 1, np.where((linia < syg) & (linia < 0), -1, 0)),
                    index=linia.index, dtype=float)
    pkt[linia.isna() | syg.isna()] = np.nan
    _, v = _ostatnia(linia)
    _, s = _ostatnia(syg)
    _, h = _ostatnia(hist)
    return _wynik(linia, pkt, linia, pl(v, 1), f"sygnał {pl(s, 1)} · histogram {plz(h, 1)}", "")


def licz_obsuniecie(k):
    c = k["gspc"]["close"]
    szczyt = c.rolling(252, min_periods=60).max()
    dd = (c / szczyt - 1) * 100
    _, v = _ostatnia(dd)
    _, sz = _ostatnia(szczyt)
    return _wynik(dd, progi(dd, [-20, -10, -5], [-2, -1, 0, 1]), dd, f"{pl(v, 1)}%",
                  f"szczyt 52 tyg. {pl(sz, 0)}", "")


def licz_var_przekroczenia(k):
    v = k["var"]
    przekroczenie = (v["close"] < v["prog_bez_korekty"]).astype(float)
    przekroczenie[v["prog_bez_korekty"].isna()] = float("nan")
    liczba = przekroczenie.rolling(63, min_periods=63).sum()
    dzienna = liczba.reindex(k["sesje"]).ffill(limit=3)
    _, n = _ostatnia(liczba)
    ostatnie = v.index[przekroczenie == 1]
    ost = data_pl(ostatnie[-1]) if len(ostatnie) else "brak"
    return _wynik(dzienna, progi(dzienna, [2, 3], [0, -1, -2]), liczba, pl(n, 0),
                  f"oczekiwane mniej niż 1 · ostatnie: {ost}", "w ostatnich 63 sesjach")


def licz_var_dzienny(k):
    v = k["var"]
    proc = v["var_bez_korekty"] / v["close"] * 100
    _, usd = _ostatnia(v["var_bez_korekty"])
    _, p = _ostatnia(proc)
    _, c = _ostatnia(v["close"])
    pct = percentyl_ostatniej(proc, 5)
    return _wynik(proc.reindex(k["sesje"]).ffill(limit=3), None, proc, f"{pl(p, 2)}%",
                  f"{pl(usd, 2)} USD na udział · jutro próg {pl(c - usd, 2)}", "", percentyl=pct, oknoPercentyla="5 lat")


def licz_var_21(k):
    v = k["var"]
    proc = v["var_z_korekta"] / v["close"] * 100
    _, usd = _ostatnia(v["var_z_korekta"])
    _, p = _ostatnia(proc)
    _, c = _ostatnia(v["close"])
    return _wynik(proc.reindex(k["sesje"]).ffill(limit=3), None, proc, f"{pl(c - usd, 2)} USD",
                  f"SPY {pl(c, 2)} · spadek do progu {pl(p, 1)}%", "")


def licz_zmiennosc(k):
    rv = zmiennosc_zrealizowana(k["gspc"]["close"], 21)
    _, v = _ostatnia(rv)
    _, z = _ostatnia(rv - rv.shift(21))
    return _wynik(rv, None, rv, f"{pl(v, 1)}%", "w skali roku", f"{plz(z, 1)} pkt w miesiąc",
                  percentyl=percentyl_ostatniej(rv, 5), oknoPercentyla="5 lat")


def licz_atr(k):
    g = k["gspc"]
    _, _, _, atr = adx_wildera(g["high"], g["low"], g["close"], 14)
    proc = atr / g["close"] * 100
    _, v = _ostatnia(atr)
    _, p = _ostatnia(proc)
    return _wynik(proc, None, proc, f"{pl(p, 2)}%", f"{pl(v, 1)} pkt indeksu", "")


def licz_zwrot3m(k):
    c = k["gspc"]["close"]
    zm = (c / c.shift(63) - 1) * 100
    _, v = _ostatnia(zm)
    _, kurs = _ostatnia(c)
    return _wynik(zm, None, zm, f"{plz(v, 1)}%", f"S&P 500 {pl(kurs, 2)}", "")


LICZ = {d["id"]: globals()[f"licz_{d['id']}"] for d in DEFINICJE}


# ---------------------------------------------------------------------------
# Nastroje (strach / chciwość) i sygnał złożony
# ---------------------------------------------------------------------------
def skladniki_nastrojow(k):
    """Siedem składników indeksu nastrojów, każdy jako percentyl (0-100) z 2 lat, gdzie
    wysoko = chciwość. Wzorowane na znanym indeksie strachu i chciwości, liczone z naszych danych."""
    c = k["gspc"]["close"]
    vix = k["vix"].reindex(k["sesje"]).ffill(limit=3)
    spy = _yahoo_close(k, "SPY", "adjclose")
    ief = _yahoo_close(k, "IEF", "adjclose")
    hyg = _yahoo_close(k, "HYG", "adjclose")
    rsp = _yahoo_close(k, "RSP", "adjclose")
    pc = k["putcall"]["akcje"].rolling(5, min_periods=4).mean().reindex(k["sesje"]).ffill(limit=5)
    surowe = {
        "momentum": ("Kurs względem średniej 125 sesji", c / sma(c, 125) - 1, 1),
        "sila": ("Odległość od szczytu 52 tyg.", c / c.rolling(252, min_periods=60).max() - 1, 1),
        "szerokosc": ("Szerokość: RSP względem SPY, 1 mies.", (rsp / spy) / (rsp / spy).shift(21) - 1, 1),
        "putcall": ("Put/call akcji, 5 sesji", pc, -1),
        "zmiennosc": ("VIX względem średniej 50 sesji", vix / sma(vix, 50), -1),
        "przystan": ("Akcje kontra obligacje, 20 sesji", (spy / spy.shift(20)) - (ief / ief.shift(20)), 1),
        "smieciowe": ("Obligacje śmieciowe kontra skarbowe, 20 sesji", (hyg / hyg.shift(20)) - (ief / ief.shift(20)), 1),
    }
    wynik = {}
    for klucz, (nazwa, seria, kierunek) in surowe.items():
        pct = percentyl_kroczacy(seria, 504, 250)
        wynik[klucz] = (nazwa, pct if kierunek > 0 else 100 - pct)
    return wynik


def poziom(wynik: float, tabela=POZIOMY) -> tuple[str, str]:
    for granica, klucz, etykieta in tabela:
        if wynik >= granica:
            return klucz, etykieta
    return tabela[-1][1], tabela[-1][2]


def stan_z_punktow(p, maks: int) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "brak"
    if maks == 0:
        return "info"
    if p > 0:
        return "dobrze"
    if p == 0:
        return "neutralnie"
    return "zle" if p <= -2 else "uwaga"


def wynik_zlozony(wskazniki: dict):
    """DataFrame z wynikiem każdej grupy i całości (od -100 do +100) na każdą sesję.

    Punkty wskaźnika dzielimy przez jego maksimum (każdy daje od -1 do +1), grupa to średnia
    ważona dostępnych wskaźników (liczona, gdy dostępna jest co najmniej połowa wagi grupy),
    a całość to średnia grup z wagami WAGI_GRUP (gdy dostępne są wszystkie trzy).
    """
    import pandas as pd

    kolumny = {}
    for d in DEFINICJE:
        w = wskazniki.get(d["id"])
        if d["maks"] and w is not None and w["punkty"] is not None:
            kolumny[d["id"]] = w["punkty"] / d["maks"]
    P = pd.DataFrame(kolumny)
    grupy = pd.DataFrame(index=P.index)
    for g in WAGI_GRUP:
        ids = [d["id"] for d in DEFINICJE if d["grupa"] == g and d["id"] in P]
        wagi = pd.Series({i: DEF[i]["waga"] for i in ids})
        dostepne = P[ids].notna().mul(wagi).sum(axis=1)
        licznik = P[ids].fillna(0).mul(wagi).sum(axis=1)
        grupy[g] = (licznik / dostepne * 100).where(dostepne >= 0.5 * wagi.sum())
    calosc = sum(grupy[g] * w for g, w in WAGI_GRUP.items())
    grupy["wynik"] = calosc.where(grupy[list(WAGI_GRUP)].notna().all(axis=1))
    return grupy


def przyszle_zwroty(zamkniecia):
    """Dla każdej sesji: zwrot S&P 500 w kolejnych 21 i 63 sesjach oraz największe obsunięcie
    w kolejnych 63 sesjach (najniższe zamknięcie względem dzisiejszego, w %, 0 gdy nie spadł)."""
    import pandas as pd

    c = zamkniecia
    minimum63 = c[::-1].rolling(63, min_periods=63).min()[::-1].shift(-1)
    return pd.DataFrame({
        "r21": (c.shift(-21) / c - 1) * 100,
        "r63": (c.shift(-63) / c - 1) * 100,
        "dd63": (minimum63 / c - 1).clip(upper=0) * 100,
    })


def statystyki_przyszlosci(x) -> dict:
    """Średnie przyszłe zwroty i obsunięcia dla wybranych sesji (wiersze z przyszle_zwroty)."""
    a = x.dropna(subset=["r21"])
    b = x.dropna(subset=["r63"])
    return {
        "dni": int(len(x)),
        "sr21": round(float(a["r21"].mean()), 2) if len(a) else None,
        "plus21": round(float((a["r21"] > 0).mean() * 100), 1) if len(a) else None,
        "sr63": round(float(b["r63"].mean()), 2) if len(b) else None,
        "plus63": round(float((b["r63"] > 0).mean() * 100), 1) if len(b) else None,
        "dd63": round(float(b["dd63"].mean()), 2) if len(b) else None,
        # odsetek sesji, po których S&P 500 w ciągu 63 sesji spadł o 10% lub więcej
        "p10": round(float((b["dd63"] <= -10).mean() * 100), 1) if len(b) else None,
    }


def skutecznosc(wynik, zamkniecia) -> dict:
    """Jak zachowywał się S&P 500 po dniach z danym poziomem sygnału (od początku historii)."""
    import pandas as pd

    df = pd.concat([pd.DataFrame({"wynik": wynik}), przyszle_zwroty(zamkniecia)], axis=1, sort=True)
    df = df.dropna(subset=["wynik"])
    df["poziom"] = [poziom(w)[0] for w in df["wynik"]]
    wiersze = []

    def wiersz(klucz, etykieta, x):
        return {"poziom": klucz, "etykieta": etykieta,
                "udzial": round(len(x) / len(df) * 100, 1) if len(df) else None, **statystyki_przyszlosci(x)}

    for _, klucz, etykieta in POZIOMY:
        x = df[df["poziom"] == klucz]
        if len(x):
            wiersze.append(wiersz(klucz, etykieta, x))
    wiersze.append(wiersz("wszystkie", "Wszystkie dni", df))
    pelne = df.dropna(subset=["r63"])
    korelacja = korelacja_dd = None
    if len(pelne) > 100:
        # korelacja rang (Spearmana): +1 = idealnie zgodny porządek, 0 = brak związku
        korelacja = float(pelne["wynik"].rank().corr(pelne["r63"].rank()))
        korelacja_dd = float(pelne["wynik"].rank().corr(pelne["dd63"].rank()))
        # Przy stałym wyniku (zero rozrzutu) korelacja jest nieokreślona i pandas zwraca NaN, którego
        # nie przyjmuje JSON czytany przez przeglądarkę; zamiast niego zapisujemy brak wartości.
        korelacja = None if math.isnan(korelacja) else korelacja
        korelacja_dd = None if math.isnan(korelacja_dd) else korelacja_dd
    return {"od": df.index[0].strftime("%Y-%m-%d") if len(df) else None,
            "do": df.index[-1].strftime("%Y-%m-%d") if len(df) else None,
            "wiersze": wiersze,
            "korelacja63": round(korelacja, 3) if korelacja is not None else None,
            "korelacjaObsuniecia": round(korelacja_dd, 3) if korelacja_dd is not None else None}


def opis_automatyczny(sygnal: dict, nastroje: dict, wskazniki: list[dict]) -> list[str]:
    """Kilka zdań opisu z samych liczb (gdy rutyna Claude nie napisała jeszcze oceny)."""
    zdania = []
    licz = sygnal["liczniki"]
    zdania.append(
        f"Wynik {plz(sygnal['wynik'], 0)} pkt w skali od -100 do +100, czyli sygnał „{sygnal['etykieta'].lower()}”: "
        f"{licz['plus']} ocenianych wskaźników sprzyja indeksowi, {licz['minus']} mu nie sprzyja, a {licz['zero']} jest neutralnych."
    )
    grupy = sorted(sygnal["grupy"], key=lambda g: g["wynik"] if g["wynik"] is not None else 0)
    if grupy and grupy[0]["wynik"] is not None:
        zdania.append(
            f"Najsłabsza grupa to {grupy[0]['nazwa'].lower()} ({plz(grupy[0]['wynik'], 0)}), "
            f"najmocniejsza {grupy[-1]['nazwa'].lower()} ({plz(grupy[-1]['wynik'], 0)})."
        )
    plusy = [w for w in sygnal["wklad"]["plus"][:3]]
    minusy = [w for w in sygnal["wklad"]["minus"][:3]]
    if plusy:
        zdania.append("Najmocniej na plus: " + "; ".join(f"{w['nazwa']}: {w['tekst']}" for w in plusy) + ".")
    if minusy:
        zdania.append("Najmocniej na minus: " + "; ".join(f"{w['nazwa']}: {w['tekst']}" for w in minusy) + ".")
    zm = sygnal.get("zmiana") or {}
    if zm.get("5") is not None:
        zdania.append(f"Zmiana wyniku od poprzedniej sesji {plz(zm.get('1'), 0)} pkt, w tydzień {plz(zm.get('5'), 0)} pkt.")
    if sygnal.get("zmienioneOceny"):
        zdania.append("Ocenę od poprzedniej sesji zmieniły: " + "; ".join(
            f"{z['nazwa']} (z {plz(z['bylo'], 0)} na {plz(z['jest'], 0)})" for z in sygnal["zmienioneOceny"][:5]) + ".")
    if nastroje.get("wartosc") is not None:
        zdania.append(f"Indeks nastrojów: {pl(nastroje['wartosc'], 0)} na 100 ({nastroje['etykieta'].lower()}).")
    return zdania


# ---------------------------------------------------------------------------
# Magazyn funkcji przeglądarki (wspólny dla wszystkich okien): konfiguracja, stan,
# formatowanie, pobieranie dwóch plików JSON i małe wykresy SVG.
# ---------------------------------------------------------------------------
APP_JS_MAGAZYN = r"""
// ===========================================================================
// MAGAZYN FUNKCJI: konfiguracja, formatowanie, pobieranie danych, wykresiki SVG
// ===========================================================================
// Wszystkie liczby liczy raz dziennie skrypt Pythona (stan_rynku.py aktualizuj, workflow
// GitHub Actions), a ocenę dnia pisze rutyna Claude. Strona tylko czyta dwa pliki JSON
// z repozytorium i je rysuje, więc nie potrzebuje tokenu ani zapytań do Workera.
const ST_PLIK_STANU = "../data/stan-rynku/stan.json";
const ST_PLIK_OCENY = "../data/stan-rynku/ocena.json";
const ST_GRUPY = { makro: "Makro", rynek: "Rynek", technika: "Technika" };
const ST_ETYKIETY = {
  "silnie-pozytywny": "Silnie pozytywny", pozytywny: "Pozytywny", neutralny: "Neutralny",
  negatywny: "Negatywny", "silnie-negatywny": "Silnie negatywny",
};
const ST_OPIS_STANU = {
  dobrze: "sprzyja indeksowi", neutralnie: "neutralnie", uwaga: "ostrzeżenie",
  zle: "wyraźnie nie sprzyja", info: "informacyjnie, poza sygnałem", brak: "brak danych",
};

// Stan strony wspólny dla wszystkich okien.
const st = {
  stan: null, // data/stan-rynku/stan.json
  ocena: null, // data/stan-rynku/ocena.json (pisze rutyna Claude); może jeszcze nie istnieć
  otwarte: new Set(), // rozwinięte wiersze wskaźników
  zakres: "3l", // zakres wykresu historii: 1r, 3l, max
  grupyNaWykresie: false,
  okres: "calosc", // okres tabeli skuteczności
};

function stEl(id) {
  return document.getElementById(id);
}
function stEsc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[z]));
}
function stLiczba(v, m = 1) {
  if (v == null || !Number.isFinite(v)) return "–";
  if (Number(v.toFixed(m)) === 0) v = 0; // bez „-0" po zaokrągleniu
  return v.toLocaleString("pl-PL", { minimumFractionDigits: m, maximumFractionDigits: m });
}
function stZnak(v, m = 1) {
  if (v == null || !Number.isFinite(v)) return "–";
  return (Number(v.toFixed(m)) > 0 ? "+" : "") + stLiczba(v, m);
}
function stProc(v, m = 1) {
  return v == null || !Number.isFinite(v) ? "–" : `${stLiczba(v, m)}%`;
}
function stProcZnak(v, m = 1) {
  return v == null || !Number.isFinite(v) ? "–" : `${stZnak(v, m)}%`;
}
function stDataPl(iso) {
  if (!iso) return "–";
  const [r, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}.${m}.${r}`;
}
function stCzasPl(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "–" : d.toLocaleString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function stKlasaZnaku(v) {
  return v > 0 ? "st-plus" : v < 0 ? "st-minus" : "";
}
// Poziom sygnału dla wyniku (progi z pliku danych, ten sam podział co w Pythonie).
function stPoziomWyniku(wynik) {
  const progi = st.stan.sygnal.progi;
  return progi.find((p) => wynik >= p.od) || progi[progi.length - 1];
}
// Tekst pisany przez Claude: bez HTML, **pogrubienie** dozwolone.
function stTekst(t) {
  return stEsc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
}
async function stPobierz(url) {
  const odp = await fetch(url, { cache: "no-cache" });
  if (odp.status === 404) return null;
  if (!odp.ok) throw new Error(`${url}: HTTP ${odp.status}`);
  return odp.json();
}

// Wykresik w wierszu wskaźnika: ostatni rok wartości, bez osi.
function stIskra(punkty, dni = 365) {
  if (!punkty || punkty.length < 2) return "";
  const koniec = Date.parse(punkty[punkty.length - 1][0]);
  const p = punkty.filter((x) => Date.parse(x[0]) >= koniec - dni * 864e5);
  if (p.length < 2) return "";
  const w = p.map((x) => x[1]);
  const min = Math.min(...w);
  const zakres = Math.max(...w) - min || 1;
  const xy = p.map((x, i) => `${((i / (p.length - 1)) * 100).toFixed(1)},${(22 - ((x[1] - min) / zakres) * 20).toFixed(1)}`).join(" ");
  return `<svg class="st-iskra-svg" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true"><polyline points="${xy}"/></svg>`;
}

// Większy wykres w rozwinięciu wskaźnika: 3 lata, minimum i maksimum na osi.
function stWykresMaly(punkty) {
  if (!punkty || punkty.length < 2) return "";
  const W = 600, H = 120, L = 4, R = 58, T = 8, B = 18;
  const t = punkty.map((x) => Date.parse(x[0]));
  const v = punkty.map((x) => x[1]);
  const vmin = Math.min(...v), vmax = Math.max(...v), dv = vmax - vmin || 1;
  const X = (x) => L + ((x - t[0]) / (t[t.length - 1] - t[0] || 1)) * (W - L - R);
  const Y = (y) => T + (1 - (y - vmin) / dv) * (H - T - B);
  const fmt = (x) => (Math.abs(x) >= 1000 ? stLiczba(x, 0) : Math.abs(x) >= 10 ? stLiczba(x, 1) : stLiczba(x, 2));
  const linia = punkty.map((x, i) => `${X(t[i]).toFixed(1)},${Y(v[i]).toFixed(1)}`).join(" ");
  const zero = vmin < 0 && vmax > 0 ? `<line class="st-svg-zero" x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}"/>` : "";
  return `<svg class="st-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Wykres wskaźnika z ostatnich lat">
    <line class="st-svg-siatka" x1="${L}" x2="${W - R}" y1="${Y(vmax)}" y2="${Y(vmax)}"/>
    <line class="st-svg-siatka" x1="${L}" x2="${W - R}" y1="${Y(vmin)}" y2="${Y(vmin)}"/>${zero}
    <polyline class="st-svg-linia" points="${linia}"/>
    <circle class="st-svg-kropka" cx="${X(t[t.length - 1])}" cy="${Y(v[v.length - 1])}" r="3"/>
    <text class="st-svg-opis" x="${W - R + 4}" y="${Y(vmax) + 4}">${fmt(vmax)}</text>
    <text class="st-svg-opis" x="${W - R + 4}" y="${Y(vmin) + 4}">${fmt(vmin)}</text>
    <text class="st-svg-opis" x="${L}" y="${H - 4}">${stDataPl(punkty[0][0])}</text>
    <text class="st-svg-opis" x="${W - R}" y="${H - 4}" text-anchor="end">${stDataPl(punkty[punkty.length - 1][0])}</text>
  </svg>`;
}
"""


# ===========================================================================
# elementy
# ===========================================================================
# Po jednym orkiestratorze na każde okno karty. Orkiestrator z Pythona buduje dane okna
# (część pliku data/stan-rynku/stan.json), a HTML_FRAGMENT_X i APP_JS_X rysują je w przeglądarce.
# Wspólny pobór danych robi zbierz_dane() (raz na aktualizację), a zapis aktualizuj().

def zbierz_dane() -> dict:
    """Pobiera wszystkie serie i zwraca kontekst `k` dla funkcji liczących."""
    import pandas as pd

    bledy, zrodla = [], []
    teraz = datetime.now(timezone.utc)

    print("Yahoo przez Worker…")
    gspc = pobierz_yahoo("^GSPC", "30y")  # bez S&P 500 nie ma karty: błąd przerywa aktualizację
    sesje = gspc.index
    yahoo = {"^GSPC": gspc}
    for t in ["SPY", "^VIX3M", "^VIX9D", "^VVIX", "^SKEW", "^MOVE", "RSP", "XLY", "XLP", "IEF", "HYG",
              "DX-Y.NYB", "BZ=F", "GC=F"]:
        try:
            yahoo[t] = pobierz_yahoo(t, "30y")
        except Exception as blad:  # noqa: BLE001
            bledy.append(f"Yahoo {t}: {blad}")
            yahoo[t] = pd.DataFrame(columns=["open", "high", "low", "close", "adjclose"], dtype=float)
    zrodla.append({"nazwa": "Yahoo Finance (przez Worker)", "opis": "S&P 500, SPY, VIX3M, VIX9D, VVIX, SKEW, MOVE, RSP, XLY, XLP, IEF, HYG, dolar, ropa, złoto",
                   "ostatnia": gspc.index[-1].strftime("%Y-%m-%d"), "stan": "ok" if not any(b.startswith("Yahoo") for b in bledy) else "częściowo"})

    print("FRED…")
    fred, sposoby = {}, set()
    serie_fred = ["A191RL1Q225SBEA", "GDPNOW", "UNRATE", "SAHMREALTIME", "IC4WSA", "CCSA", "PAYEMS", "CPIAUCSL",
                  "PCEPILFE", "DFEDTARU", "DFEDTARL", "DFF", "DGS10", "DGS2", "T10Y3M", "T10Y2Y", "CFNAIMA3", "BAA10Y",
                  "BAMLH0A0HYM2", "NFCI", "T10YIE", "DFII10", "UMCSENT", "WALCL"]
    for s in serie_fred:
        try:
            fred[s], sposob = pobierz_fred(s, "1999-01-01")
            sposoby.add(sposob)
        except Exception as blad:  # noqa: BLE001
            bledy.append(f"FRED {s}: {_bez_klucza(str(blad))}")
            fred[s] = pd.Series(dtype=float)
    ostatnie_fred = max((s.index[-1] for s in fred.values() if len(s)), default=None)
    zrodla.append({"nazwa": "FRED (Fed z St. Louis)", "opis": f"{len(serie_fred)} serii makro, stóp i spreadów",
                   "ostatnia": ostatnie_fred.strftime("%Y-%m-%d") if ostatnie_fred is not None else None,
                   "stan": "ok" if not any(b.startswith("FRED") for b in bledy) else "częściowo",
                   "uwagi": "API z kluczem" if sposoby == {"API"} else ("pliki CSV bez klucza" if sposoby == {"CSV"} else "API i pliki CSV")})

    print("Cboe: VIX, put/call, łańcuch SPX…")
    vix, zrodlo_vix = pobierz_vix()
    zrodla.append({"nazwa": "Cboe: historia VIX", "opis": zrodlo_vix, "ostatnia": vix.index[-1].strftime("%Y-%m-%d"), "stan": "ok"})
    archiwum = aktualizuj_archiwum_putcall(teraz.date())
    putcall = pd.DataFrame(archiwum["wiersze"], columns=archiwum["kolumny"])
    putcall.index = pd.to_datetime(putcall.pop("data"))
    putcall = putcall.astype(float)
    zrodla.append({"nazwa": "Cboe: dzienne statystyki opcji", "opis": "put/call całej giełdy, akcji, indeksów i SPX (archiwum od 7.10.2019)",
                   "ostatnia": putcall.index[-1].strftime("%Y-%m-%d") if len(putcall) else None, "stan": "ok" if len(putcall) else "błąd"})
    lancuch = None
    try:
        lancuch = analizuj_lancuch(pobierz_lancuch("_SPX"))
        zrodla.append({"nazwa": "Cboe: łańcuch opcji SPX", "opis": f"{lancuch['kontraktow']} kontraktów (gamma, skośność, otwarte pozycje)",
                       "ostatnia": lancuch["data"], "stan": "ok"})
    except Exception as blad:  # noqa: BLE001
        bledy.append(f"Cboe łańcuch SPX: {blad}")
        zrodla.append({"nazwa": "Cboe: łańcuch opcji SPX", "opis": "gamma, skośność, otwarte pozycje", "ostatnia": None, "stan": "błąd"})
    arch = aktualizuj_archiwum_opcji(lancuch, sesje[-1].strftime("%Y-%m-%d"))
    opcje_arch = None
    if arch:
        opcje_arch = pd.DataFrame(arch, columns=["data", "gexMldUsd", "skos25d", "pcOi60", "iv30", "iv90", "spx"])
        opcje_arch.index = pd.to_datetime(opcje_arch.pop("data"))
        opcje_arch = opcje_arch.astype(float)

    print("VaR (metoda karty VaR)…")
    var = None
    try:
        modul = zaladuj_var()
        spy = yahoo["SPY"][["open", "high", "low", "close"]].copy()
        spy["data"] = spy.index.strftime("%Y-%m-%d")
        spy["zwrot"] = spy["close"].pct_change()
        wynik_var = modul.oblicz_var_kroczaco(spy.reset_index(drop=True), 1, 21, 1, 0.99, 756, 756)
        wynik_var.index = pd.to_datetime(wynik_var["data"])
        var = wynik_var
        zrodla.append({"nazwa": "Karta VaR", "opis": "oblicz_var_kroczaco() z src/var/var.py: SPY, 99%, okna 756 sesji, horyzonty 1 i 21",
                       "ostatnia": var.index[-1].strftime("%Y-%m-%d"), "stan": "ok"})
    except Exception as blad:  # noqa: BLE001
        bledy.append(f"VaR: {blad}")
    return {"sesje": sesje, "gspc": gspc, "yahoo": yahoo, "fred": fred, "vix": vix, "putcall": putcall,
            "lancuch": lancuch, "opcje_arch": opcje_arch, "var": var, "bledy": bledy, "zrodla": zrodla}


def policz_wskazniki(k: dict) -> dict:
    wyniki = {}
    for d in DEFINICJE:
        try:
            wyniki[d["id"]] = LICZ[d["id"]](k)
        except Exception as blad:  # noqa: BLE001 (brak jednej serii nie może zatrzymać całej karty)
            k["bledy"].append(f"wskaźnik {d['id']}: {type(blad).__name__}: {blad}")
            wyniki[d["id"]] = None
    return wyniki


#_______________________________________________________________________________
# okna 3–5: Makro, Rynek, Technika (lista wskaźników grupy)
#_______________________________________________________________________________
def element_wskazniki(k: dict, wyniki: dict) -> list[dict]:
    """Orkiestrator okien grup: każdy wskaźnik jako gotowy wiersz (tekst, ocena, wykresik) i,
    dla ocenianych, tabela: jak zachowywał się S&P 500 po sesjach z każdą oceną tego wskaźnika."""
    import pandas as pd

    sesja = k["sesje"][-1]
    poprzednia = k["sesje"][-2]
    przyszle = przyszle_zwroty(k["gspc"]["close"])
    lista = []
    for d in DEFINICJE:
        w = wyniki.get(d["id"])
        wiersz = {"id": d["id"], "grupa": d["grupa"], "nazwa": d["nazwa"], "oceniany": d["maks"] > 0,
                  "waga": d["waga"], "maks": d["maks"], "opis": d["opis"], "regula": d.get("regula", ""),
                  "zrodlo": d["zrodlo"], "czestotliwosc": d["czestotliwosc"]}
        if w is None or w["seria"] is None or w["seria"].dropna().empty:
            wiersz.update({"tekst": "brak danych", "pod": "nie udało się pobrać albo policzyć", "stan": "brak",
                           "punkty": None, "historia": []})
            lista.append(wiersz)
            continue
        p = p_wczoraj = None
        historycznie = None
        if d["maks"] and w["punkty"] is not None:
            pk = w["punkty"]
            p = pk.get(sesja) if sesja in pk.index else None
            p_wczoraj = pk.get(poprzednia) if poprzednia in pk.index else None
            p = None if p is None or pd.isna(p) else int(p)
            p_wczoraj = None if p_wczoraj is None or pd.isna(p_wczoraj) else int(p_wczoraj)
            df = pd.concat([pd.DataFrame({"p": pk}), przyszle], axis=1, sort=True).dropna(subset=["p"])
            if len(df):
                historycznie = {"od": df.index[0].strftime("%Y-%m-%d"),
                                "wiersze": [{"punkty": int(pp), **statystyki_przyszlosci(x)} for pp, x in df.groupby("p")]}
        percentyl = w.get("percentyl")
        okno = w.get("oknoPercentyla")
        if percentyl is None and "percentyl" not in w:
            lat = 10 if d["grupa"] == "makro" else 5
            percentyl = percentyl_ostatniej(w["natywna"], lat)
            okno = f"{lat} lat"
        historia = co_tydzien(w["natywna"], LAT_HISTORII_WSKAZNIKA)
        wiersz.update({
            "tekst": w["tekst"], "pod": w["pod"], "zmiana": w["zmiana"], "data": w["data"],
            "punkty": p, "punktyPoprzednio": p_wczoraj, "stan": stan_z_punktow(p, d["maks"]) if d["maks"] else "info",
            "percentyl": round(percentyl, 0) if percentyl is not None and math.isfinite(percentyl) else None,
            "oknoPercentyla": okno if percentyl is not None else None,
            "historia": lista_punktow(historia, 4),
            "historycznie": historycznie,
        })
        lista.append(wiersz)
    return lista


def _okno_grupy(grupa: str, tytul: str, opis: str) -> str:
    """Jeden szablon okna dla trzech grup; różnią się tylko id, tytułem i opisem."""
    return f"""
<section class="karta t-okno t-k4 st-okno-grupa" data-grupa="{grupa}">
  <header class="t-naglowek"><h2>{tytul}</h2><div class="t-akcje"><span id="st-wynik-{grupa}" class="st-czas"></span></div></header>
  <div class="t-tresc st-tresc-lista">
    <div id="st-lista-{grupa}" class="st-lista"><div class="st-pusto">Wczytywanie danych…</div></div>
    <p class="opis">{opis} Każdy wiersz: nazwa, bieżąca wartość, ocena (od -2 do +2; „i” to wskaźnik informacyjny poza sygnałem) i wykresik z ostatniego roku. Kliknij wiersz, żeby zobaczyć, jak go czytać, regułę oceny, wykres z 3 lat i to, jak zachowywał się S&amp;P 500 po sesjach z każdą oceną tego wskaźnika.</p>
  </div>
</section>
"""


HTML_FRAGMENT_MAKRO = _okno_grupy(
    "makro", "Makro",
    "Gospodarka USA z danych FRED: wzrost (PKB, GDPNow, CFNAI), rynek pracy, inflacja i stopy procentowe. Dane miesięczne i kwartalne wchodzą do historii sygnału dopiero po typowym opóźnieniu publikacji, żeby wykres nie korzystał z danych, których danego dnia jeszcze nie znano.")
HTML_FRAGMENT_RYNEK = _okno_grupy(
    "rynek", "Rynek",
    "Ryzyko, zmienność i nastroje: opcje (put/call z dziennych statystyk Cboe, łańcuch SPX), VIX i jego struktura, spready kredytowe, warunki finansowe, rotacja między sektorami i ucieczka do obligacji.")
HTML_FRAGMENT_TECHNIKA = _okno_grupy(
    "technika", "Technika",
    "S&amp;P 500 (indeks ^GSPC) z notowań dziennych: trend (średnie 50 i 200 sesji, ADX, MACD), skrajności (RSI Wildera, wstęgi Bollingera), spadek od szczytu i VaR policzony metodą karty VaR.")

APP_JS_GRUPY = r"""
// ===========================================================================
// ELEMENT: okna 3–5 „Makro", „Rynek", „Technika" (jedna funkcja, trzy grupy)
// ===========================================================================
function stWierszWskaznika(w) {
  const otwarty = st.otwarte.has(w.id);
  const pkt = w.oceniany
    ? `<span class="st-pkt" title="${stEsc(`Ocena ${w.punkty == null ? "brak" : stZnak(w.punkty, 0)} w skali od -${w.maks} do +${w.maks}, waga ${stLiczba(w.waga, 1)}: ${ST_OPIS_STANU[w.stan] || ""}`)}">${w.punkty == null ? "–" : stZnak(w.punkty, 0)}</span>`
    : '<span class="st-pkt st-pkt-info" title="Wskaźnik informacyjny: pokazany dla kontekstu, nie wchodzi do sygnału">i</span>';
  const pod = [w.pod, w.zmiana].filter(Boolean).join(" · ");
  return `<div class="st-wiersz st-${w.stan}${otwarty ? " otwarty" : ""}" data-id="${w.id}" tabindex="0" role="button" aria-expanded="${otwarty}">
      <span class="st-nazwa">${stEsc(w.nazwa)}</span>
      <span class="st-wartosc">${stEsc(w.tekst)}</span>
      ${pkt}
      <span class="st-iskra">${stIskra(w.historia)}</span>
      <span class="st-pod">${stEsc(pod)}${w.data ? ` <span class="st-data">· ${stEsc(w.data)}</span>` : ""}</span>
    </div>${otwarty ? stSzczegoly(w) : ""}`;
}

function stSzczegoly(w) {
  const h = w.historycznie;
  const tabela = h && h.wiersze && h.wiersze.length
    ? `<table class="st-hist"><thead><tr>
        <th title="Ocena wskaźnika danego dnia">Ocena</th>
        <th class="t-liczba" title="Ile sesji w historii miało taką ocenę">Sesji</th>
        <th class="t-liczba" title="W ilu procentach przypadków S&P 500 spadł w ciągu kolejnych 63 sesji (ok. 3 mies.) o 10% lub więcej">Spadek ≥10%</th>
        <th class="t-liczba" title="Średnia zmiana S&P 500 w kolejnych 63 sesjach">Zwrot 3 mies.</th>
        <th class="t-liczba" title="Średnie największe obsunięcie S&P 500 w kolejnych 63 sesjach">Obsunięcie</th>
      </tr></thead><tbody>${h.wiersze.map((r) => `<tr class="${r.punkty === w.punkty ? "st-biezacy" : ""}">
        <td>${stZnak(r.punkty, 0)}${r.punkty === w.punkty ? " (dziś)" : ""}</td><td class="t-liczba">${stLiczba(r.dni, 0)}</td>
        <td class="t-liczba">${stProc(r.p10, 0)}</td><td class="t-liczba ${stKlasaZnaku(r.sr63)}">${stProcZnak(r.sr63, 1)}</td>
        <td class="t-liczba">${stProc(r.dd63, 1)}</td></tr>`).join("")}</tbody></table>
      <div class="st-przypis">Jak zachowywał się S&amp;P 500 po sesjach z każdą oceną tego wskaźnika, od ${stDataPl(h.od)}. Okresy po sobie się nakładają, więc to opis historii, a nie gwarancja.</div>`
    : "";
  return `<div class="st-szczegoly" data-dla="${w.id}">
      <div class="st-opis-tekst">${stEsc(w.opis)}</div>
      <dl class="st-fakty">
        ${w.oceniany ? `<div><dt>Reguła oceny</dt><dd>${stEsc(w.regula)}</dd></div>` : ""}
        ${w.percentyl != null ? `<div><dt>Percentyl</dt><dd>${stLiczba(w.percentyl, 0)} (okno ${stEsc(w.oknoPercentyla)}): taki odsetek odczytów z tego okresu był niższy albo równy dzisiejszemu</dd></div>` : ""}
        <div><dt>Dane</dt><dd>${stEsc(w.data || "–")}, częstotliwość ${stEsc(w.czestotliwosc)}</dd></div>
        <div><dt>Źródło</dt><dd><a href="${stEsc(w.zrodlo.url)}" target="_blank" rel="noopener">${stEsc(w.zrodlo.nazwa)}</a></dd></div>
      </dl>
      <div class="st-wykres-maly">${stWykresMaly(w.historia)}</div>
      ${tabela}
    </div>`;
}

function stRysujGrupe(grupa) {
  const lista = st.stan.wskazniki.filter((w) => w.grupa === grupa);
  const ocenione = lista.filter((w) => w.oceniany);
  const info = lista.filter((w) => !w.oceniany);
  const g = st.stan.sygnal.grupy.find((x) => x.id === grupa);
  stEl(`st-wynik-${grupa}`).innerHTML = g
    ? `<b class="${stKlasaZnaku(g.wynik)}">${stZnak(g.wynik, 0)}</b> · ${g.plus} za · ${g.minus} przeciw`
    : "";
  stEl(`st-lista-${grupa}`).innerHTML =
    ocenione.map(stWierszWskaznika).join("") +
    (info.length ? `<div class="st-podzial">Informacyjne, poza sygnałem (${info.length})</div>${info.map(stWierszWskaznika).join("")}` : "");
}

function stInicjujGrupy() {
  for (const grupa of Object.keys(ST_GRUPY)) {
    const host = stEl(`st-lista-${grupa}`);
    const przelacz = (wiersz) => {
      const id = wiersz.dataset.id;
      if (st.otwarte.has(id)) st.otwarte.delete(id);
      else st.otwarte.add(id);
      stRysujGrupe(grupa);
      const nowy = host.querySelector(`.st-wiersz[data-id="${id}"]`);
      if (nowy) nowy.focus({ preventScroll: true });
    };
    host.addEventListener("click", (e) => {
      if (e.target.closest("a, .st-szczegoly")) return;
      const wiersz = e.target.closest(".st-wiersz");
      if (wiersz) przelacz(wiersz);
    });
    host.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const wiersz = e.target.closest(".st-wiersz");
      if (!wiersz) return;
      e.preventDefault();
      przelacz(wiersz);
    });
  }
}
"""


#_______________________________________________________________________________
# okno 1: Sygnał rynku (wynik, grupy, nastroje)
#_______________________________________________________________________________
def element_sygnal(k: dict, wyniki: dict, zlozony, nastroje_df, lista: list[dict]) -> tuple[dict, dict]:
    """Orkiestrator okna sygnału: wynik złożony z ostatniej sesji, grupy, wkład wskaźników,
    zmiany ocen i indeks nastrojów."""
    import pandas as pd

    w = zlozony["wynik"].dropna()
    ost = float(w.iloc[-1])
    klucz, etykieta = poziom(ost)

    def zmiana(n):
        return round(ost - float(w.iloc[-1 - n]), 1) if len(w) > n else None

    grupy = []
    for g, waga in WAGI_GRUP.items():
        wiersze = [x for x in lista if x["grupa"] == g and x["oceniany"]]
        grupy.append({
            "id": g, "nazwa": NAZWY_GRUP[g], "waga": waga,
            "wynik": round(float(zlozony[g].iloc[-1]), 1) if pd.notna(zlozony[g].iloc[-1]) else None,
            "plus": sum(1 for x in wiersze if (x["punkty"] or 0) > 0),
            "minus": sum(1 for x in wiersze if (x["punkty"] or 0) < 0),
            "zero": sum(1 for x in wiersze if x["punkty"] == 0),
            "brak": sum(1 for x in wiersze if x["punkty"] is None),
        })
    # wkład = punkty / maks × waga wskaźnika / suma wag grupy × waga grupy × 100
    sumy = {g: sum(d["waga"] for d in DEFINICJE if d["grupa"] == g and d["maks"]) for g in WAGI_GRUP}
    wklad = []
    for x in lista:
        if x["oceniany"] and x["punkty"] is not None:
            wklad.append({"id": x["id"], "nazwa": x["nazwa"], "tekst": x["tekst"], "punkty": x["punkty"], "maks": x["maks"],
                          "wklad": round(x["punkty"] / x["maks"] * x["waga"] / sumy[x["grupa"]] * WAGI_GRUP[x["grupa"]] * 100, 1)})
    zmienione = [{"id": x["id"], "nazwa": x["nazwa"], "bylo": x["punktyPoprzednio"], "jest": x["punkty"]}
                 for x in lista if x["oceniany"] and x["punkty"] is not None and x["punktyPoprzednio"] is not None
                 and x["punkty"] != x["punktyPoprzednio"]]
    sygnal = {
        "wynik": round(ost, 1), "poziom": klucz, "etykieta": etykieta,
        "zmiana": {"1": zmiana(1), "5": zmiana(5), "21": zmiana(21)},
        "grupy": grupy,
        "liczniki": {"plus": sum(g["plus"] for g in grupy), "minus": sum(g["minus"] for g in grupy),
                     "zero": sum(g["zero"] for g in grupy), "brak": sum(g["brak"] for g in grupy)},
        "wklad": {"plus": sorted([x for x in wklad if x["wklad"] > 0], key=lambda x: -x["wklad"]),
                  "minus": sorted([x for x in wklad if x["wklad"] < 0], key=lambda x: x["wklad"])},
        "zmienioneOceny": zmienione,
        "progi": [{"od": g, "poziom": kl, "etykieta": et} for g, kl, et in POZIOMY],
        "wagiGrup": WAGI_GRUP,
    }
    srednia = nastroje_df.mean(axis=1, skipna=True).where(nastroje_df.notna().sum(axis=1) >= 5)
    s = srednia.dropna()
    nastroje = {"wartosc": None}
    if len(s):
        v = float(s.iloc[-1])
        kl, et = poziom(v, POZIOMY_NASTROJOW)
        nastroje = {
            "wartosc": round(v, 1), "poziom": kl, "etykieta": et,
            "zmiana5": round(v - float(s.iloc[-6]), 1) if len(s) > 5 else None,
            "zmiana21": round(v - float(s.iloc[-22]), 1) if len(s) > 21 else None,
            "skladniki": [{"id": kol, "nazwa": k["nastroje_nazwy"][kol],
                           "percentyl": round(float(nastroje_df[kol].iloc[-1]), 0) if pd.notna(nastroje_df[kol].iloc[-1]) else None}
                          for kol in nastroje_df.columns],
        }
    return sygnal, nastroje


LICZBA_OCENIANYCH = sum(1 for d in DEFINICJE if d["maks"])

HTML_FRAGMENT_SYGNAL = f"""
<section class="karta t-okno t-k4 st-okno-sygnal">
  <header class="t-naglowek"><h2>Sygnał rynku</h2><div class="t-akcje"><span id="st-sesja" class="st-czas"></span></div></header>
  <div class="t-tresc">
    <div id="st-sygnal" class="st-sygnal"><div class="st-pusto">Wczytywanie danych…</div></div>
    <p class="opis">Sygnał to średnia ważona ocen {LICZBA_OCENIANYCH} wskaźników z trzech grup (makro 30%, rynek 35%, technika 35%), w skali od -100 do +100. Każdy wskaźnik dostaje od -2 do +2 punktów według stałej reguły opisanej w jego rozwinięciu, a pasek pod etykietą pokazuje pięć poziomów: od silnie negatywnego (poniżej -40) do silnie pozytywnego (od +40). Sygnał opisuje warunki i ryzyko dla inwestora indeksowego S&amp;P 500, a nie prognozę zwrotu: im jest niższy, tym częściej w historii przychodził spadek indeksu o 10% i więcej w ciągu 3 miesięcy. Pasek nastrojów (od strachu do chciwości) to osobny indeks z siedmiu składników rynkowych.</p>
  </div>
</section>
"""

APP_JS_SYGNAL = r"""
// ===========================================================================
// ELEMENT: okno 1 „Sygnał rynku"
// ===========================================================================
// Statystyki z tabeli skuteczności (cała historia) dla bieżącego poziomu sygnału.
function stHistoriaPoziomu(poziom) {
  const okres = st.stan.skutecznosc && st.stan.skutecznosc.okresy && st.stan.skutecznosc.okresy[0];
  if (!okres) return null;
  return { wiersz: okres.wiersze.find((w) => w.poziom === poziom), wszystkie: okres.wiersze.find((w) => w.poziom === "wszystkie"), od: okres.od };
}

function stRysujSygnal() {
  const s = st.stan.sygnal;
  const n = st.stan.nastroje || {};
  const x = (v) => (Math.max(-100, Math.min(100, v)) + 100) / 2;
  const pasma = [[-100, -40, "silnie-negatywny"], [-40, -15, "negatywny"], [-15, 15, "neutralny"], [15, 40, "pozytywny"], [40, 100, "silnie-pozytywny"]]
    .map(([a, b, k]) => `<i class="st-pasmo st-p-${k}" style="left:${x(a)}%;width:${x(b) - x(a)}%" title="${ST_ETYKIETY[k]}: od ${a} do ${b}"></i>`)
    .join("");
  const zm = s.zmiana || {};
  const h = stHistoriaPoziomu(s.poziom);
  const hist = h && h.wiersz
    ? `<div class="st-historycznie" title="${stEsc(`Policzone na sesjach od ${stDataPl(h.od)}: dla każdej sesji z takim samym poziomem sygnału sprawdzamy, co działo się z S&P 500 przez kolejne 63 sesje (ok. 3 miesiące). Zależność nie jest stała w czasie, szczegóły w oknie „Skuteczność sygnału”.`)}">Po sesjach z takim sygnałem S&amp;P 500 spadał w ciągu 3 mies. o 10% lub więcej w <b>${stProc(h.wiersz.p10, 0)}</b> przypadków (przeciętnie ${stProc(h.wszystkie.p10, 0)}); średni zwrot 3 mies. ${stProcZnak(h.wiersz.sr63, 1)}.</div>`
    : "";
  const grupy = s.grupy
    .map((g) => {
      const szer = g.wynik == null ? 0 : Math.min(50, Math.abs(g.wynik) / 2);
      const lewo = g.wynik == null || g.wynik >= 0 ? 50 : 50 - szer;
      const dymek = `${g.nazwa}: średnia ważona ocen wskaźników grupy, od -100 do +100. Waga grupy w sygnale: ${stLiczba(g.waga * 100, 0)}%.`;
      return `<div class="st-grupa" title="${stEsc(dymek)}">
        <span class="st-grupa-nazwa">${g.nazwa}</span>
        <span class="st-belka"><i class="${(g.wynik || 0) >= 0 ? "st-belka-plus" : "st-belka-minus"}" style="left:${lewo}%;width:${szer}%"></i></span>
        <b class="${stKlasaZnaku(g.wynik)}">${stZnak(g.wynik, 0)}</b>
        <small>${g.plus} za · ${g.minus} przeciw · ${g.zero} neutralnie${g.brak ? ` · ${g.brak} bez danych` : ""}</small></div>`;
    })
    .join("");
  let nastroje = "";
  if (n.wartosc != null) {
    const skladniki = (n.skladniki || []).map((x) => `${x.nazwa}: ${x.percentyl == null ? "brak danych" : stLiczba(x.percentyl, 0)}`).join("\n");
    const dymek = `Indeks nastrojów od 0 (skrajny strach) do 100 (skrajna chciwość): średnia z siedmiu składników, każdy jako percentyl z ostatnich 2 lat, gdzie wysoko oznacza chciwość. Wzorowany na znanym indeksie strachu i chciwości, liczony z danych tej karty.\n\n${skladniki}`;
    nastroje = `<div class="st-nastroje" title="${stEsc(dymek)}">
      <div class="st-nastroje-gora"><span>Nastroje</span><b class="st-n-${n.poziom}">${stLiczba(n.wartosc, 0)} · ${stEsc(n.etykieta)}</b><small>tydzień ${stZnak(n.zmiana5, 0)} · miesiąc ${stZnak(n.zmiana21, 0)}</small></div>
      <div class="st-nastroje-skala"><i style="left:${Math.max(0, Math.min(100, n.wartosc))}%"></i></div>
      <div class="st-skala-opis"><span>strach</span><span>chciwość</span></div></div>`;
  }
  stEl("st-sesja").textContent = stDataPl(st.stan.sesja);
  stEl("st-sesja").title = `Ostatnia sesja w danych: ${stDataPl(st.stan.sesja)}`;
  stEl("st-sygnal").innerHTML = `
    <div class="st-odznaka st-p-${s.poziom}"><span>${stEsc(s.etykieta)}</span><b>${stZnak(s.wynik, 0)}</b><small>w skali ±100</small></div>
    <div class="st-skala-ramka"><div class="st-skala">${pasma}</div><i class="st-znacznik-skali" style="left:${x(s.wynik)}%"></i></div>
    <div class="st-skala-opis"><span>-100</span><span>0</span><span>+100</span></div>
    <div class="st-zmiany">Zmiana: sesja <b class="${stKlasaZnaku(zm["1"])}">${stZnak(zm["1"], 0)}</b> · tydzień <b class="${stKlasaZnaku(zm["5"])}">${stZnak(zm["5"], 0)}</b> · miesiąc <b class="${stKlasaZnaku(zm["21"])}">${stZnak(zm["21"], 0)}</b></div>
    ${hist}
    <div class="st-grupy">${grupy}</div>
    ${nastroje}`;
}
"""


#_______________________________________________________________________________
# okno 2: Ocena dnia (pisze ją rutyna Claude do data/stan-rynku/ocena.json)
#_______________________________________________________________________________
POLA_OCENY = ["data", "sesja", "wynik", "poziomLiczbowy", "sygnal", "tytul", "opis", "za", "przeciw", "naCoPatrzec"]


def element_ocena_sprawdz() -> list[str]:
    """Orkiestrator okna oceny po stronie Pythona: sprawdza data/stan-rynku/ocena.json, które pisze
    rutyna Claude (format w docs/stan-rynku/instrukcja-oceny.md). Zwraca listę błędów."""
    bledy: list[str] = []
    if not SCIEZKA_OCENA.exists():
        return ["brak pliku data/stan-rynku/ocena.json"]
    try:
        ocena = json.loads(SCIEZKA_OCENA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as blad:
        return [f"ocena.json to nie jest poprawny JSON: {blad}"]
    stan = json.loads(SCIEZKA_STAN.read_text(encoding="utf-8")) if SCIEZKA_STAN.exists() else {}
    poziomy = {kl for _, kl, _ in POZIOMY}
    wpisy = [("aktualna", ocena.get("aktualna"))] + [(f"archiwum[{i}]", w) for i, w in enumerate(ocena.get("archiwum") or [])]
    if not isinstance(ocena.get("aktualna"), dict):
        bledy.append("brak obiektu „aktualna”")
    for nazwa, w in wpisy:
        if not isinstance(w, dict):
            continue
        for pole in POLA_OCENY:
            if pole not in w:
                bledy.append(f"{nazwa}: brak pola {pole}")
        for pole in ("data", "sesja"):
            if pole in w and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(w[pole])):
                bledy.append(f"{nazwa}: {pole} musi mieć postać RRRR-MM-DD")
        for pole in ("sygnal", "poziomLiczbowy"):
            if pole in w and w[pole] not in poziomy:
                bledy.append(f"{nazwa}: {pole} spoza listy {sorted(poziomy)}")
        if w.get("sygnal") and w.get("poziomLiczbowy") and w["sygnal"] != w["poziomLiczbowy"] and not str(w.get("uzasadnienieRoznicy", "")).strip():
            bledy.append(f"{nazwa}: sygnał różni się od poziomu liczbowego, a brak pola uzasadnienieRoznicy")
        if len(str(w.get("tytul", ""))) > 110:
            bledy.append(f"{nazwa}: tytuł dłuższy niż 110 znaków")
        if not 150 <= len(str(w.get("opis", ""))) <= 1600:
            bledy.append(f"{nazwa}: opis powinien mieć od 150 do 1600 znaków")
        for pole, od, do in (("za", 1, 5), ("przeciw", 1, 5), ("naCoPatrzec", 0, 5)):
            if pole in w and (not isinstance(w[pole], list) or not od <= len(w[pole]) <= do):
                bledy.append(f"{nazwa}: {pole} musi być listą od {od} do {do} punktów")
        tekst = json.dumps(w, ensure_ascii=False)
        if "\u2014" in tekst:
            bledy.append(f"{nazwa}: długa kreska (U+2014) jest zakazana (CLAUDE.md); użyj przecinka, dwukropka albo kropki")
    a = ocena.get("aktualna") or {}
    if stan and a:
        if a.get("sesja") != stan.get("sesja"):
            bledy.append(f"aktualna.sesja {a.get('sesja')} nie zgadza się z sesją w stan.json ({stan.get('sesja')})")
        if a.get("poziomLiczbowy") != stan.get("sygnal", {}).get("poziom"):
            bledy.append("aktualna.poziomLiczbowy nie zgadza się z sygnal.poziom w stan.json")
        if isinstance(a.get("wynik"), (int, float)) and abs(a["wynik"] - stan.get("sygnal", {}).get("wynik", 0)) > 0.05:
            bledy.append("aktualna.wynik nie zgadza się z sygnal.wynik w stan.json")
    if len(ocena.get("archiwum") or []) > 60:
        bledy.append("archiwum dłuższe niż 60 ocen (najstarsze usuń)")
    return bledy


HTML_FRAGMENT_OCENA = """
<section class="karta t-okno t-k8 t-naroznik st-okno-ocena">
  <header class="t-naglowek"><h2>Ocena dnia</h2><div class="t-akcje"><span id="st-ocena-czas" class="st-czas"></span></div></header>
  <div class="t-tresc">
    <div id="st-ocena" class="st-ocena"><div class="st-pusto">Wczytywanie danych…</div></div>
    <p class="opis">W pełnej platformie ocenę pisze codziennie rutyna Claude po aktualizacji danych: zaczyna od wyniku liczbowego, czyta wskaźniki, ogólny pogląd rynkowy i wiadomości z dnia, i może przesunąć sygnał najwyżej o jeden poziom, zawsze z uzasadnieniem. W tej statycznej wersji pokazowej oceny się nie odświeżają: gdy ocena nie dotyczy bieżącej sesji, okno pokazuje opis policzony automatycznie z liczb. Starsze oceny są w archiwum na dole okna.</p>
  </div>
</section>
"""

APP_JS_OCENA = r"""
// ===========================================================================
// ELEMENT: okno 2 „Ocena dnia" (data/stan-rynku/ocena.json pisane przez rutynę Claude)
// ===========================================================================
function stAkapity(tekst) {
  return String(tekst || "").split(/\n{2,}/).map((a) => `<p>${stTekst(a)}</p>`).join("");
}
function stPunkty(lista) {
  return (lista || []).map((x) => `<li>${stTekst(x)}</li>`).join("");
}
function stOpisAutomatyczny() {
  return `<ul class="st-auto">${(st.stan.opisAutomatyczny || []).map((z) => `<li>${stEsc(z)}</li>`).join("")}</ul>`;
}
function stArchiwumOcen() {
  const archiwum = (st.ocena && st.ocena.archiwum) || [];
  if (!archiwum.length) return "";
  const wpisy = archiwum.slice(0, 30).map((a) => `<details class="st-archiwum-wpis"><summary><span class="st-odznaka-mala st-p-${stEsc(a.sygnal)}">${ST_ETYKIETY[a.sygnal] || stEsc(a.sygnal)}</span><b>${stDataPl(a.sesja)}</b>${stTekst(a.tytul)}</summary>${stAkapity(a.opis)}</details>`);
  return `<details class="st-archiwum"><summary>Poprzednie oceny (${archiwum.length})</summary>${wpisy.join("")}</details>`;
}

function stRysujOcene() {
  const host = stEl("st-ocena");
  const s = st.stan;
  const o = st.ocena && st.ocena.aktualna;
  const czas = stEl("st-ocena-czas");
  if (!o || o.sesja !== s.sesja) {
    czas.textContent = "opis automatyczny";
    const powod = o
      ? `Ostatnia ocena Claude (${stDataPl(o.data)}) dotyczy sesji ${stDataPl(o.sesja)}, a dane są już z sesji ${stDataPl(s.sesja)}. Do czasu nowej oceny poniżej opis policzony automatycznie z liczb.`
      : "Nie ma jeszcze oceny Claude dla tej sesji. Poniżej opis policzony automatycznie z liczb.";
    host.innerHTML = `<div class="st-uwaga-stara">${powod}</div>${stOpisAutomatyczny()}${stArchiwumOcen()}`;
    return;
  }
  czas.textContent = `Claude · ${stDataPl(o.data)}`;
  const rozni = o.sygnal !== s.sygnal.poziom;
  host.innerHTML = `
    <div class="st-ocena-gora"><span class="st-odznaka-mala st-p-${stEsc(o.sygnal)}">${ST_ETYKIETY[o.sygnal] || stEsc(o.sygnal)}</span><h3>${stTekst(o.tytul)}</h3></div>
    ${rozni ? `<div class="st-roznica">Ocena różni się od wyniku liczbowego (${ST_ETYKIETY[s.sygnal.poziom]}, ${stZnak(s.sygnal.wynik, 0)}): ${stTekst(o.uzasadnienieRoznicy || "")}</div>` : ""}
    <div class="st-ocena-tekst">${stAkapity(o.opis)}</div>
    <div class="st-za-przeciw">
      <div class="st-za"><h4>Sprzyja indeksowi</h4><ul>${stPunkty(o.za)}</ul></div>
      <div class="st-przeciw"><h4>Ryzyka</h4><ul>${stPunkty(o.przeciw)}</ul></div>
    </div>
    ${o.naCoPatrzec && o.naCoPatrzec.length ? `<div class="st-na-co"><h4>Na co patrzeć</h4><ul>${stPunkty(o.naCoPatrzec)}</ul></div>` : ""}
    <details class="st-auto-szczegoly"><summary>Opis automatyczny z liczb</summary>${stOpisAutomatyczny()}</details>
    ${stArchiwumOcen()}`;
}
"""


#_______________________________________________________________________________
# okno 6: Historia sygnału
#_______________________________________________________________________________
def element_historia(k: dict, zlozony, nastroje_seria) -> dict:
    """Orkiestrator wykresu historii: dzienne punkty z ostatnich 3 lat i tygodniowe od początku."""
    import pandas as pd

    df = pd.DataFrame({
        "wynik": zlozony["wynik"], "makro": zlozony["makro"], "rynek": zlozony["rynek"], "technika": zlozony["technika"],
        "nastroje": nastroje_seria, "spx": k["gspc"]["close"],
    }).dropna(subset=["wynik"])
    od = df.index[-1] - pd.DateOffset(years=LAT_HISTORII_DZIENNEJ)

    def wiersze(x):
        return [[t.strftime("%Y-%m-%d")] + [None if pd.isna(v) else round(float(v), 1 if i < 5 else 2) for i, v in enumerate(r)]
                for t, r in zip(x.index, x.to_numpy())]

    tygodniowe = df.resample("W-FRI").last().dropna(subset=["wynik"])
    return {"kolumny": ["data", "wynik", "makro", "rynek", "technika", "nastroje", "spx"],
            "dzienna": wiersze(df[df.index >= od]), "tygodniowa": wiersze(tygodniowe)}


HTML_FRAGMENT_HISTORIA = """
<section class="karta t-okno t-k7 st-okno-historia">
  <header class="t-naglowek"><h2>Historia sygnału</h2><div class="t-akcje">
    <span id="st-zakres" class="st-przelacznik" role="group" aria-label="Zakres wykresu">
      <button type="button" class="t-mini" data-zakres="1r">1 rok</button>
      <button type="button" class="t-mini aktywny" data-zakres="3l">3 lata</button>
      <button type="button" class="t-mini" data-zakres="max" title="Punkty tygodniowe od początku historii sygnału">całość</button>
    </span>
    <label class="st-check" title="Dorysuj wyniki trzech grup: makro, rynek i technika"><input id="st-pokaz-grupy" type="checkbox" /> grupy</label>
  </div></header>
  <div class="t-tresc">
    <div id="st-wykres" class="st-wykres"><div class="st-pusto">Wczytywanie danych…</div></div>
    <div id="st-wykres-legenda" class="st-legenda"></div>
    <p class="opis">Górny panel: S&amp;P 500 w skali logarytmicznej (równe odległości to równe zmiany procentowe), a pod nim kolorowy pasek z poziomem sygnału każdego dnia. Dolny panel: wynik sygnału od -100 do +100 na tle pasm pięciu poziomów i indeks nastrojów (przerywana linia, 0–100 przeliczone tak, że 50 wypada na zerze). Historia jest liczona tymi samymi regułami co dziś, a dane makro wchodzą z opóźnieniem publikacji. Najedź na wykres, żeby zobaczyć wartości z danego dnia.</p>
  </div>
</section>
"""

APP_JS_HISTORIA = r"""
// ===========================================================================
// ELEMENT: okno 6 „Historia sygnału" (ręcznie rysowany SVG, bez bibliotek)
// ===========================================================================
const ST_KLASY_GRUP = { makro: "st-l-makro", rynek: "st-l-rynek", technika: "st-l-technika" };

function stDaneHistorii() {
  const h = st.stan.historia;
  let wiersze = h.tygodniowa;
  if (st.zakres !== "max") {
    const d = new Date(h.dzienna[h.dzienna.length - 1][0] + "T00:00:00Z");
    d.setUTCFullYear(d.getUTCFullYear() - (st.zakres === "1r" ? 1 : 3));
    const od = d.toISOString().slice(0, 10);
    wiersze = h.dzienna.filter((w) => w[0] >= od);
  }
  return wiersze.map((w) => Object.fromEntries(h.kolumny.map((k, i) => [k, w[i]])));
}

function stRysujHistorie() {
  const host = stEl("st-wykres");
  const dane = stDaneHistorii();
  if (dane.length < 2) {
    host.innerHTML = '<div class="st-pusto">Za mało danych do wykresu.</div>';
    return;
  }
  const W = 1000, H = 420, L = 6, R = 60, T = 10, HA = 190, PASEK = 8;
  const TB = T + HA + PASEK + 26;
  const HB = H - TB - 24;
  const n = dane.length;
  const X = (i) => L + (i / (n - 1)) * (W - L - R);
  const spx = dane.map((d) => d.spx);
  const dodatnie = spx.filter((v) => v > 0);
  const lmin = Math.log(Math.min(...dodatnie)), lmax = Math.log(Math.max(...dodatnie));
  const YA = (v) => T + (1 - (Math.log(v) - lmin) / (lmax - lmin || 1)) * HA;
  const YB = (v) => TB + (1 - (Math.max(-100, Math.min(100, v)) + 100) / 200) * HB;
  const sciezka = (wartosci, Y) => {
    let d = "";
    let ciagla = false;
    wartosci.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) { ciagla = false; return; }
      d += `${ciagla ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
      ciagla = true;
    });
    return d;
  };
  const dx = (W - L - R) / (n - 1);
  const pasek = dane.map((d, i) => (d.wynik == null ? "" : `<rect class="st-f-${stPoziomWyniku(d.wynik).poziom}" x="${(X(i) - dx / 2).toFixed(1)}" y="${T + HA + 4}" width="${(dx + 0.6).toFixed(1)}" height="${PASEK}"/>`)).join("");
  const pasma = [[40, 100, "silnie-pozytywny"], [15, 40, "pozytywny"], [-15, 15, "neutralny"], [-40, -15, "negatywny"], [-100, -40, "silnie-negatywny"]]
    .map(([a, b, k]) => `<rect class="st-f-${k} st-pasmo-tla" x="${L}" y="${YB(b).toFixed(1)}" width="${W - L - R}" height="${(YB(a) - YB(b)).toFixed(1)}"/>`)
    .join("");
  const cenyOsi = [0, 0.5, 1].map((f) => Math.exp(lmin + f * (lmax - lmin)));
  const osA = cenyOsi.map((v) => `<line class="st-svg-siatka" x1="${L}" x2="${W - R}" y1="${YA(v).toFixed(1)}" y2="${YA(v).toFixed(1)}"/><text class="st-svg-opis" x="${W - R + 4}" y="${(YA(v) + 3).toFixed(1)}">${stLiczba(v, 0)}</text>`).join("");
  const osB = [100, 40, 15, 0, -15, -40, -100].map((v) => `<text class="st-svg-opis" x="${W - R + 4}" y="${(YB(v) + 3).toFixed(1)}">${stZnak(v, 0)}</text>`).join("");
  const daty = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const i = Math.round(f * (n - 1));
    return `<text class="st-svg-opis" x="${X(i).toFixed(1)}" y="${H - 6}" text-anchor="${f === 0 ? "start" : f === 1 ? "end" : "middle"}">${stDataPl(dane[i].data)}</text>`;
  }).join("");
  const grupy = st.grupyNaWykresie
    ? Object.keys(ST_GRUPY).map((g) => `<path class="st-linia-grupy ${ST_KLASY_GRUP[g]}" d="${sciezka(dane.map((d) => d[g]), YB)}"/>`).join("")
    : "";
  host.innerHTML = `<svg class="st-svg st-svg-historia" viewBox="0 0 ${W} ${H}" role="img" aria-label="Historia sygnału rynku i S&amp;P 500">
      <text class="st-svg-panel" x="${L + 2}" y="${T + 10}">S&amp;P 500</text>
      ${osA}
      <path class="st-linia-spx" d="${sciezka(spx, YA)}"/>
      ${pasek}
      ${pasma}
      <line class="st-svg-zero" x1="${L}" x2="${W - R}" y1="${YB(0).toFixed(1)}" y2="${YB(0).toFixed(1)}"/>
      <text class="st-svg-panel" x="${L + 2}" y="${TB - 4}">Sygnał (od -100 do +100) i nastroje</text>
      ${osB}
      <path class="st-linia-nastrojow" d="${sciezka(dane.map((d) => (d.nastroje == null ? null : (d.nastroje - 50) * 2)), YB)}"/>
      ${grupy}
      <path class="st-linia-wyniku" d="${sciezka(dane.map((d) => d.wynik), YB)}"/>
      ${daty}
      <line id="st-kursor" class="st-svg-kursor" x1="0" x2="0" y1="${T}" y2="${TB + HB}" visibility="hidden"/>
      <rect id="st-wykres-pole" x="${L}" y="${T}" width="${W - L - R}" height="${TB + HB - T}" fill="transparent"/>
    </svg><div id="st-wykres-dymek" class="st-wykres-dymek" hidden></div>`;
  stEl("st-wykres-legenda").innerHTML =
    '<span><i class="st-leg"></i>sygnał</span><span><i class="st-leg st-leg-nastroje"></i>nastroje (50 na zerze)</span>' +
    (st.grupyNaWykresie ? Object.entries(ST_GRUPY).map(([g, nazwa]) => `<span><i class="st-leg ${ST_KLASY_GRUP[g]}"></i>${nazwa}</span>`).join("") : "") +
    '<span>pasek pod S&amp;P 500: poziom sygnału danego dnia</span>';
  const svg = host.querySelector("svg");
  const pole = stEl("st-wykres-pole");
  const kursor = stEl("st-kursor");
  const dymek = stEl("st-wykres-dymek");
  const pokaz = (e) => {
    const r = svg.getBoundingClientRect();
    const xSvg = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n - 1, Math.round(((xSvg - L) / (W - L - R)) * (n - 1))));
    const d = dane[i];
    kursor.setAttribute("x1", X(i));
    kursor.setAttribute("x2", X(i));
    kursor.setAttribute("visibility", "visible");
    const p = d.wynik == null ? null : stPoziomWyniku(d.wynik);
    dymek.innerHTML = `<b>${stDataPl(d.data)}</b><br>S&amp;P 500: ${stLiczba(d.spx, 0)}<br>Sygnał: ${stZnak(d.wynik, 0)}${p ? ` (${p.etykieta.toLowerCase()})` : ""}<br>makro ${stZnak(d.makro, 0)} · rynek ${stZnak(d.rynek, 0)} · technika ${stZnak(d.technika, 0)}<br>nastroje ${stLiczba(d.nastroje, 0)}`;
    dymek.hidden = false;
    const xPx = (X(i) / W) * r.width;
    dymek.style.left = `${xPx > r.width / 2 ? xPx - dymek.offsetWidth - 12 : xPx + 12}px`;
  };
  pole.addEventListener("pointermove", pokaz);
  pole.addEventListener("pointerdown", pokaz);
  pole.addEventListener("pointerleave", () => {
    kursor.setAttribute("visibility", "hidden");
    dymek.hidden = true;
  });
}

function stInicjujHistorie() {
  stEl("st-zakres").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-zakres]");
    if (!b) return;
    st.zakres = b.dataset.zakres;
    for (const x of stEl("st-zakres").querySelectorAll("button")) x.classList.toggle("aktywny", x === b);
    if (st.stan) stRysujHistorie();
  });
  stEl("st-pokaz-grupy").addEventListener("change", (e) => {
    st.grupyNaWykresie = e.target.checked;
    if (st.stan) stRysujHistorie();
  });
}
"""


#_______________________________________________________________________________
# okno 7: Skuteczność sygnału
#_______________________________________________________________________________
def element_skutecznosc(k: dict, zlozony) -> dict:
    """Orkiestrator tabeli skuteczności: zwroty S&P 500 po dniach z każdym poziomem sygnału,
    dla całej historii i dwóch krótszych okresów (zależność nie jest stała w czasie: w latach
    2020–2026 po najgorszych odczytach przychodziły szybkie odbicia)."""
    w, c = zlozony["wynik"], k["gspc"]["close"]
    okresy = []
    for klucz, od, nazwa in [("calosc", None, "cała historia"), ("od2008", "2008-01-01", "od 2008"),
                             ("od2019", PUTCALL_OD.isoformat(), "od 10.2019 (pełne dane put/call)")]:
        wynik = skutecznosc(w if od is None else w[od:], c)
        wynik.update({"id": klucz, "nazwa": nazwa if od else f"cała historia (od {wynik['od'][:4]})"})
        okresy.append(wynik)
    return {"okresy": okresy}


HTML_FRAGMENT_SKUTECZNOSC = """
<section class="karta t-okno t-k5 st-okno-skutecznosc">
  <header class="t-naglowek"><h2>Skuteczność sygnału</h2><div class="t-akcje"><select id="st-okres" class="st-wybor" title="Okres historii, z którego liczona jest tabela"></select></div></header>
  <div class="t-tresc t-tresc-tabela">
    <table id="st-skutecznosc" class="st-tabela"><tbody><tr><td class="pusto">Wczytywanie danych…</td></tr></tbody></table>
    <div id="st-skutecznosc-wniosek" class="st-wniosek"></div>
    <p class="opis">Jak czytać tabelę: każdy wiersz zbiera sesje z danym poziomem sygnału (policzonym wstecz tymi samymi regułami) i pokazuje, co działo się z S&amp;P 500 w kolejnych 63 sesjach, czyli około 3 miesiącach. „Spadek ≥10%” to odsetek przypadków, w których indeks w tym czasie choć raz zamknął się co najmniej 10% niżej niż w dniu sygnału; „Obsunięcie” to średni największy spadek. W długiej historii niższy sygnał wyraźnie częściej poprzedzał duże spadki, ale nie przewidywał wysokości zwrotu, a w latach 2020–2026 po najgorszych odczytach przychodziły szybkie odbicia. Okresy po sobie się nakładają, więc sesji nie należy traktować jak niezależnych prób.</p>
  </div>
</section>
"""

APP_JS_SKUTECZNOSC = r"""
// ===========================================================================
// ELEMENT: okno 7 „Skuteczność sygnału"
// ===========================================================================
function stRysujSkutecznosc() {
  const okresy = (st.stan.skutecznosc && st.stan.skutecznosc.okresy) || [];
  const wybor = stEl("st-okres");
  if (!wybor.options.length) {
    wybor.innerHTML = okresy.map((o) => `<option value="${o.id}">${stEsc(o.nazwa)}</option>`).join("");
    wybor.value = st.okres;
  }
  const o = okresy.find((x) => x.id === st.okres) || okresy[0];
  const tabela = stEl("st-skutecznosc");
  if (!o) {
    tabela.innerHTML = '<tbody><tr><td class="pusto">Brak danych</td></tr></tbody>';
    return;
  }
  const dzis = st.stan.sygnal.poziom;
  tabela.innerHTML = `<thead><tr>
      <th>Poziom sygnału</th>
      <th class="t-liczba" title="Ile sesji w wybranym okresie miało ten poziom sygnału i jaka to część wszystkich sesji">Sesji</th>
      <th class="t-liczba" title="W ilu procentach przypadków S&P 500 w ciągu kolejnych 63 sesji (ok. 3 mies.) spadł o 10% lub więcej względem dnia sygnału">Spadek ≥10%</th>
      <th class="t-liczba" title="Średnia zmiana S&P 500 w kolejnych 63 sesjach">Zwrot 3 mies.</th>
      <th class="t-liczba" title="W ilu procentach przypadków S&P 500 był po 63 sesjach wyżej niż w dniu sygnału">Na plusie</th>
      <th class="t-liczba" title="Średni największy spadek: o ile najniższe zamknięcie w kolejnych 63 sesjach było niższe od kursu z dnia sygnału">Obsunięcie</th>
    </tr></thead><tbody>${o.wiersze.map((w) => `<tr class="${w.poziom === dzis ? "st-biezacy" : ""}${w.poziom === "wszystkie" ? " st-suma" : ""}" title="${stEsc(`Kolejny miesiąc (21 sesji): średnio ${stProcZnak(w.sr21, 2)}, na plusie w ${stProc(w.plus21, 0)} przypadków.`)}">
      <td>${w.poziom === "wszystkie" ? "" : `<span class="st-kropka st-p-${w.poziom}"></span>`}${stEsc(w.etykieta)}${w.poziom === dzis ? " (dziś)" : ""}</td>
      <td class="t-liczba">${stLiczba(w.dni, 0)}<small>${stProc(w.udzial, 0)}</small></td>
      <td class="t-liczba"><b>${stProc(w.p10, 0)}</b></td>
      <td class="t-liczba ${stKlasaZnaku(w.sr63)}">${stProcZnak(w.sr63, 1)}</td>
      <td class="t-liczba">${stProc(w.plus63, 0)}</td>
      <td class="t-liczba">${stProc(w.dd63, 1)}</td></tr>`).join("")}</tbody>`;
  const poziomy = o.wiersze.filter((w) => w.poziom !== "wszystkie");
  const a = poziomy[0], b = poziomy[poziomy.length - 1];
  stEl("st-skutecznosc-wniosek").textContent = a && b
    ? `Okres ${stDataPl(o.od)}–${stDataPl(o.do)}. Spadek o 10% i więcej przychodził po ${stProc(a.p10, 0)} sesji z poziomem „${a.etykieta.toLowerCase()}” i po ${stProc(b.p10, 0)} z poziomem „${b.etykieta.toLowerCase()}”. Korelacja rang wyniku z późniejszym obsunięciem: ${stLiczba(o.korelacjaObsuniecia, 2)}, ze zwrotem 3 mies.: ${stLiczba(o.korelacja63, 2)} (0 to brak związku, 1 pełna zgodność kolejności).`
    : "";
}

function stInicjujSkutecznosc() {
  stEl("st-okres").addEventListener("change", (e) => {
    st.okres = e.target.value;
    if (st.stan) stRysujSkutecznosc();
  });
}
"""


#_______________________________________________________________________________
# okno 8: Źródła danych
#_______________________________________________________________________________
def element_zrodla(k: dict) -> dict:
    """Orkiestrator okna źródeł: stan każdego źródła i lista błędów tej aktualizacji."""
    return {"lista": k["zrodla"], "bledy": k["bledy"]}


HTML_FRAGMENT_ZRODLA = """
<section class="karta t-okno t-k12 st-okno-zrodla">
  <header class="t-naglowek"><h2>Źródła danych i aktualizacja</h2><div class="t-akcje"><span id="st-aktualizacja" class="st-czas"></span></div></header>
  <div class="t-tresc t-tresc-tabela">
    <table id="st-zrodla" class="st-tabela"><tbody><tr><td class="pusto">Wczytywanie danych…</td></tr></tbody></table>
    <div id="st-bledy" class="st-bledy"></div>
    <p class="opis">Dane liczy skrypt src/stan_rynku/stan_rynku.py. W pełnej platformie uruchamia go codziennie GitHub Actions (w dni robocze o 22:40 UTC, po zamknięciu sesji w USA), niezależnie od rutyny Claude, która potem pisze ocenę dnia; w tej statycznej wersji pokazowej dane są zamrożone na sesji widocznej w nagłówku karty. Wszystkie źródła są bezpłatne: FRED (klucz API opcjonalny, a bez niego publiczne pliki CSV), Cboe (dzienne statystyki opcji, historia VIX, łańcuch opcji SPX), Yahoo Finance przez własne proxy i funkcja VaR z modułu src/var/var.py. Gdy któreś źródło zawiedzie, jego wskaźniki pokazują „brak danych”, a błąd trafia na listę pod tabelą.</p>
  </div>
</section>
"""

APP_JS_ZRODLA = r"""
// ===========================================================================
// ELEMENT: okno 8 „Źródła danych i aktualizacja"
// ===========================================================================
function stRysujZrodla() {
  const z = st.stan.zrodla || { lista: [], bledy: [] };
  stEl("st-aktualizacja").textContent = `aktualizacja ${stCzasPl(st.stan.zaktualizowano)}`;
  stEl("st-zrodla").innerHTML = `<thead><tr><th>Źródło</th><th>Co z niego bierzemy</th><th class="t-liczba">Ostatnie dane</th><th>Stan</th></tr></thead><tbody>${z.lista
    .map((x) => `<tr><td>${stEsc(x.nazwa)}</td><td>${stEsc(x.opis)}${x.uwagi ? `<small>(${stEsc(x.uwagi)})</small>` : ""}</td><td class="t-liczba">${stDataPl(x.ostatnia)}</td><td class="${x.stan === "ok" ? "st-zr-ok" : "st-zr-blad"}">${stEsc(x.stan)}</td></tr>`)
    .join("")}</tbody>`;
  stEl("st-bledy").innerHTML = z.bledy.length
    ? `<b>Błędy ostatniej aktualizacji (${z.bledy.length}):</b><ul>${z.bledy.map((b) => `<li>${stEsc(b)}</li>`).join("")}</ul>`
    : "";
}
"""


def aktualizuj() -> None:
    """Pobiera dane, liczy wszystkie wskaźniki i zapisuje data/stan-rynku/stan.json."""
    import pandas as pd

    DANE.mkdir(exist_ok=True)
    k = zbierz_dane()
    print("Wskaźniki…")
    wyniki = policz_wskazniki(k)
    zlozony = wynik_zlozony(wyniki)
    skladniki = skladniki_nastrojow(k)
    k["nastroje_nazwy"] = {kl: v[0] for kl, v in skladniki.items()}
    nastroje_df = pd.DataFrame({kl: v[1] for kl, v in skladniki.items()})
    nastroje_seria = nastroje_df.mean(axis=1, skipna=True).where(nastroje_df.notna().sum(axis=1) >= 5)
    lista = element_wskazniki(k, wyniki)
    sygnal, nastroje = element_sygnal(k, wyniki, zlozony, nastroje_df, lista)
    stan = {
        "wersja": 1,
        "zaktualizowano": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sesja": k["sesje"][-1].strftime("%Y-%m-%d"),
        "spx": round(float(k["gspc"]["close"].iloc[-1]), 2),
        "sygnal": sygnal,
        "nastroje": nastroje,
        "opisAutomatyczny": opis_automatyczny(sygnal, nastroje, lista),
        "wskazniki": lista,
        "historia": element_historia(k, zlozony, nastroje_seria),
        "skutecznosc": element_skutecznosc(k, zlozony),
        "zrodla": element_zrodla(k),
    }
    SCIEZKA_STAN.write_text(_json_zwarty(stan), encoding="utf-8")
    print(f"zapisano {SCIEZKA_STAN} ({SCIEZKA_STAN.stat().st_size // 1024} KB): sesja {stan['sesja']}, "
          f"wynik {sygnal['wynik']} ({sygnal['etykieta']}), nastroje {nastroje.get('wartosc')}, błędów {len(k['bledy'])}")
    for b in k["bledy"]:
        print("  BŁĄD:", b, file=sys.stderr)


# ---------------------------------------------------------------------------
# element: przestrzeń robocza (zadanie 041): okna z zakładkami jak na karcie Social
# ---------------------------------------------------------------------------
# Mechanikę okien daje wspólny moduł web/shared/przestrzen.js. Osiem okien karty stoi w
# HTML w ukrytym „magazynie" (generuj()), liczy się i rysuje zawsze tak jak dotąd, a moduł
# przenosi je do okien użytkownika według zapisu w ustawienia/stan-rynku-przestrzen.json.
# Numery zakładek to dawne numery okien (1–8), żeby uwagi w projekty/ wskazywały to samo.
# Układ domyślny: szerokości z dawnego ustawienia/uklad-stan-rynku.json, wysokości zmierzone
# w dawnym układzie przy oknie 1440×900 plus pasek zakładek.
APP_JS_PRZESTRZEN = r"""
// ===========================================================================
// ELEMENT: przestrzeń robocza (okna z zakładkami, wspólny moduł web/shared/przestrzen.js)
// ===========================================================================
const ST_KOLEJNOSC = ["sygnal", "ocena", "makro", "rynek", "technika", "historia", "skutecznosc", "zrodla"];
const ST_ELEMENTY = {
  sygnal: { nazwa: "Sygnał rynku", opis: "Wynik od -100 do +100, poziom sygnału i nastroje", szer: 4, wys: 720, wezel: ".st-okno-sygnal" },
  ocena: { nazwa: "Ocena dnia", opis: "Komentarz rutyny Claude do ostatniej sesji", szer: 8, wys: 720, wezel: ".st-okno-ocena" },
  makro: { nazwa: "Makro", opis: "Wzrost, rynek pracy, inflacja i stopy (FRED)", szer: 4, wys: 660, wezel: '.st-okno-grupa[data-grupa="makro"]' },
  rynek: { nazwa: "Rynek", opis: "Opcje, zmienność, spready kredytowe i rotacja", szer: 4, wys: 660, wezel: '.st-okno-grupa[data-grupa="rynek"]' },
  technika: { nazwa: "Technika", opis: "Trend, skrajności, spadek od szczytu i VaR", szer: 4, wys: 660, wezel: '.st-okno-grupa[data-grupa="technika"]' },
  historia: { nazwa: "Historia sygnału", opis: "S&P 500 i sygnał rynku na wykresie od 2000 r.", szer: 7, wys: 520, wezel: ".st-okno-historia" },
  skutecznosc: { nazwa: "Skuteczność sygnału", opis: "Co działo się z indeksem po każdym poziomie", szer: 5, wys: 520, wezel: ".st-okno-skutecznosc" },
  zrodla: { nazwa: "Źródła danych", opis: "Skąd są dane, kiedy się odświeżyły i błędy", szer: 12, wys: 260, wezel: ".st-okno-zrodla" },
};
const ST_UKLAD_DOMYSLNY = [["sygnal", 4, 720], ["ocena", 8, 720], ["makro", 4, 660], ["rynek", 4, 660], ["technika", 4, 660], ["historia", 9, 520], ["skutecznosc", 3, 520], ["zrodla", 12, 260]];
let stPrzestrzen = null;

function stPrzestrzenInicjuj() {
  const korzen = document.getElementById("st-przestrzen");
  // Bez modułu (np. nie wczytał się plik) pokazujemy okna jedno pod drugim, żeby dane były widoczne.
  if (typeof PRZESTRZEN === "undefined") { korzen.querySelector(".prz-magazyn").hidden = false; return; }
  stPrzestrzen = PRZESTRZEN.utworz({
    korzen,
    elementy: ST_ELEMENTY,
    kolejnosc: ST_KOLEJNOSC,
    ukladDomyslny: ST_UKLAD_DOMYSLNY,
    start: "domyslny",
    klucz: "stan-rynku-przestrzen",
    cache: "st_przestrzen_cache",   // tylko podręczna kopia; zapis główny w repozytorium
    opisZapisu: "układ okien karty Stan rynku",
    napisy: {
      dodajTytul: "Dodaj okno z jednym z ośmiu elementów karty",
      domyslnyTytul: "Ustaw osiem okien karty w układzie domyślnym",
      potwierdzDomyslny: "Zastąpić obecne okna układem domyślnym (osiem okien)?",
    },
  });
  stPrzestrzen.przywroc();
}

if (typeof document !== "undefined" && document.getElementById("st-przestrzen")) stPrzestrzenInicjuj();
"""

#_______________________________________________________________________________
# start strony (orkiestrator całości w przeglądarce)
#_______________________________________________________________________________
APP_JS_START = r"""
// ===========================================================================
// START: wczytaj data/stan-rynku/stan.json i data/stan-rynku/ocena.json, potem narysuj wszystkie okna
// ===========================================================================
async function stStart() {
  stInicjujGrupy();
  stInicjujHistorie();
  stInicjujSkutecznosc();
  try {
    const [stan, ocena] = await Promise.all([stPobierz(ST_PLIK_STANU), stPobierz(ST_PLIK_OCENY).catch(() => null)]);
    if (!stan) throw new Error("brak pliku data/stan-rynku/stan.json (dane jeszcze nie zostały policzone)");
    st.stan = stan;
    st.ocena = ocena;
  } catch (e) {
    for (const id of ["st-sygnal", "st-ocena", "st-lista-makro", "st-lista-rynek", "st-lista-technika", "st-wykres"]) {
      stEl(id).innerHTML = `<div class="st-pusto blad">Nie udało się wczytać danych: ${stEsc(e.message)}</div>`;
    }
    return;
  }
  // Każde okno rysuje się osobno: błąd w jednym nie zostawia pustych pozostałych.
  const okna = [stRysujSygnal, stRysujOcene, () => stRysujGrupe("makro"), () => stRysujGrupe("rynek"),
    () => stRysujGrupe("technika"), stRysujHistorie, stRysujSkutecznosc, stRysujZrodla];
  for (const rysuj of okna) {
    try {
      rysuj();
    } catch (e) {
      console.error("Stan rynku:", e);
    }
  }
}

if (typeof document !== "undefined" && document.getElementById("st-sygnal")) stStart();
"""

SZABLON_HTML = """<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Stan rynku</title>
<link rel="stylesheet" href="../style.css" />
</head>
<body id="pg-stan-rynku" class="t-strona">
<script>window.SIDEBAR_ROOT = "../";</script>
<script src="../shared/sidebar.js"></script>
<script src="../shared/oznaczenia.js"></script>
<script src="../shared/projekty.js"></script>
<script src="../shared/ustawienia.js"></script>
<script src="../shared/przestrzen.js"></script>
<main>
@@FRAGMENT@@
</main>
<script src="app.js"></script>
</body>
</html>
"""

NAGLOWEK_JS = (
    '"use strict";\n\n'
    "// PLIK GENEROWANY przez src/stan_rynku/stan_rynku.py, nie edytuj ręcznie.\n\n"
)


def _wciecie(tekst: str, n: int = 2) -> str:
    pref = " " * n
    return "\n".join(pref + linia if linia.strip() else linia for linia in tekst.splitlines())


def generuj() -> None:
    """Składa osiem okien karty w index.html i cały kod przeglądarki w app.js."""
    okna = "\n\n".join(f.strip("\n") for f in [
        HTML_FRAGMENT_SYGNAL, HTML_FRAGMENT_OCENA, HTML_FRAGMENT_MAKRO, HTML_FRAGMENT_RYNEK,
        HTML_FRAGMENT_TECHNIKA, HTML_FRAGMENT_HISTORIA, HTML_FRAGMENT_SKUTECZNOSC, HTML_FRAGMENT_ZRODLA,
    ])
    # Przestrzeń robocza (zadanie 041, jak na karcie Social): okna stoją w ukrytym magazynie
    # wewnątrz kontenera przestrzeni, a web/shared/przestrzen.js (APP_JS_PRZESTRZEN) przenosi je
    # do okien z zakładkami. Kontener otwarty i zamknięty tutaj; nie ma klasy `t-siatka`, więc
    # okna.js go nie dotyczy, a oznaczenia.js numeruje całą przestrzeń jako jeden blok. Pusty
    # `div.prz-przestrzen` stoi w HTML od początku, żeby mapa kodu (mapa_kodu.py) widziała to samo.
    fragment = ('<div id="st-przestrzen" class="prz-karta">\n  <div class="prz-przestrzen"></div>\n  <div class="prz-magazyn" hidden>\n'
                + _wciecie(okna, 4) + "\n  </div>\n</div>")
    js = "\n\n".join(f.strip("\n") for f in [
        APP_JS_MAGAZYN, APP_JS_SYGNAL, APP_JS_OCENA, APP_JS_GRUPY, APP_JS_HISTORIA,
        APP_JS_SKUTECZNOSC, APP_JS_ZRODLA, APP_JS_PRZESTRZEN, APP_JS_START,
    ])
    SCIEZKA_HTML.write_text(SZABLON_HTML.replace("@@FRAGMENT@@", _wciecie(fragment)), encoding="utf-8")
    SCIEZKA_JS.write_text(NAGLOWEK_JS + js + "\n", encoding="utf-8")
    print(f"wygenerowano {SCIEZKA_HTML} i {SCIEZKA_JS}")


def sprawdz() -> int:
    """Sprawdza data/stan-rynku/ocena.json (rutyna Claude woła to przed commitem). Kod 0 = poprawnie."""
    bledy = element_ocena_sprawdz()
    if bledy:
        print("ocena.json ma błędy:")
        for b in bledy:
            print(" -", b)
        return 1
    print("ocena.json poprawna")
    return 0


if __name__ == "__main__":
    polecenie = sys.argv[1] if len(sys.argv) > 1 else "generuj"
    if polecenie == "aktualizuj":
        aktualizuj()
    elif polecenie == "sprawdz":
        sys.exit(sprawdz())
    elif polecenie == "generuj":
        generuj()
    else:
        print(__doc__)
        sys.exit(2)
