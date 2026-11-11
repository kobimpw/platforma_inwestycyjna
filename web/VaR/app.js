"use strict";

// PLIK WYGENEROWANY z src/var/var.py (stałe APP_JS*), nie edytuj tutaj.
// Zmiany rób w src/var/var.py i uruchom `make build`.

const WORKER_URL = ""; // adres własnego proxy do Yahoo Finance; w wersji poglądowej pusty: notowania czyta shared/probka.js
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
// żeby jeden klik "Policz" nie odpytywał Yahoo Finance cztery razy z rzędu:
// cztery niezależne elementy strony dzielą jedno pobranie i te same obliczenia,
// bo parametry wejściowe są identyczne.
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
  const sciezka = `/quote?ticker=${encodeURIComponent(ticker)}&range=100y&interval=1d`;
  let surowe;
  if (WORKER_URL) {
    const res = await fetch(WORKER_URL + sciezka);
    if (!res.ok) {
      throw new Error(`Yahoo Finance (przez proxy) zwrócił błąd ${res.status} dla ${ticker}`);
    }
    surowe = await res.json();
  } else {
    surowe = await PROBKA.json(sciezka); // wersja poglądowa: zapisana próbka zamiast proxy
  }
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
      '<div class="wykres-blad">Nie udało się wczytać biblioteki wykresów (TradingView Lightweight Charts): ' +
      "wykres interaktywny jej wymaga, a tabele obok działają bez niej.</div>";
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
  status.textContent = WORKER_URL ? "Pobieranie notowań z Yahoo Finance…" : "Wczytywanie zapisanej próbki notowań…";
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
    status.textContent = `${ticker}: ${tabela.length} sesji (ostatnia: ${ostatni.data})` + (WORKER_URL ? "" : " · zapisana próbka, nie dane na żywo");
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

if (!WORKER_URL && typeof PROBKA !== "undefined") {
  PROBKA.indeks().then((spis) => {
    // Tylko tickery z historią wystarczającą do rachunku (indeks z jedną sesją służy karcie Pozycja do samej ceny).
    const tickery = Object.keys(spis.notowania).filter((t) => spis.notowania[t].punktow >= 250);
    const lista = document.createElement("datalist");
    lista.id = "v-tickery";
    lista.innerHTML = tickery.map((t) => '<option value="' + t + '"></option>').join("");
    document.body.appendChild(lista);
    const pole = document.getElementById("v-ticker");
    pole.setAttribute("list", "v-tickery");
    pole.title = "W wersji poglądowej są zapisane próbki tylko dla: " + tickery.join(", ");
  }).catch(() => {});
  pokaz();
}
