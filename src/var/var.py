"""notatnik
zbudowanie skill -> ocen : ma polegac na uczciwej ocenie zaporponowanego prze ze mnie roziwazania, ocena czy jest
zbudowanie skill -> code_BudowaSekcji : ma polegac na zbudowaniu pelnego elementu programu kod .py -> js -> html

1. skill
2. nowa arhitektura pliku
"""


"""Karta „VaR" — ryzyko strat (Value at Risk) dla dowolnego tickera.

Zbudowane skillem code-element-write na podstawie zatwierdzonej specyfikacji
(plik pierwotnej specyfikacji tej karty już nie istnieje w repo; zmiany
interfejsu z drugiej rundy opisuje specyfikacja pełnej platformy, poza wersją pokazową). Wzorzec pliku — patrz CLAUDE.md, „Karty: wzorzec
jednoplikowy" — CAŁA logika Pythona, fragmenty HTML i kod JS wykonywany w
przeglądarce mieszkają w tym jednym pliku; `generuj()` wypisuje z niego
`index.html`/`app.js` — tych dwóch plików nigdy nie edytuje się ręcznie.

To pełna wymiana poprzedniej zawartości tego pliku (wykresy ceny/wolumenu
z wcześniejszej próby — zostają tylko w historii gita, nic więcej ich tu
nie referencuje).

Trzy metody liczenia VaR, wszystkie z notatnika źródłowego (plik notatnika
już nie istnieje w repo), liczone kroczaco dla
każdego dnia z historii: parametryczna bez korekty o trend, parametryczna
z korektą o trend, oraz historyczna z percentyla empirycznego zwrotów.
Każda z trzech metod ma własny horyzont i własne wygładzanie SMA linii na
wykresie; poziom ufności, okno odchylenia i okno średniej są wspólne.
Progi są przesunięte o horyzont danej metody do przodu — próg policzony na
dzień t jest prognozą na dzień t + horyzont, nie oceną samego dnia t.

Użycie: `python VaR.py` (z tego katalogu) regeneruje index.html i app.js.
"""

from pathlib import Path
import math
import re

import pandas as pd

# `yfinance` importuje się dopiero w pobierz_notowania_zwrot(): karta „Stan rynku"
# (src/stan_rynku/stan_rynku.py) bierze z tego pliku oblicz_var_kroczaco(), żeby VaR na
# obu kartach liczył się tą samą metodą, a w jej workflow nie ma biblioteki yfinance.

#===============================================================================
# magazyn funkcji
#===============================================================================

