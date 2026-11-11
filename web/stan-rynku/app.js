"use strict";

// PLIK GENEROWANY przez src/stan_rynku/stan_rynku.py, nie edytuj ręcznie.

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