def pobierz_notowania_zwrot(ticker: str, poczatek: str | None = None, interwal: str = "1d") -> pd.DataFrame:
    """yfinance -> [data, open, high, low, close, zwrot] posortowane rosnąco.

    `poczatek=None` -> cała dostępna historia (yfinance `period="max"`);
    `zwrot` to `close.pct_change()`, tak jak w notatniku źródłowym. Kolumny
    open/high/low idą tylko do rysowania świec OHLC na wykresie — sam VaR liczony
    jest wyłącznie z `close`.

    `auto_adjust=False` celowo: yfinance domyślnie koryguje Close wstecz o
    dywidendy, a `app.js` (fetch bezpośrednio z API Yahoo) bierze `close`
    surowy — bez tego jawnego wyłączenia obie strony liczyłyby VaR z innych
    szeregów cen i wyniki by się rozjeżdżały (widoczne najsilniej w
    odchyleniu/średniej zwrotów, bo liczone z całego okna 756 dni). Surowy
    close jest też jedynym, jaki mają wiele indeksów — dla nich adjusted
    close często w ogóle nie istnieje.
    """
    import yfinance as yf

    try:
        if poczatek is None:
            df = yf.Ticker(ticker).history(period="max", interval=interwal, auto_adjust=False)
        else:
            df = yf.Ticker(ticker).history(start=poczatek, interval=interwal, auto_adjust=False)
    except Exception as e:
        raise RuntimeError(f"yfinance: {e}") from e
    if df.empty:
        raise RuntimeError(f"yfinance zwrócił pustą tabelę dla {ticker!r}")

    df = df.reset_index()
    kol_daty = "Datetime" if "Datetime" in df.columns else "Date"
    kolumny_ohlc = [c for c in ["Open", "High", "Low"] if c in df.columns]
    df = df[[kol_daty] + kolumny_ohlc + ["Close"]].rename(
        columns={kol_daty: "data", "Open": "open", "High": "high", "Low": "low", "Close": "close"}
    )
    for kol in ["open", "high", "low", "close"]:
        if kol in df.columns:
            df[kol] = df[kol].astype(float)
    df = df.dropna(subset=["close"]).sort_values("data").reset_index(drop=True)
    df["zwrot"] = df["close"].pct_change()
    df["data"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m-%d")
    return df


def kwantyl_normalny(poziom_ufnosci: float) -> float:
    """Kwantyl standardowego rozkładu normalnego — przybliżenie Acklama.

    Celowo NIE `scipy.stats.norm.ppf` (scipy nie jest zależnością projektu):
    ta funkcja musi być 1:1 przenoszalna na JS (przeglądarka nie ma
    odpowiednika scipy), więc Python i JS używają dokładnie tego samego
    przybliżenia, zgodnie z notatnikiem źródłowym.
    """
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    p = poziom_ufnosci
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p <= p_high:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def sma(seria: pd.Series, okno: int) -> pd.Series:
    """Zwykła średnia krocząca.

    Kandydat do bycia użytecznym poza tą kartą (przy każdym przyszłym
    wygładzaniu wykresu), ale na razie zostaje tu, dopóki nie pojawi się
    drugi realny użytkownik tej funkcji w innym pliku.
    """
    return seria.rolling(okno).mean()


def oblicz_var_kroczaco(
    df: pd.DataFrame, horyzont_bez_korekty: int, horyzont_z_korekta: int,
    horyzont_percentyl: int, zaufanie: float, okno_odchylenia: int, okno_sredniej: int
) -> pd.DataFrame:
    """[data, close, zwrot] -> ta sama tabela + kolumny VaR liczone kroczaco.

    Wzorem komórki „wykres ciągły VaR w czasie" z notatnika źródłowego:
    trzy metody liczone dla KAŻDEGO dnia. Każda metoda ma WŁASNY horyzont —
    wchodzi on i do samej miary VaR (`dt`, `√horyzont`), i w przesunięcie
    progu `.shift(...)` do przodu: próg policzony na dzień t jest prognozą na
    dzień t + horyzont tej metody, więc na wykresie ma stanąć naprzeciwko
    dnia, który faktycznie prognozował, nie dnia, w którym został policzony.
    Wspólne dla wszystkich metod zostają: poziom ufności, okno odchylenia,
    okno średniej.
    """
    df = df.copy()
    zwroty = df["zwrot"]

    sigma_dzienne = zwroty.rolling(okno_odchylenia).std(ddof=1)
    sigma_roczne = sigma_dzienne * math.sqrt(252)
    sr_zwrot_dzienny = zwroty.rolling(okno_sredniej).mean()
    sr_zwrot_roczny = sr_zwrot_dzienny * 252

    z = kwantyl_normalny(zaufanie)
    dt_bez_korekty = horyzont_bez_korekty / 252
    dt_z_korekta = horyzont_z_korekta / 252

    var_bez_korekty = z * sigma_roczne * math.sqrt(dt_bez_korekty) * df["close"]
    var_z_korekta = df["close"] * (z * sigma_roczne * math.sqrt(dt_z_korekta) - sr_zwrot_roczny * dt_z_korekta)

    percentyl = zwroty.rolling(okno_odchylenia).quantile(1 - zaufanie, interpolation="linear")
    percentyl_empiryczny = -percentyl * df["close"] * math.sqrt(horyzont_percentyl)

    df["odch_dzienne"] = sigma_dzienne
    df["odch_roczne"] = sigma_roczne
    df["sr_zwrot_dzienny"] = sr_zwrot_dzienny
    df["sr_zwrot_roczny"] = sr_zwrot_roczny
    df["kwantyl"] = z
    df["var_bez_korekty"] = var_bez_korekty
    df["var_z_korekta"] = var_z_korekta
    df["percentyl_empiryczny"] = percentyl_empiryczny

    df["prog_bez_korekty"] = (df["close"] - var_bez_korekty).shift(horyzont_bez_korekty)
    df["prog_z_korekta"] = (df["close"] - var_z_korekta).shift(horyzont_z_korekta)
    df["prog_percentyl"] = (df["close"] - percentyl_empiryczny).shift(horyzont_percentyl)

    return df


def do_wykresu_var(df: pd.DataFrame) -> dict:
    """Kroczaca tabela VaR -> {swiece, prog_bez_korekty, prog_z_korekta, prog_percentyl}
    w formacie serii Lightweight Charts. `swiece` to lista OHLC (candlestick) z ceny,
    progi to po jednej liście na linię wykresu."""
    def seria(kolumna):
        return [
            {"time": w.data, "value": round(float(getattr(w, kolumna)), 4)}
            for w in df.itertuples() if pd.notna(getattr(w, kolumna))
        ]

    swiece = [
        {
            "time": w.data,
            "open": round(float(w.open), 4),
            "high": round(float(w.high), 4),
            "low": round(float(w.low), 4),
            "close": round(float(w.close), 4),
        }
        for w in df.itertuples()
        if pd.notna(w.open) and pd.notna(w.high) and pd.notna(w.low) and pd.notna(w.close)
    ]
    return {
        "swiece": swiece,
        "prog_bez_korekty": seria("prog_bez_korekty"),
        "prog_z_korekta": seria("prog_z_korekta"),
        "prog_percentyl": seria("prog_percentyl"),
    }


def do_tabeli_wynikow_dzis(df: pd.DataFrame) -> list[dict]:
    """Ostatni wiersz z ważnym (nie-NaN) progiem -> jednowierszowa tabela wyników na dziś."""
    gotowe = df.dropna(subset=["prog_bez_korekty"])
    if gotowe.empty:
        raise RuntimeError("za mało historii, żeby policzyć choć jeden kompletny wiersz VaR")
    w = gotowe.iloc[-1]
    return [{
        "data": w["data"],
        "cena": round(float(w["close"]), 2),
        "odchylenie dzienne %": round(float(w["odch_dzienne"]) * 100, 4),
        "odchylenie roczne %": round(float(w["odch_roczne"]) * 100, 2),
        "śr. zwrot dzienny %": round(float(w["sr_zwrot_dzienny"]) * 100, 4),
        "śr. zwrot roczny %": round(float(w["sr_zwrot_roczny"]) * 100, 2),
        "kwantyl": round(float(w["kwantyl"]), 6),
        "VaR bez korekty": round(float(w["var_bez_korekty"]), 2),
        "próg bez korekty": round(float(w["prog_bez_korekty"]), 2),
        "VaR z korektą": round(float(w["var_z_korekta"]), 2),
        "próg z korektą": round(float(w["prog_z_korekta"]), 2),
        "percentyl empiryczny": round(float(w["percentyl_empiryczny"]), 2),
        "próg percentyl": round(float(w["prog_percentyl"]), 2),
    }]


def do_tabeli_szczegolowej(df: pd.DataFrame) -> list[dict]:
    """Pełna kroczaca tabela VaR (tylko wiersze z ważnym progiem) -> lista
    wierszy pod filtrowanie „od-do" po stronie przeglądarki (web/shared/tabela.js)."""
    kolumny = [
        "data", "close", "odch_dzienne", "odch_roczne", "sr_zwrot_dzienny", "sr_zwrot_roczny",
        "var_bez_korekty", "prog_bez_korekty", "var_z_korekta", "prog_z_korekta",
        "percentyl_empiryczny", "prog_percentyl",
    ]
    gotowe = df.dropna(subset=["prog_bez_korekty"])
    wynik = []
    for w in gotowe.itertuples():
        wiersz = {}
        for kol in kolumny:
            wartosc = getattr(w, kol)
            wiersz[kol] = wartosc if kol == "data" else round(float(wartosc), 4)
        wynik.append(wiersz)
    return wynik


#===============================================================================
# elementy
#===============================================================================
#_______________________________________________________________________________
# wykres ciągły VaR
#_______________________________________________________________________________

def zbuduj_wykres_var(
    ticker: str, horyzont_bez_korekty: int = 1, horyzont_z_korekta: int = 21,
    horyzont_percentyl: int = 1, zaufanie: float = 0.99,
    okno_odchylenia: int = 756, okno_sredniej: int = 756,
) -> dict:
    """Orkiestrator: pobierz_notowania_zwrot() -> oblicz_var_kroczaco() -> do_wykresu_var()."""
    df = pobierz_notowania_zwrot(ticker)
    df = oblicz_var_kroczaco(
        df, horyzont_bez_korekty, horyzont_z_korekta, horyzont_percentyl,
        zaufanie, okno_odchylenia, okno_sredniej,
    )
    return do_wykresu_var(df)

# Okna 1 i 2 siatki: „Parametry" (z przyciskiem „Wzory …" w nagłówku — dawniej w bloku
# opisu strony, usuniętym w zadaniu 016; cała obsługa okna modalnego wzorów zostaje
# w elemencie „wzory") oraz „Wykres — cena i progi VaR w czasie". Kontener siatki
# `.t-siatka` składa generuj().
HTML_FRAGMENT = """
<section class="karta t-okno t-k4">
  <header class="t-naglowek"><h2>Parametry</h2><div class="t-akcje"><button id="v-wzory-btn" class="t-mini" type="button">Wzory …</button></div></header>
  <div class="t-tresc">
    <p class="opis" style="margin-bottom: 12px;">
      Parametry wspólne dla wszystkich trzech metod. Horyzont i wygładzanie SMA
      ustawia się osobno dla każdej metody niżej.
    </p>
    <div class="siatka-formularza">
      <label>Ticker
        <input id="v-ticker" type="text" value="SPY" />
      </label>
      <label>Poziom ufności
        <select id="v-zaufanie">
          <option value="0.90">90%</option>
          <option value="0.95">95%</option>
          <option value="0.99" selected>99%</option>
        </select>
      </label>
      <label>Okno odchylenia (dni)
        <input id="v-okno-odchylenia" type="number" value="756" step="1" min="2" />
      </label>
      <label>Okno średniej (dni)
        <input id="v-okno-sredniej" type="number" value="756" step="1" min="2" />
      </label>
    </div>

    <h3 style="font-size: 13px; margin: 18px 0 8px;">VaR bez korekty</h3>
    <div class="siatka-formularza">
      <label>Horyzont (dni sesyjnych)
        <input id="v-horyzont-bez-korekty" type="number" value="1" step="1" min="1" />
      </label>
      <label>Wygładzanie SMA (dni, 0 = wyłączone)
        <input id="v-sma-bez-korekty" type="number" value="30" step="1" min="0" />
      </label>
    </div>

    <h3 style="font-size: 13px; margin: 18px 0 8px;">VaR z korektą</h3>
    <div class="siatka-formularza">
      <label>Horyzont (dni sesyjnych)
        <input id="v-horyzont-z-korekta" type="number" value="21" step="1" min="1" />
      </label>
      <label>Wygładzanie SMA (dni, 0 = wyłączone)
        <input id="v-sma-z-korekta" type="number" value="10" step="1" min="0" />
      </label>
    </div>

    <h3 style="font-size: 13px; margin: 18px 0 8px;">percentyl empiryczny</h3>
    <div class="siatka-formularza">
      <label>Horyzont (dni sesyjnych)
        <input id="v-horyzont-percentyl" type="number" value="1" step="1" min="1" />
      </label>
      <label>Wygładzanie SMA (dni, 0 = wyłączone)
        <input id="v-sma-percentyl" type="number" value="10" step="1" min="0" />
      </label>
    </div>

    <div class="pasek-akcji">
      <button id="v-btn-policz">Policz</button>
      <span id="v-status" class="status"></span>
    </div>
  </div>
</section>

<section class="karta t-okno t-k8 t-naroznik">
  <header class="t-naglowek"><h2>Wykres — cena i progi VaR w czasie</h2></header>
  <div class="t-tresc">
    <div class="var-zakres">
      <button type="button" class="var-zakres-btn" data-zakres="1m">1m</button>
      <button type="button" class="var-zakres-btn" data-zakres="3m">3m</button>
      <button type="button" class="var-zakres-btn aktywny" data-zakres="1y">1y</button>
      <button type="button" class="var-zakres-btn" data-zakres="3y">3y</button>
      <button type="button" class="var-zakres-btn" data-zakres="5y">5y</button>
      <button type="button" class="var-zakres-btn" data-zakres="max">max</button>
    </div>
    <div class="var-wykres-rzad">
      <div class="wykres-tv-wrapper">
        <div id="v-wykres"></div>
      </div>
      <div id="v-wykres-legenda" class="var-wykres-legenda"></div>
    </div>
  </div>
</section>
"""

APP_JS = """
const WORKER_URL = "https://proxy.example.invalid"; // adres własnego proxy do Yahoo Finance (poza wersją pokazową)
const TLO_WYKRES = "#131722";
const SIATKA_WYKRES = "#2a2e39";
const PRZYGASZONY_WYKRES = "#868993";

// Kolory świec OHLC (celowo inne niż zielona/czerwona linia VaR, żeby się nie myliły)
const KOLOR_SWIECA_GORA = "#089981";
const KOLOR_SWIECA_DOL = "#f23645";
// Kolory linii progów VaR — te same co dotąd, teraz też jako próbki w legendzie
const KOLOR_BEZ_KOREKTY = "#f5a623";
const KOLOR_Z_KOREKTA = "#2e9e6e";
const KOLOR_PERCENTYL = "#d9534f";

// Elementy dodane niżej (b/c/d) dopisują tu swoją funkcję renderującą —
// woła je wspólny pokaz() poniżej, PO jednym wspólnym pobraniu/obliczeniu,
// żeby jeden klik "Policz" nie odpytywał Yahoo Finance cztery razy z rzędu
// (uproszczenie względem specyfikacji na poziomie JS — Część 2 opisuje
// cztery niezależne orkiestratory, ale w przeglądarce dzielą one to samo
// pobranie i te same obliczenia, bo parametry wejściowe są identyczne).
const WSPOLNE_RENDERY_VAR = [];

function isoZSekund(sekundyUTC) {
  return new Date(sekundyUTC * 1000).toISOString().slice(0, 10);
}

function formatujKomorke(v) {
  if (v == null || (typeof v === "number" && Number.isNaN(v))) return "—";
  return String(v);
}

function renderujTabeleObiektow(idTabeli, wiersze) {
  const tabela = document.getElementById(idTabeli);
  const thead = tabela.querySelector("thead");
  const tbody = tabela.querySelector("tbody");
  thead.innerHTML = "";
  tbody.innerHTML = "";
  if (!wiersze || wiersze.length === 0) {
    tbody.innerHTML = '<tr><td class="pusto">Brak danych</td></tr>';
    return;
  }
  const kolumny = Object.keys(wiersze[0]);
  thead.innerHTML = `<tr>${kolumny.map((k) => `<th>${k}</th>`).join("")}</tr>`;
  for (const w of wiersze) {
    const tr = document.createElement("tr");
    tr.innerHTML = kolumny.map((k) => `<td>${formatujKomorke(w[k])}</td>`).join("");
    tbody.appendChild(tr);
  }
}

// Odpowiednik pobierz_notowania_zwrot()
//
// UWAGA: celowo range=100y, NIE range=max. Yahoo Finance przy dosłownym
// "max" po cichu zwraca świece MIESIĘCZNE zamiast dziennych (sprawdzone na
// SPY i NVDA — range=max daje ~12 punktów/rok niezależnie od tickera),
// mimo że interval=1d jest jawnie podane. Jawny, duży zakres liczbowy
// (np. 50y/100y) Yahoo honoruje poprawnie i zwraca prawdziwe dane dzienne
// — 100y to zapas bezpieczeństwa dla starych indeksów z długą historią.
async function pobierzNotowaniaZwrot(ticker) {
  const url = `${WORKER_URL}/quote?ticker=${encodeURIComponent(ticker)}&range=100y&interval=1d`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Yahoo Finance (przez proxy) zwrócił błąd ${res.status} dla ${ticker}`);
  }
  const surowe = await res.json();
  const wynik = surowe?.chart?.result?.[0];
  const znaczniki = wynik?.timestamp;
  const quote = wynik?.indicators?.quote?.[0] || {};
  const close = quote.close;
  const open = quote.open;
  const high = quote.high;
  const low = quote.low;
  if (!Array.isArray(znaczniki) || !Array.isArray(close)) {
    const komunikat = surowe?.chart?.error?.description;
    throw new Error(komunikat ? `Yahoo Finance: ${komunikat}` : `Yahoo Finance zwrócił pustą tabelę dla ${ticker}`);
  }

  const wiersze = [];
  for (let i = 0; i < znaczniki.length; i++) {
    if (close[i] == null) continue;
    wiersze.push({
      data: isoZSekund(znaczniki[i]),
      open: open?.[i] ?? close[i],
      high: high?.[i] ?? close[i],
      low: low?.[i] ?? close[i],
      close: close[i],
    });
  }
  if (wiersze.length === 0) {
    throw new Error(`Yahoo Finance zwrócił pustą tabelę dla ${ticker}`);
  }
  wiersze.sort((a, b) => (a.data < b.data ? -1 : a.data > b.data ? 1 : 0));
  wiersze[0].zwrot = NaN;
  for (let i = 1; i < wiersze.length; i++) {
    wiersze[i].zwrot = wiersze[i].close / wiersze[i - 1].close - 1;
  }
  return wiersze;
}

// Odpowiednik kwantyl_normalny() — przybliżenie Acklama (przeglądarka nie ma odpowiednika scipy)
function kwantylNormalny(p) {
  const a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
    1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
  const b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
    6.680131188771972e+01, -1.328068155288572e+01];
  const c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
    -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
  const d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
    3.754408661907416e+00];
  const pLow = 0.02425;
  const pHigh = 1 - 0.02425;
  if (p < pLow) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
  } else if (p <= pHigh) {
    const q = p - 0.5;
    const r = q * q;
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);
  } else {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
  }
}

// Odpowiednik sma()
function sma(wartosci, okno) {
  const n = wartosci.length;
  const wynik = new Array(n).fill(NaN);
  for (let i = okno - 1; i < n; i++) {
    let suma = 0;
    let ok = true;
    for (let j = i - okno + 1; j <= i; j++) {
      if (Number.isNaN(wartosci[j])) { ok = false; break; }
      suma += wartosci[j];
    }
    wynik[i] = ok ? suma / okno : NaN;
  }
  return wynik;
}

function rollingStd(wartosci, okno) {
  const n = wartosci.length;
  const wynik = new Array(n).fill(NaN);
  for (let i = okno - 1; i < n; i++) {
    const w = wartosci.slice(i - okno + 1, i + 1);
    if (w.some(Number.isNaN)) continue;
    const srednia = w.reduce((s, x) => s + x, 0) / okno;
    const wariancja = w.reduce((s, x) => s + (x - srednia) ** 2, 0) / (okno - 1);
    wynik[i] = Math.sqrt(wariancja);
  }
  return wynik;
}

function percentylLiniowy(posortowane, p) {
  const n = posortowane.length;
  if (n === 1) return posortowane[0];
  const idx = p * (n - 1);
  const dolny = Math.floor(idx);
  const gorny = Math.ceil(idx);
  if (dolny === gorny) return posortowane[dolny];
  const waga = idx - dolny;
  return posortowane[dolny] * (1 - waga) + posortowane[gorny] * waga;
}

function rollingPercentyl(wartosci, okno, p) {
  const n = wartosci.length;
  const wynik = new Array(n).fill(NaN);
  for (let i = okno - 1; i < n; i++) {
    const w = wartosci.slice(i - okno + 1, i + 1);
    if (w.some(Number.isNaN)) continue;
    const posortowane = [...w].sort((x, y) => x - y);
    wynik[i] = percentylLiniowy(posortowane, p);
  }
  return wynik;
}

function przesunTablice(tab, ile) {
  const wynik = new Array(tab.length).fill(NaN);
  for (let i = ile; i < tab.length; i++) wynik[i] = tab[i - ile];
  return wynik;
}

// Odpowiednik oblicz_var_kroczaco()
// horyzonty = { bezKorekty, zKorekta, percentyl } — każda metoda ma własny horyzont
// (wchodzi i do miary VaR, i do przesunięcia progu); zaufanie/okna są wspólne.
function obliczVarKroczaco(wiersze, horyzonty, zaufanie, oknoOdchylenia, oknoSredniej) {
  const zwroty = wiersze.map((w) => w.zwrot);
  const close = wiersze.map((w) => w.close);

  const sigmaDzienne = rollingStd(zwroty, oknoOdchylenia);
  const sigmaRoczne = sigmaDzienne.map((s) => s * Math.sqrt(252));
  const srZwrotDzienny = sma(zwroty, oknoSredniej);
  const srZwrotRoczny = srZwrotDzienny.map((s) => s * 252);

  const z = kwantylNormalny(zaufanie);
  const dtBezKorekty = horyzonty.bezKorekty / 252;
  const dtZKorekta = horyzonty.zKorekta / 252;

  const varBezKorekty = sigmaRoczne.map((s, i) => (Number.isNaN(s) ? NaN : z * s * Math.sqrt(dtBezKorekty) * close[i]));
  const varZKorekta = sigmaRoczne.map((s, i) =>
    (Number.isNaN(s) || Number.isNaN(srZwrotRoczny[i])) ? NaN : close[i] * (z * s * Math.sqrt(dtZKorekta) - srZwrotRoczny[i] * dtZKorekta)
  );
  const percentyl = rollingPercentyl(zwroty, oknoOdchylenia, 1 - zaufanie);
  const percentylEmpiryczny = percentyl.map((p, i) => (Number.isNaN(p) ? NaN : -p * close[i] * Math.sqrt(horyzonty.percentyl)));

  const progBezKorekty = przesunTablice(varBezKorekty.map((v, i) => (Number.isNaN(v) ? NaN : close[i] - v)), horyzonty.bezKorekty);
  const progZKorekta = przesunTablice(varZKorekta.map((v, i) => (Number.isNaN(v) ? NaN : close[i] - v)), horyzonty.zKorekta);
  const progPercentyl = przesunTablice(percentylEmpiryczny.map((v, i) => (Number.isNaN(v) ? NaN : close[i] - v)), horyzonty.percentyl);

  return wiersze.map((w, i) => ({
    data: w.data,
    open: w.open,
    high: w.high,
    low: w.low,
    close: w.close,
    odch_dzienne: sigmaDzienne[i],
    odch_roczne: sigmaRoczne[i],
    sr_zwrot_dzienny: srZwrotDzienny[i],
    sr_zwrot_roczny: srZwrotRoczny[i],
    kwantyl: z,
    var_bez_korekty: varBezKorekty[i],
    var_z_korekta: varZKorekta[i],
    percentyl_empiryczny: percentylEmpiryczny[i],
    prog_bez_korekty: progBezKorekty[i],
    prog_z_korekta: progZKorekta[i],
    prog_percentyl: progPercentyl[i],
  }));
}

// Odpowiednik do_wykresu_var() — progi jako serie liniowe
function doSeriiWykresu(tabela, kolumna) {
  return tabela
    .filter((w) => w[kolumna] != null && !Number.isNaN(w[kolumna]))
    .map((w) => ({ time: w.data, value: Number(w[kolumna].toFixed(4)) }));
}

// Odpowiednik do_wykresu_var() — cena jako świece OHLC
function doSeriiSwiec(tabela) {
  return tabela
    .filter((w) => [w.open, w.high, w.low, w.close].every((x) => x != null && !Number.isNaN(x)))
    .map((w) => ({ time: w.data, open: w.open, high: w.high, low: w.low, close: w.close }));
}

let wykresVar = null;
let seriaSwiece = null;
let seriaBezKorekty = null;
let seriaZKorekta = null;
let seriaPercentyl = null;

// Bez `title:` — nazwy serii idą teraz do legendy HTML obok wykresu, nie na oś Y
function dodajLinieProgu(dane, kolor) {
  const seria = wykresVar.addLineSeries
    ? wykresVar.addLineSeries({ color: kolor, lineWidth: 1 })
    : wykresVar.addSeries(LightweightCharts.LineSeries, { color: kolor, lineWidth: 1 });
  seria.setData(dane);
  return seria;
}

// Legenda w kolumnie po prawej stronie wykresu: próbka koloru + nazwa + ostatnia
// wartość. Wiersze VaR mają checkbox (id jak dawniej: v-linia-*), „cena" nie ma.
// Stan checkboxów zachowujemy przy każdym przerysowaniu.
function odswiezLegende(tabela) {
  const el = document.getElementById("v-wykres-legenda");
  const gotowe = tabela.filter((w) => w.prog_bez_korekty != null && !Number.isNaN(w.prog_bez_korekty));
  const w = gotowe.length ? gotowe[gotowe.length - 1] : null;
  const swiece = doSeriiSwiec(tabela);
  const ostCena = swiece.length ? swiece[swiece.length - 1].close : null;
  const fmt = (x) => (x == null || Number.isNaN(x) ? "—" : Number(x).toFixed(2));

  const wiersze = [
    { klucz: null, kolor: KOLOR_SWIECA_GORA, nazwa: "cena", wartosc: ostCena },
    { klucz: "v-linia-bez-korekty", kolor: KOLOR_BEZ_KOREKTY, nazwa: "VaR bez korekty", wartosc: w ? w.prog_bez_korekty : null },
    { klucz: "v-linia-z-korekta", kolor: KOLOR_Z_KOREKTA, nazwa: "VaR z korektą", wartosc: w ? w.prog_z_korekta : null },
    { klucz: "v-linia-percentyl", kolor: KOLOR_PERCENTYL, nazwa: "percentyl empiryczny", wartosc: w ? w.prog_percentyl : null },
  ];

  const stan = {};
  for (const r of wiersze) {
    if (!r.klucz) continue;
    const istn = document.getElementById(r.klucz);
    stan[r.klucz] = istn ? istn.checked : true;
  }

  el.innerHTML = wiersze
    .map((r) => {
      const ptaszek = r.klucz
        ? `<input type="checkbox" id="${r.klucz}" ${stan[r.klucz] ? "checked" : ""} />`
        : '<span class="var-legenda-pusto"></span>';
      return (
        '<div class="var-legenda-wiersz">' +
        ptaszek +
        `<span class="var-legenda-probka" style="background:${r.kolor}"></span>` +
        `<span class="var-legenda-nazwa">${r.nazwa}</span>` +
        `<span class="var-legenda-wartosc">${fmt(r.wartosc)}</span>` +
        "</div>"
      );
    })
    .join("");
}

function narysujWykresVar(tabela, smaOkna) {
  const el = document.getElementById("v-wykres");
  if (typeof LightweightCharts === "undefined") {
    el.innerHTML =
      '<div class="wykres-blad">Nie udało się wczytać biblioteki TradingView Lightweight Charts z sieci — ' +
      "wykres interaktywny wymaga dostępu do unpkg.com.</div>";
    return;
  }
  if (!wykresVar) {
    wykresVar = LightweightCharts.createChart(el, {
      width: el.clientWidth || 800,
      height: 420,
      layout: { background: { color: TLO_WYKRES }, textColor: PRZYGASZONY_WYKRES, fontSize: 11 },
      grid: { vertLines: { color: SIATKA_WYKRES }, horzLines: { color: SIATKA_WYKRES } },
      rightPriceScale: { borderColor: SIATKA_WYKRES },
      timeScale: { borderColor: SIATKA_WYKRES, fixLeftEdge: true, fixRightEdge: true },
    });
    window.addEventListener("resize", () => wykresVar.applyOptions({ width: el.clientWidth || 800 }));
  }

  odswiezLegende(tabela);

  for (const seria of [seriaSwiece, seriaBezKorekty, seriaZKorekta, seriaPercentyl]) {
    if (seria) wykresVar.removeSeries(seria);
  }

  const opcjeSwiec = {
    upColor: KOLOR_SWIECA_GORA,
    downColor: KOLOR_SWIECA_DOL,
    borderVisible: false,
    wickUpColor: KOLOR_SWIECA_GORA,
    wickDownColor: KOLOR_SWIECA_DOL,
  };
  seriaSwiece = wykresVar.addCandlestickSeries
    ? wykresVar.addCandlestickSeries(opcjeSwiec)
    : wykresVar.addSeries(LightweightCharts.CandlestickSeries, opcjeSwiec);
  seriaSwiece.setData(doSeriiSwiec(tabela));

  function daneProgu(kolumna, smaOkno) {
    const surowe = doSeriiWykresu(tabela, kolumna);
    if (!(smaOkno > 0)) return surowe;
    const wygladzone = sma(surowe.map((p) => p.value), smaOkno);
    return surowe.map((p, i) => ({ time: p.time, value: wygladzone[i] })).filter((p) => !Number.isNaN(p.value));
  }

  seriaBezKorekty = dodajLinieProgu(daneProgu("prog_bez_korekty", smaOkna.bezKorekty), KOLOR_BEZ_KOREKTY);
  seriaZKorekta = dodajLinieProgu(daneProgu("prog_z_korekta", smaOkna.zKorekta), KOLOR_Z_KOREKTA);
  seriaPercentyl = dodajLinieProgu(daneProgu("prog_percentyl", smaOkna.percentyl), KOLOR_PERCENTYL);

  seriaBezKorekty.applyOptions({ visible: document.getElementById("v-linia-bez-korekty").checked });
  seriaZKorekta.applyOptions({ visible: document.getElementById("v-linia-z-korekta").checked });
  seriaPercentyl.applyOptions({ visible: document.getElementById("v-linia-percentyl").checked });
}

// Przyciski zakresu czasu — działają tylko na widoczny wycinek wykresu, nic nie
// przeliczają (dane i tak są liczone z pełnej historii). „max" = cała historia.
const OKRESY_ZAKRESU_MIES = { "1m": 1, "3m": 3, "1y": 12, "3y": 36, "5y": 60 };

function ustawZakresWykresu(zakres) {
  document
    .querySelectorAll(".var-zakres-btn")
    .forEach((b) => b.classList.toggle("aktywny", b.dataset.zakres === zakres));
  if (!wykresVar) return;

  const swiece = doSeriiSwiec(ostatniaTabelaVar || []);
  if (zakres === "max" || swiece.length === 0) {
    wykresVar.timeScale().fitContent();
    return;
  }
  const doData = swiece[swiece.length - 1].time;
  const d = new Date(doData + "T00:00:00Z");
  d.setUTCMonth(d.getUTCMonth() - (OKRESY_ZAKRESU_MIES[zakres] || 12));
  const odData = d.toISOString().slice(0, 10);
  try {
    wykresVar.timeScale().setVisibleRange({ from: odData, to: doData });
  } catch (e) {
    wykresVar.timeScale().fitContent();
  }
}

document.querySelector(".var-zakres").addEventListener("click", (e) => {
  const btn = e.target.closest(".var-zakres-btn");
  if (btn) ustawZakresWykresu(btn.dataset.zakres);
});

// Checkboxy linii VaR żyją teraz w legendzie (innerHTML przerysowywany co „Policz"),
// więc słuchamy zmian na kontenerze legendy, nie na samych polach.
document.getElementById("v-wykres-legenda").addEventListener("change", (e) => {
  const cb = e.target;
  if (cb.id === "v-linia-bez-korekty" && seriaBezKorekty) seriaBezKorekty.applyOptions({ visible: cb.checked });
  if (cb.id === "v-linia-z-korekta" && seriaZKorekta) seriaZKorekta.applyOptions({ visible: cb.checked });
  if (cb.id === "v-linia-percentyl" && seriaPercentyl) seriaPercentyl.applyOptions({ visible: cb.checked });
});

let ostatniaTabelaVar = null;

async function pokaz() {
  const status = document.getElementById("v-status");
  const przycisk = document.getElementById("v-btn-policz");
  status.classList.remove("blad");
  przycisk.disabled = true;
  status.textContent = "Pobieranie notowań z Yahoo Finance…";
  try {
    const ticker = document.getElementById("v-ticker").value.trim().toUpperCase();
    if (!ticker) throw new Error("wpisz ticker");
    const zaufanie = Number(document.getElementById("v-zaufanie").value) || 0.99;
    const oknoOdchylenia = Number(document.getElementById("v-okno-odchylenia").value) || 756;
    const oknoSredniej = Number(document.getElementById("v-okno-sredniej").value) || 756;
    const horyzonty = {
      bezKorekty: Number(document.getElementById("v-horyzont-bez-korekty").value) || 1,
      zKorekta: Number(document.getElementById("v-horyzont-z-korekta").value) || 21,
      percentyl: Number(document.getElementById("v-horyzont-percentyl").value) || 1,
    };
    const smaOkna = {
      bezKorekty: Number(document.getElementById("v-sma-bez-korekty").value) || 0,
      zKorekta: Number(document.getElementById("v-sma-z-korekta").value) || 0,
      percentyl: Number(document.getElementById("v-sma-percentyl").value) || 0,
    };

    const wiersze = await pobierzNotowaniaZwrot(ticker);
    const tabela = obliczVarKroczaco(wiersze, horyzonty, zaufanie, oknoOdchylenia, oknoSredniej);
    ostatniaTabelaVar = tabela;

    narysujWykresVar(tabela, smaOkna);
    ustawZakresWykresu("1y");
    for (const render of WSPOLNE_RENDERY_VAR) render(tabela);

    const ostatni = tabela[tabela.length - 1];
    status.textContent = `${ticker}: ${tabela.length} sesji (ostatnia: ${ostatni.data})`;
  } catch (err) {
    status.textContent = `Błąd: ${err.message}`;
    status.classList.add("blad");
  } finally {
    przycisk.disabled = false;
  }
}

document.getElementById("v-btn-policz").addEventListener("click", pokaz);
document.getElementById("v-ticker").addEventListener("keydown", (e) => {
  if (e.key === "Enter") pokaz();
});
"""

#_______________________________________________________________________________
# wyniki na dziś
#_______________________________________________________________________________

def zbuduj_wyniki_dzis(
    ticker: str, horyzont_bez_korekty: int = 1, horyzont_z_korekta: int = 21,
    horyzont_percentyl: int = 1, zaufanie: float = 0.99,
    okno_odchylenia: int = 756, okno_sredniej: int = 756,
) -> list[dict]:
    """Orkiestrator: te same dane co zbuduj_wykres_var(), ostatni wiersz jako tabela."""
    df = pobierz_notowania_zwrot(ticker)
    df = oblicz_var_kroczaco(
        df, horyzont_bez_korekty, horyzont_z_korekta, horyzont_percentyl,
        zaufanie, okno_odchylenia, okno_sredniej,
    )
    return do_tabeli_wynikow_dzis(df)

HTML_FRAGMENT_WYNIKI = """
<section class="karta t-okno t-k4">
  <header class="t-naglowek"><h2>Wyniki na dziś</h2></header>
  <div class="t-tresc t-tresc-tabela">
    <div class="tabela-wrapper">
      <table id="v-tabela-dzis">
        <thead></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</section>
"""

APP_JS_WYNIKI = """
function narysujWynikiDzis(tabela) {
  const ostatni = tabela.filter((w) => w.prog_bez_korekty != null && !Number.isNaN(w.prog_bez_korekty));
  if (ostatni.length === 0) {
    renderujTabeleObiektow("v-tabela-dzis", []);
    return;
  }
  const w = ostatni[ostatni.length - 1];
  renderujTabeleObiektow("v-tabela-dzis", [{
    data: w.data,
    cena: w.close.toFixed(2),
    "odchylenie dzienne %": (w.odch_dzienne * 100).toFixed(4),
    "odchylenie roczne %": (w.odch_roczne * 100).toFixed(2),
    "śr. zwrot dzienny %": (w.sr_zwrot_dzienny * 100).toFixed(4),
    "śr. zwrot roczny %": (w.sr_zwrot_roczny * 100).toFixed(2),
    kwantyl: w.kwantyl.toFixed(6),
    "VaR bez korekty": w.var_bez_korekty.toFixed(2),
    "próg bez korekty": w.prog_bez_korekty.toFixed(2),
    "VaR z korektą": w.var_z_korekta.toFixed(2),
    "próg z korektą": w.prog_z_korekta.toFixed(2),
    "percentyl empiryczny": w.percentyl_empiryczny.toFixed(2),
    "próg percentyl": w.prog_percentyl.toFixed(2),
  }]);
}

WSPOLNE_RENDERY_VAR.push(narysujWynikiDzis);
"""

#_______________________________________________________________________________
# tabela szczegółowa
#_______________________________________________________________________________

def zbuduj_tabele_szczegolowa(
    ticker: str, horyzont_bez_korekty: int = 1, horyzont_z_korekta: int = 21,
    horyzont_percentyl: int = 1, zaufanie: float = 0.99,
    okno_odchylenia: int = 756, okno_sredniej: int = 756,
) -> list[dict]:
    """Orkiestrator: te same dane co zbuduj_wykres_var(), cała tabela (filtrowanie
    „od-do" robi się dopiero w przeglądarce, patrz web/shared/tabela.js)."""
    df = pobierz_notowania_zwrot(ticker)
    df = oblicz_var_kroczaco(
        df, horyzont_bez_korekty, horyzont_z_korekta, horyzont_percentyl,
        zaufanie, okno_odchylenia, okno_sredniej,
    )
    return do_tabeli_szczegolowej(df)

HTML_FRAGMENT_SZCZEGOLOWA = """
<section class="karta t-okno t-k8">
  <header class="t-naglowek"><h2>Tabela szczegółowa — wybrany okres</h2></header>
  <div class="t-tresc">
    <div class="siatka-formularza">
      <label>Od
        <input id="v-od" type="date" />
      </label>
      <label>Do
        <input id="v-do" type="date" />
      </label>
    </div>
    <div class="tabela-wrapper tabela-wrapper-scroll">
      <table id="v-tabela-szczegolowa">
        <thead></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</section>
"""

APP_JS_SZCZEGOLOWA = """
function doTabeliSzczegolowej(tabela) {
  return tabela
    .filter((w) => w.prog_bez_korekty != null && !Number.isNaN(w.prog_bez_korekty))
    .map((w) => ({
      data: w.data,
      cena: w.close.toFixed(2),
      "VaR bez korekty": w.var_bez_korekty.toFixed(2),
      "próg bez korekty": w.prog_bez_korekty.toFixed(2),
      "VaR z korektą": w.var_z_korekta.toFixed(2),
      "próg z korektą": w.prog_z_korekta.toFixed(2),
      "percentyl empiryczny": w.percentyl_empiryczny.toFixed(2),
      "próg percentyl": w.prog_percentyl.toFixed(2),
    }));
}

function filtrujIRysujTabeleSzczegolowa() {
  if (!ostatniaTabelaVar) return;
  const od = document.getElementById("v-od").value;
  const do_ = document.getElementById("v-do").value;
  const wszystkie = doTabeliSzczegolowej(ostatniaTabelaVar);
  const przefiltrowane = przygotuj(wszystkie, {
    filtry: od && do_ ? [["data", "between", [od, do_]]] : [],
    sortujPo: "data",
    malejaco: false,
  });
  renderujTabeleObiektow("v-tabela-szczegolowa", przefiltrowane);
}

function ustawDomyslnyZakresDat(tabela) {
  const odPole = document.getElementById("v-od");
  const doPole = document.getElementById("v-do");
  if (odPole.value || doPole.value || tabela.length === 0) return;
  const gotowe = tabela.filter((w) => w.prog_bez_korekty != null && !Number.isNaN(w.prog_bez_korekty));
  if (gotowe.length === 0) return;
  doPole.value = gotowe[gotowe.length - 1].data;
  odPole.value = gotowe[Math.max(0, gotowe.length - 90)].data;
}

function narysujTabeleSzczegolowa(tabela) {
  ustawDomyslnyZakresDat(tabela);
  filtrujIRysujTabeleSzczegolowa();
}

document.getElementById("v-od").addEventListener("change", filtrujIRysujTabeleSzczegolowa);
document.getElementById("v-do").addEventListener("change", filtrujIRysujTabeleSzczegolowa);

WSPOLNE_RENDERY_VAR.push(narysujTabeleSzczegolowa);
"""

#_______________________________________________________________________________
# wzory (statyczne, bez pobierania danych) — okno modalne
#_______________________________________________________________________________

# Sam przycisk „Wzory …" jest w HTML_FRAGMENT (blok opisu, u góry) — patrz komentarz
# tam. Tutaj mieszka całe okno modalne i jego obsługa.

HTML_FRAGMENT_WZORY = """
<div id="v-wzory-modal" class="var-modal" hidden>
  <div class="var-modal-tlo" data-zamknij></div>
  <div class="var-modal-okno" role="dialog" aria-modal="true" aria-labelledby="v-wzory-tytul">
    <button type="button" class="var-modal-x" data-zamknij aria-label="Zamknij">×</button>
    <h2 id="v-wzory-tytul">Wzory użyte do obliczeń</h2>
    <div class="var-wzory-tresc">
      <p><strong>Kwantyl (z_c)</strong> — liczba odchyleń standardowych odpowiadająca
      wybranemu poziomowi pewności w standardowym rozkładzie normalnym.</p>
      <p><strong>VaR bez korekty</strong> = z_c × σ_roczne × √(horyzont / 252) × cena</p>
      <p><strong>VaR z korektą</strong> = cena × (z_c × σ_roczne × √(horyzont/252) − μ_roczne × horyzont/252)</p>
      <p><strong>Percentyl empiryczny</strong> = −percentyl(1 − poziom ufności) zwrotów × cena, przeskalowany × √horyzont</p>
      <p>Próg = cena − odpowiednia miara VaR. Każdy próg na wykresie jest dodatkowo
      przesunięty o horyzont danej metody do przodu, bo policzony na dzień t jest
      prognozą na dzień t + horyzont, nie oceną samego dnia t.</p>
      <p>Horyzont i wygładzanie SMA linii są ustawiane osobno dla każdej z trzech
      metod; poziom ufności, okno odchylenia i okno średniej są wspólne.</p>
    </div>
  </div>
</div>
"""

APP_JS_WZORY = """
const wzoryModal = document.getElementById("v-wzory-modal");

function pokazWzory() { wzoryModal.hidden = false; }
function ukryjWzory() { wzoryModal.hidden = true; }

document.getElementById("v-wzory-btn").addEventListener("click", pokazWzory);
wzoryModal.addEventListener("click", (e) => {
  if (e.target.closest("[data-zamknij]")) ukryjWzory();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !wzoryModal.hidden) ukryjWzory();
});
"""

#===============================================================================
# Generator — jedyne miejsce, które dotyka index.html i app.js
#===============================================================================

KORZEN = Path(__file__).resolve().parents[2]
SCIEZKA_KATALOGU = KORZEN / "web" / "VaR"        # strona karty (adres /VaR/ bez zmian)
SCIEZKA_HTML = SCIEZKA_KATALOGU / "index.html"
SCIEZKA_JS = SCIEZKA_KATALOGU / "app.js"

NAGLOWEK_JS = (
    '"use strict";\n\n'
    "// PLIK WYGENEROWANY z VaR.py (stałe APP_JS*) — nie edytuj tutaj,\n"
    "// zmiany rób w VaR.py i uruchom `python VaR.py`.\n\n"
)


def _wciecie(tekst: str, wciecie: str = "  ") -> str:
    """Dokłada wcięcie do każdej niepustej linii (pod styl reszty index.html)."""
    linie = tekst.strip("\n").splitlines()
    return "\n".join((wciecie + linia if linia else linia) for linia in linie)


def generuj() -> None:
    """Łączy fragmenty wszystkich elementów i wpisuje je do index.html / app.js."""
    # Siatka okien (wspólny styl terminala, zadanie 016): kontener otwarty i zamknięty
    # tutaj — wyjątek od zasady „nowy element = osobny fragment". Okno modalne
    # wzorów jest poza siatką (ukryte, otwierane przyciskiem z nagłówka okna 1).
    # Klasę `t-strona` na <body> ustawia ręcznie index.html.
    okna = "\n\n".join(
        frag.strip("\n") for frag in [HTML_FRAGMENT, HTML_FRAGMENT_WYNIKI, HTML_FRAGMENT_SZCZEGOLOWA]
    )
    fragment_html = (
        '<div class="t-siatka">\n' + _wciecie(okna) + "\n</div>\n\n"
        + HTML_FRAGMENT_WZORY.strip("\n") + "\n"
    )
    fragment_js = "\n\n".join(
        frag.strip("\n") for frag in [
            APP_JS, APP_JS_WYNIKI, APP_JS_SZCZEGOLOWA, APP_JS_WZORY,
        ]
    ) + "\n"

    html = SCIEZKA_HTML.read_text(encoding="utf-8")
    zamiennik = "<main>\n" + _wciecie(fragment_html) + "\n</main>"
    nowy_html, n = re.subn(r"<main>.*?</main>", lambda m: zamiennik, html, flags=re.DOTALL)
    if n != 1:
        raise RuntimeError("nie znaleziono <main>...</main> w index.html")
    SCIEZKA_HTML.write_text(nowy_html, encoding="utf-8")
    SCIEZKA_JS.write_text(NAGLOWEK_JS + fragment_js, encoding="utf-8")
    print(f"wygenerowano {SCIEZKA_HTML} i {SCIEZKA_JS}")


if __name__ == "__main__":
    generuj()
