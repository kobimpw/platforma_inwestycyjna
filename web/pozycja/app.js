"use strict";

// PLIK GENEROWANY przez src/pozycja/pozycja.py, nie edytuj ręcznie.

// ===========================================================================
// MAGAZYN FUNKCJI: konfiguracja i stan strony
// ===========================================================================
// CBOE i Yahoo nie pozwalają pytać się wprost z przeglądarki w obcej domenie, więc w pełnej platformie
// zapytania idą przez własny serwer pośredniczący (Cloudflare Worker), który tylko przepuszcza odpowiedź.
// Wersja poglądowa nie ma takiego serwera: gdy adres jest pusty, karta czyta zapisane próbki
// (web/shared/probka.js, dane w data/przyklad/).
const PZ_WORKER = "";
const PZ_PROBKA = !PZ_WORKER;
// Mnożnik opcji XSP i XND: 1 punkt strike'a = 100 USD na kontrakt.
const PZ_MNOZNIK = 100;
const MNOZNIK_OPCJI = PZ_MNOZNIK; // nazwa używana w rachunku skopiowanym ze starej karty
const PZ_KLUCZ = "pozycja"; // ustawienia/pozycja.json (USTAW)
const PZ_CACHE = "pz_ustawienia"; // podręczna kopia ustawień w localStorage (tylko cache)
const PZ_HISTORIA = "ustawienia/historia-zakladow.csv";
// Kolumny historii zakładów; `symbol` i `expiry` dopisała ta karta (stara karta czyta
// nagłówek z pliku, więc je zachowuje, a w swoich wierszach zostawia puste).
const PZ_KOLUMNY_CSV = ["id", "data_otwarcia", "data_zamkniecia", "strike_krotki", "strike_dlugi", "dni_T", "premia_otrzymana", "wynik_dolary", "stawka_zaangazowana", "wynik_procent_stawki", "kontrakty", "symbol", "expiry"];
// Dane rynkowe profilu są ważne 5 minut: przełączanie profili ich nie pobiera od nowa.
const PZ_WAZNOSC_DANYCH_MS = 5 * 60 * 1000;
const PZ_LIMIT_WIERSZY = 400;
// Wskaźniki, z których liczy się barometr (te, które oceniają warunki dla sprzedaży calli).
const PZ_BAROMETR = [1, 3, 4, 5, 8, 9];

// Wersja poglądowa: profile są PRZYKŁADOWE. Liczba jednostek i cena kupna są FIKCYJNE (prawdziwe pozycje
// autora nie są częścią tego repozytorium), a tickery to popularne ETF-y notowane w USA. Ceny kupna dobrano tak,
// żeby na dzień próbki pozycje były lekko pod wodą: generator zakładów stawia spready tam, gdzie zysk z ETF pokrywa
// stratę spreadu, więc przy dużym zysku strike'i wypadałyby tuż przy cenie indeksu i żaden zakład nie spełniałby
// warunku prawdopodobieństwa przebicia do 35%. Po odświeżeniu próbek (make probki) warto sprawdzić te dwie liczby.
const PZ_PROFIL_PUSTY = { id: "", nazwa: "Nowy profil", etf: "", ilosc: 0, cenaKupna: 0, indeks: "", indeksHistoria: "", cboe: "", ryzyko: 500, dryf: 10.5, maksKontraktow: 5, pokrycie: 100 };
const PZ_USTAWIENIA_DOMYSLNE = {
  wersja: 1,
  aktywny: "xsp",
  profile: [
    { ...PZ_PROFIL_PUSTY, id: "xsp", nazwa: "S&P 500 (XSP), przykład", etf: "SPY", ilosc: 100, cenaKupna: 770, indeks: "^XSP", indeksHistoria: "^XSP", cboe: "_XSP" },
    { ...PZ_PROFIL_PUSTY, id: "xnd", nazwa: "Nasdaq-100 (XND), przykład", etf: "QQQ", ilosc: 100, cenaKupna: 700, indeks: "^XND", indeksHistoria: "^NDX", cboe: "_XND" },
  ],
  tabela: { zestaw: "podstawowe", sortuj: "ocena", malejaco: true, pokaz: "wszystkie", termin: "wszystkie", typ: "wszystkie" },
};
const PZ_POLA_LICZBOWE = ["ilosc", "cenaKupna", "ryzyko", "dryf", "maksKontraktow", "pokrycie"];

// Pola formularza profilu. `pobierz` = zmiana wymaga pobrania danych od nowa.
const PZ_POLA = [
  { klucz: "nazwa", etykieta: "Nazwa profilu", typ: "text", dymek: "Nazwa na przycisku profilu, np. S&P 500 (XSP)." },
  { klucz: "etf", etykieta: "ETF (ticker Yahoo)", typ: "text", pobierz: true, dymek: "Ticker ETF w Yahoo Finance, np. SPY albo QQQ. Z jego ceny liczy się wartość pozycji." },
  { klucz: "ilosc", etykieta: "Liczba jednostek", typ: "number", krok: 1, dymek: "Ile jednostek ETF masz w portfelu." },
  { klucz: "cenaKupna", etykieta: "Cena kupna", typ: "number", krok: 0.01, dymek: "Średnia cena kupna jednej jednostki ETF w walucie notowania. Od niej liczy się zysk ETF, który ma pokryć stratę spreadu." },
  { klucz: "indeks", etykieta: "Indeks (cena)", typ: "text", pobierz: true, dymek: "Ticker indeksu w Yahoo, na którym są opcje, np. ^XSP albo ^XND." },
  { klucz: "indeksHistoria", etykieta: "Indeks (historia)", typ: "text", pobierz: true, dymek: "Ticker z roczną historią notowań do zmienności zrealizowanej i średniej z 50 sesji. Dla XND to ^NDX (ten sam indeks w skali razy 100), bo ^XND nie ma historii w Yahoo." },
  { klucz: "cboe", etykieta: "Symbol CBOE", typ: "text", pobierz: true, dymek: "Symbol łańcucha opcji w CBOE, np. _XSP albo _XND." },
  { klucz: "ryzyko", etykieta: "Ryzyko nominalne (USD)", typ: "number", krok: 100, dymek: "Górna granica straty spreadu, którą rozważasz. Generator buduje progi co 100 USD aż do tej kwoty." },
  { klucz: "dryf", etykieta: "Dryf roczny µ (%)", typ: "number", krok: 0.1, dymek: "Oczekiwany roczny wzrost indeksu w rachunku EV (10,5% to 20-letni dryf S&P 500 przyjęty w arkuszu EV)." },
  { klucz: "maksKontraktow", etykieta: "Maks. kontraktów", typ: "number", krok: 1, dymek: "Największa liczba kontraktów w jednym zakładzie: zamiast jednego szerokiego spreadu kilka węższych." },
  { klucz: "pokrycie", etykieta: "Pokrycie straty (%)", typ: "number", krok: 1, dymek: "Jaką część maksymalnej straty spreadu musi pokryć zysk ETF przy danym progu (100% oznacza całą)." },
];

// Stan strony, wspólny dla wszystkich okien.
const pz = {
  ustawienia: null, // jak PZ_USTAWIENIA_DOMYSLNE
  dane: new Map(), // klucz danych profilu -> { czas, lancuch, etf, indeks, historia, bledy }
  wynik: null, // ostatni przeliczony stan (pzPrzelicz)
  wybrany: null, // zakład pokazany na wykresie wypłaty
  otwarte: [], // wiersze historii zakładów bez daty zamknięcia
  zamkniete: [], // ostatnie zamknięte zakłady
  historiaStan: "", // komunikat o wczytaniu historii
};

// ---------------------------------------------------------------------------
// Formatowanie (liczby po polsku, daty, ucieczka HTML)
// ---------------------------------------------------------------------------
function pzLiczba(v, miejsca = 0) {
  if (v == null || !Number.isFinite(v)) return "–";
  if (Number(v.toFixed(miejsca)) === 0) v = 0; // bez „-0" po zaokrągleniu
  return v.toLocaleString("pl-PL", { minimumFractionDigits: miejsca, maximumFractionDigits: miejsca });
}
function pzZeZnakiem(v, miejsca = 0) {
  if (v == null || !Number.isFinite(v)) return "–";
  return (v > 0 ? "+" : "") + pzLiczba(v, miejsca);
}
function pzProcent(ulamek, miejsca = 1) {
  return ulamek == null || !Number.isFinite(ulamek) ? "–" : pzLiczba(ulamek * 100, miejsca) + "%";
}
function pzUsd(v, miejsca = 0) {
  return v == null || !Number.isFinite(v) ? "–" : pzLiczba(v, miejsca) + " USD";
}
function pzKlasaZnaku(v) {
  return v > 0 ? "pz-plus" : v < 0 ? "pz-minus" : "";
}
function pzDataKrotka(ms) {
  const d = new Date(ms);
  return `${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
function pzDataIso(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}
function pzDzisiajUTC() {
  // Wersja poglądowa: terminy opcji liczą się od dnia próbki, a nie od dzisiaj (próbka jest zamrożona w czasie).
  if (PZ_PROBKA && typeof PROBKA !== "undefined" && PROBKA.dzisiajUTC() != null) return PROBKA.dzisiajUTC();
  const n = new Date();
  return Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate());
}
function pzDzisiajIso() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
function pzEsc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[z]));
}
function pzEl(id) {
  return document.getElementById(id);
}
function pzNoweId() {
  return "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
}

// ---------------------------------------------------------------------------
// Pobieranie danych przez Workera: łańcuch opcji CBOE, ceny i historia z Yahoo.
// ---------------------------------------------------------------------------
async function pzPobierzJson(sciezka) {
  if (PZ_PROBKA) return PROBKA.json(sciezka); // wersja poglądowa: zapisana próbka zamiast serwera pośredniczącego
  const odp = await fetch(PZ_WORKER + sciezka);
  if (!odp.ok) throw new Error(`Worker zwrócił błąd ${odp.status} (${sciezka.split("?")[0]})`);
  return odp.json();
}

// Łańcuch CBOE -> lista opcji w formacie starej karty (strike, typ, bid/ask, cena
// środkowa, greki, dni do wygaśnięcia, cały wpis CBOE w `surowe`) i migawka nagłówka.
function pzParsujLancuch(surowe, dzisiaj) {
  const lista = surowe?.data?.options;
  if (!Array.isArray(lista)) throw new Error("Nieoczekiwana odpowiedź CBOE: brak data.options");
  const opcje = [];
  for (const o of lista) {
    const m = /^([A-Z]+)(\d{6})([CP])(\d{8})$/.exec(o.option);
    if (!m) continue;
    const expiry = Date.UTC(2000 + Number(m[2].slice(0, 2)), Number(m[2].slice(2, 4)) - 1, Number(m[2].slice(4, 6)));
    const dni = Math.round((expiry - dzisiaj) / 86400000);
    if (dni < 0) continue;
    opcje.push({
      root: m[1],
      expiry,
      typ: m[3],
      strike: Number(m[4]) / 1000,
      bid: o.bid,
      ask: o.ask,
      mid: o.bid > 0 ? (o.bid + o.ask) / 2 : null,
      delta: o.delta,
      theta: o.theta,
      iv: o.iv,
      days: dni > 0 ? dni : 0.5,
      surowe: o,
    });
  }
  const d = surowe.data;
  return {
    opcje,
    migawka: { czas: surowe.timestamp || null, cena: d.current_price ?? null, iv30: d.iv30 ?? null, zmianaIv30: d.iv30_change ?? null },
  };
}

async function pzPobierzLancuch(symbol) {
  return pzParsujLancuch(await pzPobierzJson(`/options?symbol=${encodeURIComponent(symbol)}`), pzDzisiajUTC());
}

async function pzPobierzCene(ticker) {
  const d = await pzPobierzJson(`/quote?ticker=${encodeURIComponent(ticker)}`);
  const meta = d?.chart?.result?.[0]?.meta;
  if (typeof meta?.regularMarketPrice !== "number") throw new Error(`Brak ceny dla ${ticker} w Yahoo Finance`);
  return {
    cena: meta.regularMarketPrice,
    waluta: meta.currency || "",
    poprzednia: typeof meta.chartPreviousClose === "number" ? meta.chartPreviousClose : null,
    czas: typeof meta.regularMarketTime === "number" ? meta.regularMarketTime * 1000 : null,
  };
}

// Dzienne zamknięcia z ostatniego roku (zmienność zrealizowana, średnia z 50 sesji).
async function pzPobierzHistorie(ticker) {
  const d = await pzPobierzJson(`/quote?ticker=${encodeURIComponent(ticker)}&range=1y&interval=1d`);
  const r = d?.chart?.result?.[0];
  return (r?.indicators?.quote?.[0]?.close || []).filter((x) => typeof x === "number" && x > 0);
}

// Wszystkie dane profilu naraz; błąd jednego źródła nie blokuje pozostałych.
async function pzPobierzDaneProfilu(profil) {
  const wyniki = await Promise.allSettled([
    pzPobierzLancuch(profil.cboe),
    pzPobierzCene(profil.etf),
    pzPobierzCene(profil.indeks),
    pzPobierzHistorie(profil.indeksHistoria || profil.indeks),
  ]);
  const [lancuch, etf, indeks, historia] = wyniki.map((w) => (w.status === "fulfilled" ? w.value : null));
  const bledy = wyniki.filter((w) => w.status === "rejected").map((w) => w.reason?.message || String(w.reason));
  return { czas: Date.now(), lancuch, etf, indeks, historia: historia || [], bledy };
}

function pzKluczDanych(p) {
  return [p.cboe, p.etf, p.indeks, p.indeksHistoria].join("|");
}

// ---------------------------------------------------------------------------
// Wartość oczekiwana (EV) zakładu i całej pozycji ETF + spread. KOPIA rachunku ze
// starej karty (arkusz „EV" z pełnej platformy, poza tym repozytorium; numery w
// komentarzach = INDEKS wiersza arkusza). Liczone pod rzeczywistą miarą P, czyli z
// dryfem µ z profilu, a nie ze stopą wolną od ryzyka r.
// ---------------------------------------------------------------------------

// Dystrybuanta rozkładu normalnego (przybliżenie Abramowitza-Stegun, błąd ok. 7.5e-8).
function normCdf(x) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const wielomian =
    t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  const gestosc = Math.exp(-(x * x) / 2) / Math.sqrt(2 * Math.PI);
  const ogon = gestosc * wielomian;
  return x >= 0 ? 1 - ogon : ogon;
}

// Oczekiwana wypłata opcji call E[max(S_T − K, 0)] w punktach indeksu:
// S·e^(µT)·N(d1') − K·N(d2'); N(d2') = P(S_T ≥ K) (INDEKS 33-37 / 39-43).
function oczekiwanaWyplataCall({ S, K, T, mu, sigma }) {
  const sigmaPierwT = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (mu + 0.5 * sigma * sigma) * T) / sigmaPierwT;
  const d2 = d1 - sigmaPierwT;
  const nd1 = normCdf(d1);
  const nd2 = normCdf(d2);
  return { nd1, nd2, wyplata: S * Math.exp(mu * T) * nd1 - K * nd2 };
}

// Pełen rachunek EV jednego zakładu (S, K1, K2 w punktach indeksu; premiaUsd dla całej
// pozycji; cenaNabycia i cenaRynkowa w walucie ETF).
function policzEV({ S, K1, K2, premiaUsd, mu, sigma, dni, cenaNabycia, ilosc, cenaRynkowa, kontrakty = 1 }) {
  const T = dni / 365;
  const sc = oczekiwanaWyplataCall({ S, K: K1, T, mu, sigma });
  const lc = oczekiwanaWyplataCall({ S, K: K2, T, mu, sigma });

  const pSC = sc.nd2; // 36: P(S_T ≥ K1)
  const evSC = sc.wyplata * MNOZNIK_OPCJI * kontrakty; // 37
  const evLC = lc.wyplata * MNOZNIK_OPCJI * kontrakty; // 43
  const kosztSpreadu = evSC - evLC; // 45
  const evOpcji = premiaUsd - kosztSpreadu; // 46

  const cenaEtfZDryfem = cenaRynkowa * Math.exp(mu * T);
  const kapital = ilosc * cenaRynkowa;
  const annualizuj = (ev) => ev / T / kapital; // 55/60/68

  const cenaWarunkowaPowyzej = pSC > 0 ? cenaEtfZDryfem * (sc.nd1 / sc.nd2) : null; // 51
  const wynikWarunkowyPowyzej = cenaWarunkowaPowyzej == null ? null : (cenaWarunkowaPowyzej - cenaNabycia) * ilosc; // 52
  const evEtfPowyzej = (cenaEtfZDryfem * sc.nd1 - cenaNabycia * sc.nd2) * ilosc; // 53
  const evScenariuszPowyzej = evOpcji + evEtfPowyzej; // 54
  const evRyPowyzej = annualizuj(evScenariuszPowyzej); // 55

  const cenaWarunkowaPonizej = pSC < 1 ? cenaEtfZDryfem * ((1 - sc.nd1) / (1 - sc.nd2)) : null; // 56
  const wynikWarunkowyPonizej = cenaWarunkowaPonizej == null ? null : (cenaWarunkowaPonizej - cenaNabycia) * ilosc; // 57
  const evEtfPonizej = (cenaEtfZDryfem * (1 - sc.nd1) - cenaNabycia * (1 - sc.nd2)) * ilosc; // 58
  const evScenariuszPonizej = evOpcji + evEtfPonizej; // 59
  const evRyPonizej = annualizuj(evScenariuszPonizej); // 60

  const zwrotEtfPrzyStrikeSC = (K1 / S) * cenaRynkowa * ilosc - ilosc * cenaNabycia; // 62
  const evEtf = (cenaEtfZDryfem - cenaNabycia) * ilosc; // 64
  const evRyPozycji = (cenaRynkowa * Math.exp(mu) - cenaNabycia) / cenaRynkowa; // 65
  const evPozycji = evOpcji + evEtf; // 66
  const evDryfu = (cenaEtfZDryfem - cenaRynkowa) * ilosc; // 67
  const evRyDryfu = annualizuj(evDryfu); // 68

  // Punkty 0-5, po jednym za każdy spełniony warunek z arkusza (INDEKS 21).
  const punkty =
    (pSC < 0.5 ? 1 : 0) +
    (evOpcji > 0 ? 1 : 0) +
    (evRyPowyzej > evRyDryfu ? 1 : 0) +
    (evRyPowyzej > evRyPozycji ? 1 : 0) +
    (evRyPowyzej > Math.abs(evRyPonizej) ? 1 : 0);

  return {
    pSC, evSC, evLC, kosztSpreadu, evOpcji,
    cenaWarunkowaPowyzej, wynikWarunkowyPowyzej, evEtfPowyzej, evScenariuszPowyzej, evRyPowyzej,
    cenaWarunkowaPonizej, wynikWarunkowyPonizej, evEtfPonizej, evScenariuszPonizej, evRyPonizej,
    zwrotEtfPrzyStrikeSC, evEtf, evRyPozycji, evPozycji, evDryfu, evRyDryfu, punkty,
  };
}

// Kolumny EV doklejone do zakładu; σ = iv nogi sprzedanej (jedna dla obu nóg, jak w arkuszu).
function dolozEV(z, { S, mu, cenaNabycia, ilosc, cenaRynkowa }) {
  if (!(z.ivSprzedanejNogi > 0)) return { ...z, punkty: null };
  return {
    ...z,
    ...policzEV({
      S,
      K1: z.strikeSprzedany,
      K2: z.strikeKupiony,
      premiaUsd: z.premia * MNOZNIK_OPCJI,
      kontrakty: z.kontrakty,
      mu,
      sigma: z.ivSprzedanejNogi,
      dni: z.days,
      cenaNabycia,
      ilosc,
      cenaRynkowa,
    }),
  };
}

// ---------------------------------------------------------------------------
// Progi ryzyka i generator zakładów bear call spread. KOPIA ze starej karty
// (zbudujProgiRyzyka bez pobierania cen, które przychodzą tu jako argumenty).
// ---------------------------------------------------------------------------
// Próg = wartość ETF, przy której zysk ETF pokrywa stratę spreadu; środek drabinki to
// poziom indeksu odpowiadający tej wartości (indeks × próg / dzisiejsza wartość ETF).
function pzProgi({ ilosc, cenaKupna, ryzyko, pokrycie }, cenaEtf, cenaIndeksu) {
  const marketValue = Math.round(ilosc * cenaEtf);
  const costBasic = ilosc * cenaKupna;
  const indexPrice = Math.round(cenaIndeksu);
  const baza = costBasic > marketValue ? costBasic : marketValue;
  const progi = [];
  for (let krok = 100; krok < ryzyko + 100; krok += 100) {
    const prog = baza + krok;
    const srodek = Math.round(indexPrice * (prog / marketValue));
    // Szerokość spreadu w punktach strike'a: przy 100% pokrycia krok/mnożnik, przy
    // niższym % pokrycia dopuszczalna strata rośnie, więc spread się poszerza.
    const szerokosc = (krok / MNOZNIK_OPCJI) / (pokrycie / 100);
    const gornyStrike = Math.round(srodek + szerokosc);
    const dolnyStrike = Math.round(srodek - szerokosc);
    progi.push({
      prog,
      srodek,
      budzetPunktow: szerokosc,
      gornyStrike,
      dolnyStrike,
      zyskEtf: prog - marketValue,
      zyskGornyStrike: (gornyStrike / indexPrice) * marketValue - costBasic,
      zyskDolnyStrike: (dolnyStrike / indexPrice) * marketValue - costBasic,
      zyskSrodek: (srodek / indexPrice) * marketValue - costBasic,
    });
  }
  return { progi, kontekst: { marketValue, marketPrice: cenaEtf, costBasic, index: indexPrice } };
}

function opcjeNaStrike(opcjeCall, strike) {
  return opcjeCall.filter((o) => o.strike === strike);
}

function parujPoExpiry(gorne, dolne) {
  const dolnePoExpiry = new Map();
  for (const o of dolne) {
    if (!dolnePoExpiry.has(o.expiry)) dolnePoExpiry.set(o.expiry, []);
    dolnePoExpiry.get(o.expiry).push(o);
  }
  const pary = [];
  for (const g of gorne) {
    for (const d of dolnePoExpiry.get(g.expiry) || []) pary.push([g, d]);
  }
  return pary;
}

// Kombinacje (liczba kontraktów n, szerokość spreadu w): n × w wypełnia budżet punktów
// progu. n = 1 zostaje z drabinki progów (szerokosc = null); n ≥ 2 tylko szerokości całkowite.
function kombinacjeKontraktow(budzetPunktow, maksKontraktow) {
  const wynik = [{ kontrakty: 1, szerokosc: null }];
  const calkowity = Math.round(budzetPunktow);
  if (Math.abs(budzetPunktow - calkowity) > 1e-9) return wynik;
  for (let n = 2; n <= maksKontraktow; n++) {
    if (calkowity % n === 0) wynik.push({ kontrakty: n, szerokosc: calkowity / n });
  }
  return wynik;
}

// "dolny" to zawsze noga SPRZEDANA (bliżej ceny), "gorny" zawsze KUPIONA (dalej od ceny).
function zbudujZaklad(gorny, dolny, typZakladu, szerokoscPunkty, zyskEtf, procentPokrycia, zyskGornyStrike, zyskDolnyStrike, kontrakty = 1) {
  if (gorny.mid == null || dolny.mid == null) return null;
  const premiaZaKontrakt = dolny.mid - gorny.mid;
  const premia = premiaZaKontrakt * kontrakty;
  const days = gorny.days;
  const maxStrata = (szerokoscPunkty * MNOZNIK_OPCJI - premiaZaKontrakt * MNOZNIK_OPCJI) * kontrakty;
  // warunek: zysk ETF przy tym progu pokrywa maksymalną stratę w procentPokrycia%
  if (maxStrata * (procentPokrycia / 100) > zyskEtf) return null;
  return {
    zaklad: `${kontrakty > 1 ? `${kontrakty}x ` : ""}${Math.trunc(gorny.strike)}/${Math.trunc(dolny.strike)}`,
    kontrakty,
    days,
    expiry: gorny.expiry,
    premia,
    delta: dolny.delta,
    deltaPortfela: (-dolny.delta + gorny.delta) * kontrakty,
    thetaPortfela: (-dolny.theta + gorny.theta) * kontrakty,
    dailyPremia: days > 0 ? Math.round(((premia / days) * 100) * 100) / 100 : 0,
    typZakladu,
    zyskGornyStrike,
    zyskDolnyStrike,
    strikeSprzedany: dolny.strike,
    strikeKupiony: gorny.strike,
    ivSprzedanejNogi: dolny.iv,
    sprzedana: dolny,
    kupiona: gorny,
    maxStrata,
  };
}

function generujZaklady(progi, wszystkieOpcje, procentPokrycia, maksKontraktow = 1, kontekst = null) {
  const calle = wszystkieOpcje.filter((o) => o.typ === "C");
  const wynik = [];
  const zyskDlaStrike = (strike) => (strike / kontekst.index) * kontekst.marketValue - kontekst.costBasic;

  for (const { srodek, gornyStrike, dolnyStrike, zyskEtf, zyskGornyStrike, zyskDolnyStrike, zyskSrodek, budzetPunktow } of progi) {
    for (const { kontrakty, szerokosc } of kombinacjeKontraktow(budzetPunktow, kontekst ? maksKontraktow : 1)) {
      const gora = szerokosc == null ? gornyStrike : srodek + szerokosc;
      const dol = szerokosc == null ? dolnyStrike : srodek - szerokosc;
      const zyskGora = szerokosc == null ? zyskGornyStrike : zyskDlaStrike(gora);
      const zyskDol = szerokosc == null ? zyskDolnyStrike : zyskDlaStrike(dol);
      // bezpieczny: para (gora, srodek)
      for (const [gorny, dolny] of parujPoExpiry(opcjeNaStrike(calle, gora), opcjeNaStrike(calle, srodek))) {
        const z = zbudujZaklad(gorny, dolny, "bezpieczny", gora - srodek, zyskEtf, procentPokrycia, zyskGora, zyskSrodek, kontrakty);
        if (z) wynik.push(z);
      }
      // ryzykowny: para (srodek, dol)
      for (const [gorny, dolny] of parujPoExpiry(opcjeNaStrike(calle, srodek), opcjeNaStrike(calle, dol))) {
        const z = zbudujZaklad(gorny, dolny, "ryzykowny", srodek - dol, zyskEtf, procentPokrycia, zyskSrodek, zyskDol, kontrakty);
        if (z) wynik.push(z);
      }
    }
  }
  return wynik;
}

// ---------------------------------------------------------------------------
// Płynność zakładu (zadanie 033). KOPIA ze starej karty: premia po cenach rynkowych,
// koszt płynności, głębokość kwotowania i punkty płynności 0-5.
// ---------------------------------------------------------------------------
const PLYNNOSC_PROG_SPREAD = 0.1;
const PLYNNOSC_PROG_OI = 50;
const PLYNNOSC_PROG_WIEK_DNI = 5;

function dniMiedzy(odData, doData) {
  const ms = (d) => Date.UTC(Number(d.slice(0, 4)), Number(d.slice(5, 7)) - 1, Number(d.slice(8, 10)));
  return Math.max(0, Math.round((ms(doData) - ms(odData)) / 86400000));
}

// Ostatnia sesja widoczna w danych = najpóźniejsza data transakcji w łańcuchu.
function kontekstPlynnosciLancucha(opcje) {
  let dataSesji = null;
  for (const o of opcje) {
    const data = o.surowe?.last_trade_time?.slice(0, 10);
    if (data && (!dataSesji || data > dataSesji)) dataSesji = data;
  }
  return { dataSesji };
}

function wskaznikiOpcji(o, dataSesji) {
  if (!o) return null;
  const s = o.surowe || {};
  const bid = Number(o.bid) || 0;
  const ask = Number(o.ask) || 0;
  const srodek = ask > 0 ? (bid + ask) / 2 : null;
  const spread = ask > 0 ? ask - bid : null;
  const czas = s.last_trade_time || null;
  const theo = Number(s.theo) > 0 ? Number(s.theo) : null;
  return {
    bid,
    ask,
    bidSize: Number(s.bid_size) || 0,
    askSize: Number(s.ask_size) || 0,
    srodek,
    spread,
    spreadProc: srodek > 0 ? spread / srodek : null,
    wolumen: Number(s.volume) || 0,
    oi: Number(s.open_interest) || 0,
    wiek: czas && dataSesji ? dniMiedzy(czas.slice(0, 10), dataSesji) : null,
    theo,
  };
}

function dolozPlynnosc(z, { dataSesji }) {
  const n = z.kontrakty || 1;
  const s = wskaznikiOpcji(z.sprzedana, dataSesji);
  const k = wskaznikiOpcji(z.kupiona, dataSesji);
  const premiaSrodekUsd = z.premia * MNOZNIK_OPCJI;
  // natychmiast, po cenach z rynku: sprzedaż nogi sprzedanej po bid, kupno nogi kupionej po ask
  const premiaRynkowaUsd = k.ask > 0 ? (s.bid - k.ask) * MNOZNIK_OPCJI * n : null;
  const kosztPlynnosciUsd = premiaRynkowaUsd == null ? null : premiaSrodekUsd - premiaRynkowaUsd;
  const glebokoscKwotowania = Math.min(s.bidSize, k.askSize);
  const najwyzej = (v, prog) => v != null && v <= prog;
  const punktyPlynnosci =
    (najwyzej(s.spreadProc, PLYNNOSC_PROG_SPREAD) && najwyzej(k.spreadProc, PLYNNOSC_PROG_SPREAD) ? 1 : 0) +
    (s.oi >= PLYNNOSC_PROG_OI && k.oi >= PLYNNOSC_PROG_OI ? 1 : 0) +
    (s.wolumen > 0 ? 1 : 0) +
    (najwyzej(s.wiek, PLYNNOSC_PROG_WIEK_DNI) && najwyzej(k.wiek, PLYNNOSC_PROG_WIEK_DNI) ? 1 : 0) +
    (glebokoscKwotowania >= n ? 1 : 0);
  return {
    ...z,
    premiaSrodekUsd,
    premiaRynkowaUsd,
    kosztPlynnosciUsd,
    kosztPlynnosciProc: kosztPlynnosciUsd != null && premiaSrodekUsd > 0 ? kosztPlynnosciUsd / premiaSrodekUsd : null,
    spreadSprzedanejProc: s.spreadProc,
    spreadKupionejProc: k.spreadProc,
    glebokoscKwotowania,
    oiSprzedanej: s.oi,
    punktyPlynnosci,
  };
}

// ---------------------------------------------------------------------------
// Dziesięć wskaźników (specyfikacja, sekcja 3). Każdy zwraca
// { nr, nazwa, dymek, wartosc, pod, stan }, gdzie stan to "dobrze" (sprzyja sprzedaży
// call spreadu), "uwaga", "zle" (nie sprzyja), "info" (bez oceny) albo "brak" (brak danych).
// Progi kolorów to pierwsza kalibracja na danych z 31.10.2026, do strojenia.
// ---------------------------------------------------------------------------
function pzBrak(powod) {
  return { wartosc: "brak danych", pod: powod, stan: "brak" };
}

function pzTerminy(opcje, minDni = 0) {
  const m = new Map();
  for (const o of opcje) if (o.days >= minDni && !m.has(o.expiry)) m.set(o.expiry, o.days);
  return [...m.entries()].map(([expiry, dni]) => ({ expiry, dni })).sort((a, b) => a.expiry - b.expiry);
}

// Termin wygaśnięcia najbliższy `celDni` (nie krótszy niż `minDni`).
function pzTerminBlisko(opcje, celDni, minDni = 7) {
  const t = pzTerminy(opcje, minDni);
  if (!t.length) return null;
  return t.reduce((a, b) => (Math.abs(b.dni - celDni) < Math.abs(a.dni - celDni) ? b : a));
}

// Strike „przy cenie": najbliższy cenie indeksu, przy którym call i put mają kwotowanie.
function pzAtm(opcje, expiry, S) {
  const calle = new Map();
  const puty = new Map();
  for (const o of opcje) {
    if (o.expiry !== expiry || !(o.mid > 0)) continue;
    (o.typ === "C" ? calle : puty).set(o.strike, o);
  }
  let wynik = null;
  for (const [k, call] of calle) {
    const put = puty.get(k);
    if (put && (!wynik || Math.abs(k - S) < Math.abs(wynik.strike - S))) wynik = { strike: k, call, put };
  }
  return wynik;
}

function pzIvAtm(atm) {
  if (!atm) return null;
  const iv = [atm.call.iv, atm.put.iv].filter((x) => x > 0);
  return iv.length ? iv.reduce((a, b) => a + b, 0) / iv.length : null;
}

// Roczna zmienność zrealizowana z `n` ostatnich dziennych zwrotów logarytmicznych.
function pzZmiennoscZrealizowana(zamkniecia, n = 20) {
  if (zamkniecia.length < n + 1) return null;
  const z = zamkniecia.slice(-(n + 1));
  const zwroty = [];
  for (let i = 1; i < z.length; i++) zwroty.push(Math.log(z[i] / z[i - 1]));
  const sr = zwroty.reduce((a, b) => a + b, 0) / zwroty.length;
  const war = zwroty.reduce((a, b) => a + (b - sr) ** 2, 0) / (zwroty.length - 1);
  return Math.sqrt(war * 252);
}

function pzOi(o) {
  return Number(o.surowe?.open_interest) || 0;
}

function pzWsk1PremiaZmiennosci({ migawka, historia }) {
  const opis = { nr: 1, nazwa: "Premia za zmienność", dymek: "IV30 (zmienność implikowana: jak duże ruchy indeksu w ciągu 30 dni wycenia rynek opcji, z CBOE) minus zmienność zrealizowana (jak mocno indeks faktycznie ruszał się w ostatnich 20 sesjach, w skali roku). Dodatnia różnica oznacza, że opcje są drogie względem rzeczywistych ruchów, więc sprzedawca call spreadu dostaje więcej, niż wynosi typowe ryzyko; to jak składka ubezpieczeniowa wyższa od średnich szkód. Zielony od +2 pkt proc., żółty od 0 do 2, czerwony poniżej zera." };
  const iv30 = migawka?.iv30;
  const rv = pzZmiennoscZrealizowana(historia, 20);
  if (!(iv30 > 0) || rv == null) return { ...opis, ...pzBrak("brak IV30 albo historii indeksu") };
  const premia = iv30 - rv * 100;
  return { ...opis, wartosc: `${pzZeZnakiem(premia, 1)} pkt proc.`, pod: `IV30 ${pzLiczba(iv30, 1)}% · zrealizowana ${pzLiczba(rv * 100, 1)}%`, stan: premia >= 2 ? "dobrze" : premia >= 0 ? "uwaga" : "zle" };
}

function pzWsk2OczekiwanyRuch({ opcje, S }) {
  const opis = { nr: 2, nazwa: "Oczekiwany ruch (ok. 30 dni)", dymek: "Cena straddle'a przy cenie: kupno calla i puta o strike'u najbliższym bieżącej cenie indeksu, dla terminu najbliższego 30 dniom. Straddle wypłaca na wygaśnięciu tyle, o ile indeks odejdzie od strike'u w którąkolwiek stronę, więc jego cena to średni ruch wyceniany przez rynek. Krótki call bezpieczniej stawiać powyżej górnej granicy tego zakresu." };
  const t = pzTerminBlisko(opcje, 30, 7);
  const atm = t && pzAtm(opcje, t.expiry, S);
  if (!atm) return { ...opis, ...pzBrak("brak kwotowań przy cenie") };
  const ruch = atm.call.mid + atm.put.mid;
  return { ...opis, wartosc: `±${pzLiczba(ruch, 1)} pkt`, pod: `${pzProcent(ruch / S, 1)} do ${pzDataKrotka(t.expiry)} (${t.dni} dni): ${pzLiczba(S - ruch, 0)}–${pzLiczba(S + ruch, 0)}`, stan: "info", ruch, termin: t };
}

function pzWsk3Skosnosc({ opcje, S }) {
  const opis = { nr: 3, nazwa: "Skośność call", dymek: "IV calla z deltą około 0,25 (taki strike, jaki zwykle sprzedajemy) minus IV calla przy cenie, dla terminu około 30 dni, w punktach procentowych. Na indeksach ta różnica jest zwykle ujemna, bo dalekie calle są tańsze od opcji przy cenie. Im bliżej zera, tym relatywnie droższe są dalekie calle, czyli lepsza premia za ich sprzedaż. Zielony od −2, żółty poniżej −4 (dalekie calle wyjątkowo tanie), pomiędzy szary." };
  const t = pzTerminBlisko(opcje, 30, 7);
  const atm = t && pzAtm(opcje, t.expiry, S);
  const calle = t ? opcje.filter((o) => o.expiry === t.expiry && o.typ === "C" && o.mid > 0 && o.iv > 0 && o.delta > 0.05 && o.delta < 0.5) : [];
  if (!atm || !(atm.call.iv > 0) || !calle.length) return { ...opis, ...pzBrak("brak kwotowań calli") };
  const c25 = calle.reduce((a, b) => (Math.abs(b.delta - 0.25) < Math.abs(a.delta - 0.25) ? b : a));
  const skos = (c25.iv - atm.call.iv) * 100;
  return { ...opis, wartosc: `${pzZeZnakiem(skos, 1)} pkt proc.`, pod: `call ${pzLiczba(c25.strike, 0)} (Δ ${pzLiczba(c25.delta, 2)}) ${pzLiczba(c25.iv * 100, 1)}% · przy cenie ${pzLiczba(atm.call.iv * 100, 1)}%`, stan: skos >= -2 ? "dobrze" : skos < -4 ? "uwaga" : "info" };
}

function pzWsk4StrukturaTerminowa({ opcje, S }) {
  const opis = { nr: 4, nazwa: "Struktura terminowa", dymek: "IV opcji przy cenie dla terminu około 30 dni podzielona przez IV dla terminu około 90 dni. W spokojnym rynku krótkie terminy są tańsze (wynik poniżej 1). Wynik powyżej 1 oznacza krótkoterminowy niepokój: rynek spodziewa się gwałtownych ruchów w najbliższych tygodniach. Zielony poniżej 0,95, żółty od 0,95 do 1, czerwony powyżej 1." };
  const t30 = pzTerminBlisko(opcje, 30, 7);
  const t90 = pzTerminBlisko(opcje, 90, 60);
  const iv30 = t30 && pzIvAtm(pzAtm(opcje, t30.expiry, S));
  const iv90 = t90 && pzIvAtm(pzAtm(opcje, t90.expiry, S));
  if (!(iv30 > 0) || !(iv90 > 0)) return { ...opis, ...pzBrak("brak terminów 30 i 90 dni") };
  const r = iv30 / iv90;
  return { ...opis, wartosc: pzLiczba(r, 2), pod: `${t30.dni} dni ${pzLiczba(iv30 * 100, 1)}% · ${t90.dni} dni ${pzLiczba(iv90 * 100, 1)}%`, stan: r > 1 ? "zle" : r < 0.95 ? "dobrze" : "uwaga" };
}

function pzWsk5PutCall({ opcje }) {
  const opis = { nr: 5, nazwa: "Put/call (otwarte pozycje)", dymek: "Liczba otwartych kontraktów put podzielona przez liczbę otwartych kontraktów call, dla terminów do 60 dni. Na opcjach indeksowych putów jest zawsze więcej, bo służą do zabezpieczania portfeli. Skrajnie dużo zabezpieczeń (powyżej 3,5) bywa paliwem do gwałtownego odbicia w górę, gdy są zamykane; bardzo mało (poniżej 1) to euforia. Oba skraje są żółte, pomiędzy zielony. Progi wstępne, do kalibracji." };
  let puty = 0;
  let calle = 0;
  for (const o of opcje) {
    if (o.days > 60) continue;
    if (o.typ === "P") puty += pzOi(o);
    else calle += pzOi(o);
  }
  if (!(calle > 0)) return { ...opis, ...pzBrak("brak otwartych calli") };
  const r = puty / calle;
  const malo = puty + calle < 3000;
  return { ...opis, wartosc: pzLiczba(r, 2), pod: `${pzLiczba(puty, 0)} putów · ${pzLiczba(calle, 0)} calli${malo ? " · mało pozycji" : ""}`, stan: malo ? "info" : r > 3.5 || r < 1 ? "uwaga" : "dobrze" };
}

function pzWsk6ScianaCall({ opcje, S }) {
  const opis = { nr: 6, nazwa: "Ściana call", dymek: "Strike powyżej ceny indeksu z największą liczbą otwartych calli w terminach do 45 dni. Duże skupisko calli często działa jak opór: sprzedawcy tych opcji bronią poziomu, a cena rzadziej go przebija. Krótki call na ścianie albo powyżej jest bezpieczniejszy (to jedno z kryteriów oceny propozycji)." };
  const naStrike = new Map();
  let suma = 0;
  for (const o of opcje) {
    if (o.typ !== "C" || o.days > 45 || !(o.strike > S)) continue;
    const oi = pzOi(o);
    if (!oi) continue;
    naStrike.set(o.strike, (naStrike.get(o.strike) || 0) + oi);
    suma += oi;
  }
  if (!naStrike.size) return { ...opis, ...pzBrak("brak otwartych calli nad ceną") };
  const [strike, oi] = [...naStrike.entries()].reduce((a, b) => (b[1] > a[1] ? b : a));
  // Ściana z mniej niż 500 kontraktami to przypadkowe skupisko: pokazujemy ją, ale nie liczy się w ocenie propozycji.
  const slaba = oi < 500;
  return { ...opis, wartosc: `${pzLiczba(strike, 0)} (${pzZeZnakiem((strike / S - 1) * 100, 1)}%)`, pod: `${pzLiczba(oi, 0)} otwartych calli do 45 dni${slaba ? " · słaba, poza oceną" : ""}`, stan: "info", strike: slaba ? null : strike };
}

function pzWsk7MaxPain({ opcje, S }) {
  const opis = { nr: 7, nazwa: "Max pain", dymek: "Poziom indeksu, przy którym na wygaśnięciu posiadacze opcji (calli i putów razem) straciliby najwięcej, liczony dla terminu od 7 do 45 dni z największą liczbą otwartych kontraktów. Przed wygaśnięciem cena bywa do niego przyciągana, ale to słaba zależność: traktuj jako tło, nie sygnał." };
  const naTermin = new Map();
  for (const o of opcje) if (o.days >= 7 && o.days <= 45) naTermin.set(o.expiry, (naTermin.get(o.expiry) || 0) + pzOi(o));
  if (!naTermin.size) return { ...opis, ...pzBrak("brak terminu 7–45 dni") };
  const [expiry, oiTerminu] = [...naTermin.entries()].reduce((a, b) => (b[1] > a[1] ? b : a));
  const lista = opcje.filter((o) => o.expiry === expiry && pzOi(o) > 0);
  if (!lista.length) return { ...opis, ...pzBrak("brak otwartych pozycji") };
  const strike = [...new Set(lista.map((o) => o.strike))];
  let najlepszy = null;
  for (const K of strike) {
    let bol = 0;
    for (const o of lista) bol += pzOi(o) * (o.typ === "C" ? Math.max(K - o.strike, 0) : Math.max(o.strike - K, 0));
    if (!najlepszy || bol < najlepszy.bol) najlepszy = { K, bol };
  }
  const dni = lista[0].days;
  return { ...opis, wartosc: `${pzLiczba(najlepszy.K, 0)} (${pzZeZnakiem((najlepszy.K / S - 1) * 100, 1)}%)`, pod: `termin ${pzDataKrotka(expiry)} (${dni} dni) · ${pzLiczba(oiTerminu, 0)} kontraktów`, stan: "info" };
}

function pzWsk8Gex({ opcje, S }) {
  const opis = { nr: 8, nazwa: "Ekspozycja gamma (GEX)", dymek: "Suma gamma × otwarte kontrakty × 100 × S² × 1%, z callami dodatnio i putami ujemnie (uproszczone założenie: animatorzy rynku mają kupione calle i sprzedane puty). Wynik w USD na 1% ruchu indeksu. Dodatnia wartość: zabezpieczając się, animatorzy kupują w spadkach i sprzedają we wzrostach, co tłumi ruchy (zielony). Ujemna: ruchy przyspieszają w obie strony (czerwony)." };
  let gex = 0;
  let oiSuma = 0;
  for (const o of opcje) {
    const oi = pzOi(o);
    const g = Number(o.surowe?.gamma) || 0;
    if (!oi || !g) continue;
    gex += (o.typ === "C" ? 1 : -1) * g * oi * PZ_MNOZNIK * S * S * 0.01;
    oiSuma += oi;
  }
  if (!oiSuma) return { ...opis, ...pzBrak("brak gamma i otwartych pozycji") };
  const abs = Math.abs(gex);
  const tekst = abs >= 1e9 ? `${pzZeZnakiem(gex / 1e9, 2)} mld USD` : abs >= 1e6 ? `${pzZeZnakiem(gex / 1e6, 1)} mln USD` : `${pzZeZnakiem(gex / 1e3, 0)} tys. USD`;
  const malo = oiSuma < 3000;
  return { ...opis, wartosc: tekst, pod: `na 1% ruchu indeksu${malo ? " · mało pozycji" : ""}`, stan: malo ? "info" : gex > 0 ? "dobrze" : "zle" };
}

function pzWsk9Trend({ historia }) {
  const opis = { nr: 9, nazwa: "Trend indeksu", dymek: "Odległość ostatniego zamknięcia indeksu od średniej z 50 sesji. Silny trend w górę zagraża sprzedanym callom, bo indeks szybciej dochodzi do strike'ów. Zielony do +2%, żółty od +2 do +4%, czerwony powyżej +4%. Indeks pod średnią sprzyja call spreadom (choć sam ETF wtedy traci)." };
  if (historia.length < 51) return { ...opis, ...pzBrak("za krótka historia") };
  const ost = historia[historia.length - 1];
  const sma = historia.slice(-50).reduce((a, b) => a + b, 0) / 50;
  const d = (ost / sma - 1) * 100;
  return { ...opis, wartosc: `${pzZeZnakiem(d, 1)}%`, pod: `zamknięcie ${pzLiczba(ost, 0)} · średnia 50 sesji ${pzLiczba(sma, 0)}`, stan: d <= 2 ? "dobrze" : d <= 4 ? "uwaga" : "zle" };
}

function pzWsk10DeltaPortfela({ profil, cenaEtf, Sindeks, otwarte }) {
  const opis = { nr: 10, nazwa: "Delta portfela", dymek: "Ile USD zarabia albo traci cała pozycja, gdy indeks wzrośnie o 1 punkt (zadanie 007). ETF: wartość ETF podzielona przez poziom indeksu (np. 15 000 USD przy indeksie 750 to 20 USD na punkt). Otwarte spready: suma (−delta nogi sprzedanej + delta nogi kupionej) × 100 × liczba kontraktów, z bieżącego łańcucha CBOE. Wynik dodatni oznacza, że portfel zyskuje na wzroście indeksu." };
  if (!(cenaEtf > 0) || !(Sindeks > 0)) return { ...opis, ...pzBrak("brak ceny ETF albo indeksu") };
  const etf = (profil.ilosc * cenaEtf) / Sindeks;
  const zDelta = otwarte.filter((o) => o.delta != null);
  const spready = zDelta.reduce((a, o) => a + o.delta * PZ_MNOZNIK, 0);
  const razem = etf + spready;
  const bezWyceny = otwarte.length - zDelta.length;
  return { ...opis, wartosc: `${pzZeZnakiem(razem, 1)} USD/pkt`, pod: `ETF ${pzLiczba(etf, 1)} · spready ${pzZeZnakiem(spready, 1)} · 1% indeksu ≈ ${pzZeZnakiem((razem * Sindeks) / 100, 0)} USD${bezWyceny ? ` · ${bezWyceny} bez wyceny` : ""}`, stan: "info" };
}

function pzWskazniki(kontekst) {
  return [
    pzWsk1PremiaZmiennosci(kontekst),
    pzWsk2OczekiwanyRuch(kontekst),
    pzWsk3Skosnosc(kontekst),
    pzWsk4StrukturaTerminowa(kontekst),
    pzWsk5PutCall(kontekst),
    pzWsk6ScianaCall(kontekst),
    pzWsk7MaxPain(kontekst),
    pzWsk8Gex(kontekst),
    pzWsk9Trend(kontekst),
    pzWsk10DeltaPortfela(kontekst),
  ];
}

// ---------------------------------------------------------------------------
// Ocena zakładów i wybór trzech propozycji (specyfikacja, sekcja 4).
// ---------------------------------------------------------------------------
// Kandydat: termin 7–60 dni, premia z cen środkowych dodatnia, strike sprzedany nad
// indeksem, P przebicia sprzedanej opcji najwyżej 35%.
function pzOcenZaklad(z, { S, sciana }) {
  const ruch1s = z.ivSprzedanejNogi > 0 ? S * z.ivSprzedanejNogi * Math.sqrt(z.days / 365) : null;
  const ev = z.punkty ?? 0;
  const kryteria = [
    { nazwa: "Punkty EV z arkusza", pkt: ev, max: 5, ok: ev >= 3, opis: `${ev} z 5`, dymek: "Po punkcie za: P przebicia poniżej 50%, EV opcji dodatnie i trzy porównania rocznego EV scenariusza „indeks powyżej strike'u” (z dryfem, z samym ETF i ze scenariuszem przeciwnym)." },
    { nazwa: "Płynność min. 3 z 5", pkt: z.punktyPlynnosci >= 3 ? 1 : 0, max: 1, opis: `${z.punktyPlynnosci} z 5`, dymek: "Punkty płynności z zadania 033: wąskie widełki obu nóg, otwarte pozycje, obrót, świeże transakcje i głębokość kwotowania." },
    { nazwa: "Premia od razu dodatnia", pkt: z.premiaRynkowaUsd > 0 ? 1 : 0, max: 1, opis: pzUsd(z.premiaRynkowaUsd), dymek: "Sprzedaż nogi sprzedanej po bid i kupno nogi kupionej po ask daje premię większą od zera, czyli zakład da się otworzyć od razu, bez czekania na zlecenie z limitem." },
    { nazwa: "Strike na ścianie call lub wyżej", pkt: sciana != null && z.strikeSprzedany >= sciana ? 1 : 0, max: 1, opis: sciana != null ? `ściana ${pzLiczba(sciana, 0)}` : "brak ściany", dymek: "Krótki call na poziomie największego skupiska otwartych calli albo nad nim (wskaźnik 6)." },
    { nazwa: "Strike poza ruchem 1σ", pkt: ruch1s != null && z.strikeSprzedany > S + ruch1s ? 1 : 0, max: 1, opis: ruch1s != null ? `granica ${pzLiczba(S + ruch1s, 0)}` : "brak IV", dymek: "Krótki call dalej od ceny niż jedno odchylenie standardowe ruchu indeksu do wygaśnięcia, liczone z IV nogi sprzedanej (S × IV × √(dni/365))." },
    { nazwa: "Termin 14–45 dni", pkt: z.days >= 14 && z.days <= 45 ? 1 : 0, max: 1, opis: `${z.days} dni`, dymek: "W tym przedziale wartość czasowa opcji spada najszybciej przy rozsądnym czasie na reakcję." },
  ];
  for (const k of kryteria) if (k.ok == null) k.ok = k.pkt > 0;
  const ocena = kryteria.reduce((a, k) => a + k.pkt, 0);
  const kandydat = z.days >= 7 && z.days <= 60 && z.premia > 0 && z.strikeSprzedany > S && z.pSC != null && z.pSC <= 0.35;
  return { ...z, ocena, kryteria, kandydat, klucz: `${z.kontrakty}|${z.strikeSprzedany}|${z.strikeKupiony}|${z.expiry}` };
}

function pzWybierzPropozycje(zaklady) {
  const kandydaci = zaklady.filter((z) => z.kandydat);
  if (!kandydaci.length) return [];
  const evLub = (z) => (z.evOpcji == null ? -Infinity : z.evOpcji);
  const wynik = [];
  const zajete = new Set();
  const dodaj = (rodzaj, dymek, z) => {
    if (!z) return;
    wynik.push({ rodzaj, dymek, z });
    zajete.add(z.klucz);
  };
  dodaj("Najwyższa ocena", "Zakład z najwyższą oceną 0–10 (przy remisie wyższe EV opcji, potem wyższa premia dzienna).",
    [...kandydaci].sort((a, b) => b.ocena - a.ocena || evLub(b) - evLub(a) || b.dailyPremia - a.dailyPremia)[0]);
  const dobre = () => kandydaci.filter((z) => z.ocena >= 6 && !zajete.has(z.klucz));
  // Premia co najmniej 10% maksymalnej straty: bez tego „najbezpieczniejszy" bywa zakład za
  // kilka dolarów przy ryzyku kilkuset (np. 5 USD premii przy 495 USD możliwej straty).
  dodaj("Najbezpieczniejsza", "Najniższe prawdopodobieństwo przebicia sprzedanej opcji wśród zakładów z oceną co najmniej 6 i premią równą co najmniej 10% maksymalnej straty.",
    dobre().filter((z) => z.premia * PZ_MNOZNIK >= 0.1 * z.maxStrata).sort((a, b) => a.pSC - b.pSC || b.ocena - a.ocena)[0]);
  dodaj("Najwyższa premia dzienna", "Najwyższa premia na dzień do wygaśnięcia wśród zakładów z oceną co najmniej 6.",
    dobre().sort((a, b) => b.dailyPremia - a.dailyPremia || b.ocena - a.ocena)[0]);
  return wynik;
}

// ---------------------------------------------------------------------------
// Historia zakładów w repozytorium (ustawienia/historia-zakladow.csv) przez moduł PR
// (shared/projekty.js, ten sam token GitHub co reszta stron).
// ---------------------------------------------------------------------------
function pzParsujCsv(tekst) {
  const linie = String(tekst || "").split("\n").map((l) => l.replace(/\r$/, "")).filter((l) => l.length > 0);
  if (!linie.length) return { naglowek: [...PZ_KOLUMNY_CSV], wiersze: [] };
  const naglowek = linie[0].split(",");
  const wiersze = linie.slice(1).map((linia) => {
    const wartosci = linia.split(",");
    const w = {};
    naglowek.forEach((k, i) => (w[k] = wartosci[i] ?? ""));
    return w;
  });
  for (const k of PZ_KOLUMNY_CSV) if (!naglowek.includes(k)) naglowek.push(k);
  return { naglowek, wiersze };
}

function pzSerializujCsv(naglowek, wiersze) {
  const linie = [naglowek.join(",")];
  for (const w of wiersze) linie.push(naglowek.map((k) => String(w[k] ?? "").replace(/[,\n\r]/g, " ")).join(","));
  return linie.join("\n") + "\n";
}

function pzTokenJest() {
  return typeof PR !== "undefined" && !!PR.token();
}

// Odczyt świeżej wersji -> mutuj(wiersze) -> zapis; przy konflikcie ponawia na nowej kopii.
async function pzZmienHistorie(mutuj, opis) {
  for (let proba = 0; proba < 3; proba++) {
    const plik = await PR.odczytaj(PZ_HISTORIA);
    const { naglowek, wiersze } = pzParsujCsv(plik ? plik.tresc : "");
    mutuj(wiersze);
    try {
      await PR.zapiszTekst(PZ_HISTORIA, pzSerializujCsv(naglowek, wiersze), plik ? plik.sha : null, opis);
      return wiersze;
    } catch (e) {
      if (e.kod !== 409 && e.kod !== 422) throw e;
    }
  }
  throw new Error("Plik historii zmienił się w międzyczasie, spróbuj ponownie.");
}

async function pzWczytajHistorie() {
  if (!pzTokenJest()) {
    pz.otwarte = [];
    pz.zamkniete = [];
    pz.historiaStan = window.WERSJA_POGLADOWA ? "Historia zakładów jest wyłączona w wersji poglądowej (w pełnej platformie zapisuje się w repozytorium przez token GitHub)." : "Wklej token GitHub w oknie 1, żeby widzieć i zapisywać zakłady.";
    return;
  }
  try {
    const plik = await PR.odczytaj(PZ_HISTORIA);
    const { wiersze } = pzParsujCsv(plik ? plik.tresc : "");
    pz.otwarte = wiersze.filter((w) => !w.data_zamkniecia);
    pz.zamkniete = wiersze.filter((w) => w.data_zamkniecia).slice(-5).reverse();
    pz.historiaStan = "";
  } catch (e) {
    pz.historiaStan = `Nie udało się wczytać historii: ${e.message}`;
  }
}

// Bieżąca wycena otwartych spreadów z łańcucha aktywnego profilu (po symbolu i dacie).
function pzWycenOtwarte(wiersze, profil, opcje) {
  const calle = new Map();
  for (const o of opcje) if (o.typ === "C") calle.set(`${pzDataIso(o.expiry)}|${o.strike}`, o);
  const dzis = pzDzisiajUTC();
  return wiersze.map((w) => {
    const n = Number(w.kontrakty) || 1;
    const wynik = { wiersz: w, n, premia: Number(w.premia_otrzymana) || 0, wycena: null, wynikTeraz: null, delta: null, theta: null, dni: null, tenProfil: w.symbol === profil.cboe };
    if (w.expiry) wynik.dni = Math.round((Date.parse(w.expiry) - dzis) / 86400000);
    if (!wynik.tenProfil || !w.expiry) return wynik;
    const s = calle.get(`${w.expiry}|${Number(w.strike_krotki)}`);
    const k = calle.get(`${w.expiry}|${Number(w.strike_dlugi)}`);
    if (!s || !k) return wynik;
    const cena = (o) => (o.mid != null ? o.mid : Number(o.surowe?.theo) > 0 ? Number(o.surowe.theo) : null);
    const cs = cena(s);
    const ck = cena(k);
    if (cs != null && ck != null) {
      wynik.wycena = (cs - ck) * PZ_MNOZNIK * n; // koszt odkupienia spreadu teraz
      wynik.wynikTeraz = wynik.premia - wynik.wycena;
    }
    wynik.delta = (-s.delta + k.delta) * n;
    wynik.theta = (-s.theta + k.theta) * PZ_MNOZNIK * n; // USD dziennie, dodatnia = zarabiasz na upływie czasu
    return wynik;
  });
}

async function pzOtworzZaklad(z, przycisk) {
  const profil = pzProfil();
  if (!pzTokenJest()) {
    alert(window.WERSJA_POGLADOWA ? "W wersji poglądowej zapis zakładów jest wyłączony." : "Zapis wymaga tokenu GitHub: wklej go w oknie 1.");
    return;
  }
  if (!confirm(`Zapisać zakład ${z.zaklad} (${profil.cboe}, wygasa ${pzDataIso(z.expiry)}) jako otwarty w historii zakładów?`)) return;
  const tekst = przycisk.textContent;
  przycisk.disabled = true;
  przycisk.textContent = "Zapisywanie…";
  try {
    const wiersz = {
      id: String(Date.now()),
      data_otwarcia: pzDzisiajIso(),
      data_zamkniecia: "",
      strike_krotki: String(z.strikeSprzedany),
      strike_dlugi: String(z.strikeKupiony),
      dni_T: String(z.days),
      premia_otrzymana: String(Math.round(z.premia * PZ_MNOZNIK * 100) / 100),
      wynik_dolary: "",
      stawka_zaangazowana: String(Math.round(z.maxStrata * 100) / 100),
      wynik_procent_stawki: "",
      kontrakty: String(z.kontrakty),
      symbol: profil.cboe,
      expiry: pzDataIso(z.expiry),
    };
    await pzZmienHistorie((wiersze) => wiersze.push(wiersz), `Otworz zaklad ${z.strikeKupiony}/${z.strikeSprzedany} ${profil.cboe} ${wiersz.expiry} z karty Pozycja`);
    przycisk.textContent = "Zapisano ✓";
    await pzWczytajHistorie();
    pzPrzelicz();
  } catch (e) {
    przycisk.textContent = tekst;
    przycisk.disabled = false;
    alert(`Nie udało się zapisać: ${e.message}`);
  }
}

async function pzZamknijZaklad(id, data, wynikUsd, przycisk) {
  const w = pz.otwarte.find((x) => x.id === id);
  const stawka = Number(w?.stawka_zaangazowana) || 0;
  przycisk.disabled = true;
  przycisk.textContent = "Zapisywanie…";
  try {
    await pzZmienHistorie((wiersze) => {
      const i = wiersze.findIndex((x) => x.id === id);
      if (i === -1) throw new Error(`Nie ma w historii zakładu o id ${id}`);
      wiersze[i] = { ...wiersze[i], data_zamkniecia: data, wynik_dolary: String(wynikUsd), wynik_procent_stawki: stawka ? String(wynikUsd / stawka) : "" };
    }, `Zamknij zaklad ${id} (${data}) z karty Pozycja`);
    await pzWczytajHistorie();
    pzPrzelicz();
  } catch (e) {
    przycisk.disabled = false;
    przycisk.textContent = "Zamknij";
    alert(`Nie udało się zapisać: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Profile i ustawienia: repozytorium (ustawienia/pozycja.json przez USTAW) z podręczną
// kopią w localStorage, żeby strona od razu pokazała ostatni profil.
// ---------------------------------------------------------------------------
function pzNormalizujUstawienia(u) {
  const d = JSON.parse(JSON.stringify(PZ_USTAWIENIA_DOMYSLNE));
  if (!u || typeof u !== "object") return d;
  const profile = Array.isArray(u.profile) && u.profile.length
    ? u.profile.map((p) => {
        const wynik = { ...PZ_PROFIL_PUSTY, ...p, id: String(p.id || pzNoweId()) };
        for (const k of PZ_POLA_LICZBOWE) wynik[k] = Number(wynik[k]) || 0;
        if (!(wynik.pokrycie > 0)) wynik.pokrycie = 100;
        return wynik;
      })
    : d.profile;
  const aktywny = profile.some((p) => p.id === u.aktywny) ? u.aktywny : profile[0].id;
  return { wersja: 1, aktywny, profile, tabela: { ...d.tabela, ...(u.tabela || {}) } };
}

function pzProfil() {
  const u = pz.ustawienia;
  return u.profile.find((p) => p.id === u.aktywny) || u.profile[0];
}

function pzUstawZapis(tekst, blad = false) {
  const el = pzEl("pz-zapis");
  if (!el) return;
  el.textContent = tekst;
  el.classList.toggle("blad", !!blad);
}

function pzZapiszCache() {
  try {
    localStorage.setItem(PZ_CACHE, JSON.stringify(pz.ustawienia));
  } catch (e) {
    /* tryb prywatny: zostaje zapis w repozytorium */
  }
}

async function pzWczytajUstawienia() {
  let lokalne = null;
  try {
    lokalne = JSON.parse(localStorage.getItem(PZ_CACHE) || "null");
  } catch (e) {
    /* brak kopii */
  }
  pz.ustawienia = pzNormalizujUstawienia(lokalne);
  const form = pzEl("pz-formularz");
  if (form) form.dataset.profil = ""; // nowe wartości tego samego profilu: formularz od nowa
  if (typeof USTAW === "undefined" || !USTAW.dostepne()) {
    pzUstawZapis(window.WERSJA_POGLADOWA ? "Wersja poglądowa: profile zostają tylko w tej przeglądarce." : "Bez tokenu GitHub profile zostają tylko w tej przeglądarce (wklej token wyżej).");
    return;
  }
  try {
    const { wartosc } = await USTAW.wczytaj(PZ_KLUCZ, null);
    if (wartosc) {
      pz.ustawienia = pzNormalizujUstawienia(wartosc);
      if (form) form.dataset.profil = "";
      pzZapiszCache();
      pzUstawZapis("Profile z repozytorium (ustawienia/pozycja.json).");
    } else {
      pzUstawZapis("Profile domyślne; pierwsza zmiana zapisze je w repozytorium.");
    }
  } catch (e) {
    pzUstawZapis(`Nie udało się wczytać profili z repozytorium: ${e.message}`, true);
  }
}

let pzTimerZapisu = null;
function pzZaplanujZapis(opis) {
  pzZapiszCache();
  clearTimeout(pzTimerZapisu);
  pzTimerZapisu = setTimeout(() => pzZapiszUstawienia(opis), 1200);
}

async function pzZapiszUstawienia(opis) {
  if (typeof USTAW === "undefined" || !USTAW.dostepne()) {
    pzUstawZapis(window.WERSJA_POGLADOWA ? "Wersja poglądowa: zapisano tylko w tej przeglądarce." : "Zapisano tylko w tej przeglądarce (brak tokenu GitHub).", true);
    return;
  }
  pzUstawZapis("Zapisywanie profili…");
  const kopia = JSON.parse(JSON.stringify(pz.ustawienia));
  try {
    await USTAW.zmien(PZ_KLUCZ, null, () => kopia, opis);
    pzUstawZapis(`Zapisano w repozytorium o ${new Date().toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}.`);
  } catch (e) {
    pzUstawZapis(`Błąd zapisu profili: ${e.message}`, true);
  }
}

// ---------------------------------------------------------------------------
// Przeliczenie całej strony z danych aktywnego profilu i pobieranie danych.
// ---------------------------------------------------------------------------
function pzPrzelicz() {
  const profil = pzProfil();
  const dane = pz.dane.get(pzKluczDanych(profil)) || null;
  const lancuch = dane?.lancuch || null;
  const opcje = lancuch ? lancuch.opcje : [];
  const migawka = lancuch ? lancuch.migawka : null;
  // S: cena indeksu z Yahoo (jak w starej karcie, ta sama chwila co cena ETF); Sc: cena z
  // migawki CBOE, w której są też ceny opcji (wskaźniki z łańcucha).
  const S = dane?.indeks?.cena ?? migawka?.cena ?? null;
  const Sc = migawka?.cena ?? S;
  const cenaEtf = dane?.etf?.cena ?? null;
  const wynik = { profil, dane, opcje, migawka, S, Sc, cenaEtf, zaklady: null, komunikatZakladow: "", wskazniki: [], propozycje: [], sciana: null, otwarte: [] };
  wynik.otwarte = pzWycenOtwarte(pz.otwarte, profil, opcje);
  if (dane) {
    wynik.wskazniki = pzWskazniki({ opcje, migawka, historia: dane.historia, S: Sc, profil, cenaEtf, Sindeks: S, otwarte: wynik.otwarte.filter((o) => o.tenProfil) });
    wynik.sciana = wynik.wskazniki.find((x) => x.nr === 6)?.strike ?? null;
  }
  if (!dane) wynik.komunikatZakladow = "Pobieranie danych…";
  else if (!opcje.length) wynik.komunikatZakladow = "Brak łańcucha opcji CBOE dla tego profilu.";
  else if (!(cenaEtf > 0) || !(S > 0)) wynik.komunikatZakladow = "Brak ceny ETF albo indeksu z Yahoo.";
  else if (!(profil.ilosc > 0)) wynik.komunikatZakladow = "Uzupełnij liczbę jednostek ETF i cenę kupna w parametrach profilu (okno 1): od nich zależą progi zakładów.";
  else {
    const { progi, kontekst } = pzProgi(profil, cenaEtf, S);
    const surowe = generujZaklady(progi, opcje, profil.pokrycie, Math.max(1, Math.floor(profil.maksKontraktow) || 1), kontekst);
    const kp = kontekstPlynnosciLancucha(opcje);
    const unikalne = new Map();
    for (const z0 of surowe) {
      const zEv = dolozEV(z0, { S: kontekst.index, mu: profil.dryf / 100, cenaNabycia: profil.cenaKupna, ilosc: profil.ilosc, cenaRynkowa: cenaEtf });
      const z = pzOcenZaklad(dolozPlynnosc(zEv, kp), { S, sciana: wynik.sciana });
      if (!unikalne.has(z.klucz)) unikalne.set(z.klucz, z);
    }
    wynik.zaklady = [...unikalne.values()];
    // Delta portfela w USD na 1 punkt indeksu, gdyby dołożyć ten zakład (zadanie 007):
    // ETF = wartość / indeks, spread = delta × 100 × kontrakty (deltaPortfela ma już × kontrakty).
    wynik.deltaEtf = (profil.ilosc * cenaEtf) / S;
    for (const z of wynik.zaklady) z.deltaUsd = wynik.deltaEtf + z.deltaPortfela * PZ_MNOZNIK;
    wynik.progi = progi;
    wynik.kontekst = kontekst;
    wynik.propozycje = pzWybierzPropozycje(wynik.zaklady);
    if (!wynik.zaklady.length) wynik.komunikatZakladow = "Generator nie znalazł zakładów dla tych progów: sprawdź ryzyko nominalne i % pokrycia.";
  }
  pz.wynik = wynik;
  const stary = pz.wybrany?.klucz;
  pz.wybrany = (wynik.zaklady || []).find((z) => z.klucz === stary) || wynik.propozycje[0]?.z || null;
  pzRysujWszystko();
}

function pzRysujWszystko() {
  pzRysujPozycje();
  pzRysujWskazniki();
  pzRysujPropozycje();
  pzRysujWykres();
  pzRysujTabele();
  pzRysujOtwarte();
}

function pzUstawStan(tekst, blad = false) {
  const el = pzEl("pz-stan");
  el.textContent = tekst;
  el.classList.toggle("blad", !!blad);
}

function pzOpisDanych(dane) {
  const czesci = [];
  if (dane.lancuch?.migawka?.czas) czesci.push(`łańcuch CBOE z ${String(dane.lancuch.migawka.czas).slice(0, 16)} (opóźniony)`);
  if (PZ_PROBKA) czesci.push("zapisana próbka, nie dane na żywo");
  else czesci.push(`pobrano o ${new Date(dane.czas).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}`);
  return czesci.join(" · ");
}

let pzNumerPobrania = 0;
async function pzOdswiez(wymus = false) {
  const profil = pzProfil();
  const klucz = pzKluczDanych(profil);
  const dane = pz.dane.get(klucz);
  if (!wymus && dane && Date.now() - dane.czas < PZ_WAZNOSC_DANYCH_MS) {
    pzPrzelicz();
    pzUstawStan(pzOpisDanych(dane));
    return;
  }
  if (!profil.cboe || !profil.etf || !profil.indeks) {
    pzPrzelicz();
    pzUstawStan("Uzupełnij ETF, indeks i symbol CBOE w parametrach profilu.", true);
    return;
  }
  const numer = ++pzNumerPobrania;
  const przycisk = pzEl("pz-odswiez");
  przycisk.disabled = true;
  pzUstawStan(PZ_PROBKA ? `Wczytywanie zapisanej próbki łańcucha opcji ${profil.cboe} i cen…` : `Pobieranie łańcucha opcji ${profil.cboe} z CBOE i cen z Yahoo…`);
  if (!dane) pzPrzelicz();
  try {
    const nowe = await pzPobierzDaneProfilu(profil);
    pz.dane.set(klucz, nowe);
    if (numer !== pzNumerPobrania || pzKluczDanych(pzProfil()) !== klucz) return; // w międzyczasie zmieniono profil
    pzPrzelicz();
    pzUstawStan(nowe.bledy.length ? `Część danych niedostępna: ${nowe.bledy.join("; ")}` : pzOpisDanych(nowe), nowe.bledy.length > 0);
  } finally {
    if (numer === pzNumerPobrania) przycisk.disabled = false;
  }
}

// ===========================================================================
// ELEMENT: okno 1 „Pozycja"
// ===========================================================================
function pzRysujPozycje() {
  const u = pz.ustawienia;
  const profil = pzProfil();
  pzEl("pz-profile").innerHTML =
    u.profile.map((p) => `<button type="button" class="pz-profil${p.id === u.aktywny ? " aktywny" : ""}" data-profil="${pzEsc(p.id)}" role="tab" aria-selected="${p.id === u.aktywny}">${pzEsc(p.nazwa || p.id)}</button>`).join("") +
    `<button type="button" class="pz-profil pz-profil-nowy" data-akcja="nowy" title="Nowy profil: kopia bieżącego do zmiany w parametrach">+</button>`;

  const w = pz.wynik;
  const etf = w?.dane?.etf;
  const ind = w?.dane?.indeks;
  const pola = [];
  if (etf) {
    const wartosc = profil.ilosc * etf.cena;
    const zysk = profil.cenaKupna > 0 ? profil.ilosc * (etf.cena - profil.cenaKupna) : null;
    pola.push(`<div class="pz-pole-sum" title="Liczba jednostek × bieżąca cena ETF; poniżej wynik względem ceny kupna"><span>${pzEsc(profil.etf)} · ${pzLiczba(profil.ilosc, 0)} szt.</span><b>${pzLiczba(wartosc, 0)} ${pzEsc(etf.waluta)}</b><small class="${pzKlasaZnaku(zysk)}">${zysk == null ? "brak ceny kupna" : `${pzZeZnakiem(zysk, 0)} (${pzZeZnakiem((etf.cena / profil.cenaKupna - 1) * 100, 1)}%) od kupna`}</small></div>`);
  }
  if (ind) {
    const zm = ind.poprzednia ? (ind.cena / ind.poprzednia - 1) * 100 : null;
    pola.push(`<div class="pz-pole-sum" title="Cena indeksu z Yahoo i zmiana od poprzedniego zamknięcia"><span>${pzEsc(profil.indeks)}</span><b>${pzLiczba(ind.cena, 2)}</b><small class="${pzKlasaZnaku(zm)}">${zm == null ? "" : `${pzZeZnakiem(zm, 2)}% dziś`}</small></div>`);
  }
  if (w?.migawka?.iv30 > 0) {
    pola.push(`<div class="pz-pole-sum" title="IV30: zmienność implikowana indeksu na 30 dni z CBOE, w skali roku; poniżej zmiana od poprzedniej sesji"><span>IV30 (CBOE)</span><b>${pzLiczba(w.migawka.iv30, 1)}%</b><small>${w.migawka.zmianaIv30 ? `${pzZeZnakiem(w.migawka.zmianaIv30, 2)} pkt proc.` : ""}</small></div>`);
  }
  if (w?.zaklady) {
    pola.push(`<div class="pz-pole-sum" title="Liczba zakładów z generatora i kandydatów do propozycji (7–60 dni, premia dodatnia, strike nad indeksem, P przebicia do 35%)"><span>Zakłady</span><b>${pzLiczba(w.zaklady.length, 0)}</b><small>${pzLiczba(w.zaklady.filter((z) => z.kandydat).length, 0)} kandydatów</small></div>`);
  }
  pzEl("pz-podsumowanie").innerHTML = pola.join("");

  // Formularz rysujemy tylko przy zmianie profilu, żeby nie gubić kursora podczas pisania.
  const form = pzEl("pz-formularz");
  if (form.dataset.profil !== profil.id) {
    form.dataset.profil = profil.id;
    form.innerHTML = PZ_POLA.map((p) => `<label title="${pzEsc(p.dymek)}">${pzEsc(p.etykieta)}<input data-pole="${p.klucz}" type="${p.typ}"${p.krok ? ` step="${p.krok}"` : ""} value="${pzEsc(profil[p.klucz])}" /></label>`).join("");
    if (!(profil.ilosc > 0) || !profil.cboe) pzEl("pz-parametry").open = true;
  }
  pzEl("pz-usun-profil").disabled = u.profile.length < 2;
  pzEl("pz-token").hidden = pzTokenJest() || !!window.WERSJA_POGLADOWA; // w wersji poglądowej pola tokenu nie ma
}

let pzTimerPola = null;
function pzZmianaPola(input) {
  const profil = pzProfil();
  const pole = PZ_POLA.find((p) => p.klucz === input.dataset.pole);
  if (!pole) return;
  profil[pole.klucz] = pole.typ === "number" ? Number(input.value) || 0 : input.value.trim();
  pzZaplanujZapis(`profil ${profil.nazwa}: ${pole.etykieta}`);
  clearTimeout(pzTimerPola);
  if (pole.klucz === "nazwa") {
    pzRysujPozycje();
    return;
  }
  pzTimerPola = setTimeout(() => (pole.pobierz ? pzOdswiez(false) : pzPrzelicz()), pole.pobierz ? 900 : 350);
}

function pzWybierzProfil(id) {
  if (id === pz.ustawienia.aktywny) return;
  pz.ustawienia.aktywny = id;
  pz.wybrany = null;
  pzZaplanujZapis(`aktywny profil ${pzProfil().nazwa}`);
  pzOdswiez(false);
}

function pzNowyProfil() {
  const p = { ...pzProfil(), id: pzNoweId(), nazwa: `Kopia: ${pzProfil().nazwa}` };
  pz.ustawienia.profile.push(p);
  pzWybierzProfil(p.id);
  pzEl("pz-parametry").open = true;
}

function pzUsunProfil() {
  const u = pz.ustawienia;
  if (u.profile.length < 2) return;
  const p = pzProfil();
  if (!confirm(`Usunąć profil „${p.nazwa}"?`)) return;
  u.profile = u.profile.filter((x) => x.id !== p.id);
  u.aktywny = u.profile[0].id;
  pzZaplanujZapis(`usunięty profil ${p.nazwa}`);
  pzOdswiez(false);
}

function pzPozycjaInicjuj() {
  pzEl("pz-odswiez").addEventListener("click", () => pzOdswiez(true));
  pzEl("pz-profile").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.akcja === "nowy") pzNowyProfil();
    else if (b.dataset.profil) pzWybierzProfil(b.dataset.profil);
  });
  pzEl("pz-formularz").addEventListener("input", (e) => {
    if (e.target.matches("input[data-pole]")) pzZmianaPola(e.target);
  });
  pzEl("pz-usun-profil").addEventListener("click", pzUsunProfil);
  pzEl("pz-token-zapisz").addEventListener("click", async () => {
    const t = pzEl("pz-token-pole").value.trim();
    if (!t) return;
    PR.ustawToken(t);
    pzEl("pz-token-pole").value = "";
    await pzWczytajUstawienia();
    await pzWczytajHistorie();
    pzOdswiez(false);
  });
}

// ===========================================================================
// ELEMENT: okno 2 „Wskaźniki rynku opcji"
// ===========================================================================
function pzRysujWskazniki() {
  const lista = pz.wynik?.wskazniki || [];
  const host = pzEl("pz-wskazniki");
  const bar = pzEl("pz-barometr");
  if (!lista.length) {
    host.innerHTML = `<div class="pz-pusto">${pz.wynik?.dane ? "Brak danych do wskaźników." : "Pobieranie danych…"}</div>`;
    bar.innerHTML = "";
    return;
  }
  host.innerHTML = lista.map((x) => `<div class="pz-wsk pz-${x.stan}" title="${pzEsc(x.dymek)}"><span class="pz-wsk-nazwa"><b>${x.nr}</b> ${pzEsc(x.nazwa)}</span><span class="pz-wsk-wartosc">${pzEsc(x.wartosc)}</span><span class="pz-wsk-pod">${pzEsc(x.pod || "")}</span></div>`).join("");
  const sygnaly = lista.filter((x) => PZ_BAROMETR.includes(x.nr));
  const ile = sygnaly.filter((x) => x.stan === "dobrze").length;
  const kolor = ile >= 4 ? "dobrze" : ile >= 2 ? "uwaga" : "zle";
  bar.className = `pz-barometr pz-${kolor}`;
  bar.innerHTML = `<b>Barometr: ${ile} z ${sygnaly.length}</b><span>sygnałów sprzyja sprzedaży call spreadu</span><span class="pz-segmenty">${sygnaly.map((x) => `<i class="pz-${x.stan}" title="${x.nr}. ${pzEsc(x.nazwa)}: ${pzEsc(x.wartosc)}"></i>`).join("")}</span>`;
  bar.title = "Liczy zielone kafelki wśród wskaźników 1, 3, 4, 5, 8 i 9, czyli tych, które oceniają warunki dla sprzedaży calli. Pozostałe (2, 6, 7, 10) to punkty odniesienia bez oceny.";
}

// ===========================================================================
// ELEMENT: okno 3 „Propozycje zakładów"
// ===========================================================================
function pzKolorOceny(o) {
  return o >= 8 ? "dobrze" : o >= 6 ? "uwaga" : "zle";
}

function pzRysujPropozycje() {
  const host = pzEl("pz-propozycje");
  const w = pz.wynik;
  if (!w || !w.zaklady) {
    host.innerHTML = `<div class="pz-pusto">${pzEsc(w?.komunikatZakladow || "Pobieranie danych…")}</div>`;
    return;
  }
  if (!w.propozycje.length) {
    host.innerHTML = `<div class="pz-pusto">Żaden zakład nie spełnia warunków propozycji (7–60 dni, premia dodatnia, strike sprzedany nad indeksem, P przebicia do 35%). Pełna lista jest w tabeli zakładów.</div>`;
    return;
  }
  host.innerHTML = w.propozycje.map(({ rodzaj, dymek, z }) => `
    <article class="pz-prop${pz.wybrany?.klucz === z.klucz ? " wybrana" : ""}" data-klucz="${pzEsc(z.klucz)}">
      <header><span class="pz-prop-rodzaj" title="${pzEsc(dymek)}">${pzEsc(rodzaj)}</span><span class="pz-ocena pz-${pzKolorOceny(z.ocena)}" title="Ocena 0–10">${z.ocena}/10</span></header>
      <div class="pz-prop-zaklad">${pzEsc(z.zaklad)}<small>${pzDataKrotka(z.expiry)} · ${z.days} dni</small></div>
      <dl class="pz-prop-liczby">
        <div title="Premia netto całej pozycji z cen środkowych obu nóg"><dt>Premia</dt><dd>${pzUsd(z.premia * PZ_MNOZNIK)}</dd></div>
        <div title="Szerokość spreadu × 100 × kontrakty minus premia"><dt>Maks. strata</dt><dd>${pzUsd(z.maxStrata)}</dd></div>
        <div title="Prawdopodobieństwo, że indeks zamknie się na wygaśnięciu powyżej strike'u sprzedanego (z dryfem µ i IV nogi sprzedanej)"><dt>P przebicia</dt><dd>${pzProcent(z.pSC, 0)}</dd></div>
        <div title="Premia minus oczekiwany koszt spreadu (z rachunku EV)"><dt>EV opcji</dt><dd class="${pzKlasaZnaku(z.evOpcji)}">${pzUsd(z.evOpcji)}</dd></div>
        <div title="Premia podzielona przez dni do wygaśnięcia"><dt>Dziennie</dt><dd>${pzUsd(z.dailyPremia, 2)}</dd></div>
        <div title="Premia po cenach rynkowych: sprzedaż po bid, kupno po ask"><dt>Od razu</dt><dd class="${pzKlasaZnaku(z.premiaRynkowaUsd)}">${pzUsd(z.premiaRynkowaUsd)}</dd></div>
      </dl>
      <ul class="pz-kryteria">${z.kryteria.map((k) => `<li class="${k.ok ? "tak" : "nie"}" title="${pzEsc(k.dymek)}"><span>${k.max > 1 ? `${k.pkt}/${k.max}` : k.pkt ? "✓" : "✗"}</span>${pzEsc(k.nazwa)}<small>${pzEsc(k.opis)}</small></li>`).join("")}</ul>
      <div class="pz-prop-akcje"><button type="button" class="t-mini" data-akcja="wykres">Pokaż na wykresie</button><button type="button" class="t-mini pz-mocny" data-akcja="otworz" title="Zapisz w historii zakładów (ustawienia/historia-zakladow.csv)">Zapisz jako otwarty</button></div>
    </article>`).join("");
}

function pzZakladPoKluczu(klucz) {
  return (pz.wynik?.zaklady || []).find((z) => z.klucz === klucz) || null;
}

function pzWybierzZaklad(klucz) {
  const z = pzZakladPoKluczu(klucz);
  if (!z) return;
  pz.wybrany = z;
  pzRysujPropozycje();
  pzRysujWykres();
  pzRysujTabele();
}

function pzPropozycjeInicjuj() {
  pzEl("pz-propozycje").addEventListener("click", (e) => {
    const karta = e.target.closest(".pz-prop");
    if (!karta) return;
    const b = e.target.closest("button");
    if (b?.dataset.akcja === "otworz") {
      const z = pzZakladPoKluczu(karta.dataset.klucz);
      if (z) pzOtworzZaklad(z, b);
      return;
    }
    pzWybierzZaklad(karta.dataset.klucz);
  });
}

// ===========================================================================
// ELEMENT: okno 4 „Wykres wypłaty" (SVG rysowane ręcznie, bez biblioteki)
// ===========================================================================
function pzLadneKroki(min, max, ile = 5) {
  const zakres = max - min;
  if (!(zakres > 0)) return [min];
  const potega = Math.pow(10, Math.floor(Math.log10(zakres / ile)));
  const krok = [1, 2, 2.5, 5, 10].map((m) => m * potega).find((k) => zakres / k <= ile) || 10 * potega;
  const wynik = [];
  for (let v = Math.ceil(min / krok) * krok; v <= max + 1e-9; v += krok) wynik.push(Math.round(v / krok) * krok + 0);
  return wynik;
}

function pzKrotkaLiczba(v) {
  const a = Math.abs(v);
  if (a >= 1e6) return pzLiczba(v / 1e6, 1) + " mln";
  if (a >= 1e4) return pzLiczba(v / 1e3, 0) + " tys.";
  return pzLiczba(v, a < 10 && a !== 0 ? 1 : 0);
}

function pzRysujWykres() {
  const host = pzEl("pz-wykres");
  const legenda = pzEl("pz-wykres-legenda");
  const tytul = pzEl("pz-wykres-zaklad");
  const w = pz.wynik;
  const z = pz.wybrany;
  if (!w || !z || !(w.S > 0) || !(w.cenaEtf > 0)) {
    host.innerHTML = `<div class="pz-pusto">${w?.zaklady ? "Wybierz zakład w propozycjach albo w tabeli zakładów." : pzEsc(w?.komunikatZakladow || "Pobieranie danych…")}</div>`;
    legenda.innerHTML = "";
    tytul.textContent = "";
    return;
  }
  const { profil, S, cenaEtf } = w;
  const n = z.kontrakty || 1;
  const K1 = z.strikeSprzedany;
  const K2 = z.strikeKupiony;
  const szer = K2 - K1;
  const premiaUsd = z.premia * PZ_MNOZNIK;
  const progRent = K1 + z.premia / n;
  const bazaKupna = profil.cenaKupna > 0 ? profil.cenaKupna : cenaEtf;
  const sT = z.ivSprzedanejNogi > 0 ? z.ivSprzedanejNogi * Math.sqrt(z.days / 365) : 0.03;
  const zakres = Math.max(2 * sT, 0.04);
  const xMin = S * (1 - zakres);
  const xMax = Math.max(S * (1 + zakres), K2 + (K2 - S) * 0.2);
  const policz = (x) => {
    const etf = profil.ilosc * (cenaEtf * (x / S) - bazaKupna);
    const spread = premiaUsd - Math.min(Math.max(x - K1, 0), szer) * PZ_MNOZNIK * n;
    return { x, etf, spread, razem: etf + spread };
  };
  const xs = [];
  for (let i = 0; i <= 200; i++) xs.push(xMin + ((xMax - xMin) * i) / 200);
  xs.push(K1, K2);
  const pkt = xs.filter((x) => x >= xMin && x <= xMax).sort((a, b) => a - b).map(policz);

  const W = Math.max(260, Math.floor(host.clientWidth || 480));
  const H = 280;
  const m = { l: 56, r: 10, t: 8, b: 22 };
  const przerwa = 16;
  const hGora = Math.round((H - m.t - m.b - przerwa) * 0.58);
  const hDol = H - m.t - m.b - przerwa - hGora;
  const yG = m.t;
  const yD = m.t + hGora + przerwa;
  const sx = (x) => m.l + ((x - xMin) / (xMax - xMin)) * (W - m.l - m.r);
  const skala = (wartosci, y0, h, zapas) => {
    let lo = Math.min(0, ...wartosci);
    let hi = Math.max(0, ...wartosci);
    const p = (hi - lo || 1) * zapas;
    lo -= p;
    hi += p;
    return { lo, hi, y: (v) => y0 + h - ((v - lo) / (hi - lo)) * h };
  };
  const gora = skala(pkt.flatMap((p) => [p.etf, p.razem]), yG, hGora, 0.08);
  const dol = skala(pkt.map((p) => p.spread), yD, hDol, 0.18);
  const sciezka = (klucz, sk) => pkt.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sk.y(p[klucz]).toFixed(1)}`).join("");
  const y0d = dol.y(0);
  const pole = `${sciezka("spread", dol)}L${sx(pkt[pkt.length - 1].x).toFixed(1)},${y0d.toFixed(1)}L${sx(pkt[0].x).toFixed(1)},${y0d.toFixed(1)}Z`;
  const pion = (x, klasa) => (x >= xMin && x <= xMax ? `<line class="${klasa}" x1="${sx(x).toFixed(1)}" x2="${sx(x).toFixed(1)}" y1="${yG}" y2="${yD + hDol}"/>` : "");
  const osY = (sk, y0, h, ile) => pzLadneKroki(sk.lo, sk.hi, ile).map((v) => `<line class="pz-svg-siatka${v === 0 ? " zero" : ""}" x1="${m.l}" x2="${W - m.r}" y1="${sk.y(v).toFixed(1)}" y2="${sk.y(v).toFixed(1)}"/><text class="pz-svg-opis" x="${m.l - 4}" y="${(sk.y(v) + 3).toFixed(1)}" text-anchor="end">${pzKrotkaLiczba(v)}</text>`).join("");
  const osX = pzLadneKroki(xMin, xMax, Math.max(3, Math.floor(W / 90))).map((v) => `<text class="pz-svg-opis" x="${sx(v).toFixed(1)}" y="${H - 6}" text-anchor="middle">${pzLiczba(v, 0)}</text>`).join("");
  const s1 = Math.max(xMin, S * (1 - sT));
  const s2 = Math.min(xMax, S * (1 + sT));
  host.innerHTML = `<svg class="pz-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Wykres wypłaty zakładu ${pzEsc(z.zaklad)}">
    <defs>
      <clipPath id="pz-klip-plus"><rect x="0" y="${yD}" width="${W}" height="${Math.max(0, y0d - yD)}"/></clipPath>
      <clipPath id="pz-klip-minus"><rect x="0" y="${y0d}" width="${W}" height="${Math.max(0, yD + hDol - y0d)}"/></clipPath>
    </defs>
    <rect class="pz-svg-sigma" x="${sx(s1).toFixed(1)}" y="${yG}" width="${(sx(s2) - sx(s1)).toFixed(1)}" height="${yD + hDol - yG}"/>
    ${osY(gora, yG, hGora, 4)}${osY(dol, yD, hDol, 3)}${osX}
    <text class="pz-svg-panel" x="${m.l + 4}" y="${yG + 11}">ETF i całość (USD)</text>
    <text class="pz-svg-panel" x="${m.l + 4}" y="${yD + hDol - 4}">spread (USD)</text>
    <path class="pz-svg-pole-plus" d="${pole}" clip-path="url(#pz-klip-plus)"/>
    <path class="pz-svg-pole-minus" d="${pole}" clip-path="url(#pz-klip-minus)"/>
    <path class="pz-svg-spread" d="${sciezka("spread", dol)}"/>
    <path class="pz-svg-etf" d="${sciezka("etf", gora)}"/>
    <path class="pz-svg-razem" d="${sciezka("razem", gora)}"/>
    ${pion(S, "pz-svg-cena")}${pion(K1, "pz-svg-strike")}${pion(K2, "pz-svg-strike")}${pion(progRent, "pz-svg-prog")}
    <line id="pz-svg-kursor" class="pz-svg-kursor" x1="0" x2="0" y1="${yG}" y2="${yD + hDol}" visibility="hidden"/>
    <rect id="pz-svg-nakladka" x="${m.l}" y="${yG}" width="${W - m.l - m.r}" height="${yD + hDol - yG}" fill="transparent"/>
  </svg><div id="pz-wykres-dymek" class="pz-wykres-dymek" hidden></div>`;

  const nakladka = pzEl("pz-svg-nakladka");
  const kursor = pzEl("pz-svg-kursor");
  const dymek = pzEl("pz-wykres-dymek");
  const svg = host.querySelector("svg");
  nakladka.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const x = xMin + (((e.clientX - r.left) * (W / r.width) - m.l) / (W - m.l - m.r)) * (xMax - xMin);
    const p = policz(Math.min(xMax, Math.max(xMin, x)));
    kursor.setAttribute("x1", sx(p.x));
    kursor.setAttribute("x2", sx(p.x));
    kursor.setAttribute("visibility", "visible");
    dymek.hidden = false;
    dymek.innerHTML = `<b>Indeks ${pzLiczba(p.x, 1)}</b> (${pzZeZnakiem((p.x / S - 1) * 100, 1)}%)<br>ETF: <span class="${pzKlasaZnaku(p.etf)}">${pzZeZnakiem(p.etf, 0)}</span> · spread: <span class="${pzKlasaZnaku(p.spread)}">${pzZeZnakiem(p.spread, 0)}</span><br>razem: <b class="${pzKlasaZnaku(p.razem)}">${pzZeZnakiem(p.razem, 0)} USD</b>`;
    const lewo = ((sx(p.x) / W) * r.width) > r.width / 2;
    dymek.style.left = lewo ? "" : `${(sx(p.x) / W) * r.width + 10}px`;
    dymek.style.right = lewo ? `${r.width - (sx(p.x) / W) * r.width + 10}px` : "";
  });
  nakladka.addEventListener("pointerleave", () => {
    kursor.setAttribute("visibility", "hidden");
    dymek.hidden = true;
  });

  tytul.textContent = `${z.zaklad} · ${pzDataKrotka(z.expiry)}`;
  const tutaj = policz(S);
  legenda.innerHTML = `
    <span><i class="pz-leg pz-leg-razem"></i>ETF + spread</span>
    <span><i class="pz-leg pz-leg-etf"></i>sam ETF${profil.cenaKupna > 0 ? " (od ceny kupna)" : " (od dziś)"}</span>
    <span><i class="pz-leg pz-leg-spread"></i>sam spread</span>
    <span><i class="pz-leg pz-leg-sigma"></i>±1σ: ${pzLiczba(S * (1 - sT), 0)}–${pzLiczba(S * (1 + sT), 0)}</span>
    <dl class="pz-wykres-liczby">
      <div><dt>Sprzedany / kupiony</dt><dd>${pzLiczba(K1, 0)} / ${pzLiczba(K2, 0)}${n > 1 ? ` × ${n}` : ""}</dd></div>
      <div title="Strike sprzedany plus premia jednego kontraktu: do tego poziomu indeksu spread nie traci"><dt>Próg rentowności</dt><dd>${pzLiczba(progRent, 2)}</dd></div>
      <div><dt>Premia / maks. strata</dt><dd>${pzUsd(premiaUsd)} / ${pzUsd(z.maxStrata)}</dd></div>
      <div title="Wynik całej pozycji na wygaśnięciu, gdyby indeks został na dzisiejszym poziomie"><dt>Razem przy indeksie bez zmian</dt><dd class="${pzKlasaZnaku(tutaj.razem)}">${pzZeZnakiem(tutaj.razem, 0)} USD</dd></div>
      <div title="Prawdopodobieństwo, że indeks zamknie się na wygaśnięciu powyżej strike'u sprzedanego"><dt>P przebicia</dt><dd>${pzProcent(z.pSC, 0)}</dd></div>
      <div title="Ile USD zarobi cała pozycja (ETF i ten zakład) na wzroście indeksu o 1 punkt (zadanie 007)"><dt>Delta portfela z zakładem</dt><dd>${pzZeZnakiem(z.deltaUsd, 1)} USD/pkt</dd></div>
    </dl>`;
}

function pzWykresInicjuj() {
  let timer = null;
  let szerokosc = 0;
  const host = pzEl("pz-wykres");
  if (typeof ResizeObserver === "undefined") return;
  new ResizeObserver(() => {
    const s = Math.floor(host.clientWidth);
    if (Math.abs(s - szerokosc) < 8) return;
    szerokosc = s;
    clearTimeout(timer);
    timer = setTimeout(pzRysujWykres, 120);
  }).observe(host);
}

// ===========================================================================
// ELEMENT: okno 5 „Wszystkie zakłady"
// ===========================================================================
// Kolumny: nagłówek, dymek, wartość do wyświetlenia, klucz sortowania, klasa komórki.
const PZ_KOLUMNY = {
  zaklad: { naglowek: "Zakład", dymek: "Strike kupiony / sprzedany; przy kilku kontraktach liczba z przodu (np. 2x 790/788).", pokaz: (z) => pzEsc(z.zaklad), sort: (z) => z.strikeSprzedany, tekst: true },
  typ: { naglowek: "Typ", dymek: "Bezpieczny: para (górny strike progu, środek). Ryzykowny: para (środek, dolny strike progu).", pokaz: (z) => z.typZakladu, sort: (z) => z.typZakladu, tekst: true },
  expiry: { naglowek: "Wygasa", dymek: "Dzień wygaśnięcia opcji.", pokaz: (z) => pzDataKrotka(z.expiry), sort: (z) => z.expiry },
  days: { naglowek: "Dni", dymek: "Dni do wygaśnięcia.", pokaz: (z) => pzLiczba(z.days, 0), sort: (z) => z.days, liczba: true },
  premiaUsd: { naglowek: "Premia", dymek: "Premia netto całej pozycji z cen środkowych (USD).", pokaz: (z) => pzLiczba(z.premia * PZ_MNOZNIK, 0), sort: (z) => z.premia, liczba: true },
  dailyPremia: { naglowek: "Dziennie", dymek: "Premia na dzień do wygaśnięcia (USD).", pokaz: (z) => pzLiczba(z.dailyPremia, 2), sort: (z) => z.dailyPremia, liczba: true },
  maxStrata: { naglowek: "Maks. strata", dymek: "Szerokość spreadu × 100 × kontrakty minus premia (USD).", pokaz: (z) => pzLiczba(z.maxStrata, 0), sort: (z) => z.maxStrata, liczba: true },
  pSC: { naglowek: "P przebicia", dymek: "Prawdopodobieństwo zamknięcia indeksu powyżej strike'u sprzedanego na wygaśnięciu (z dryfem µ).", pokaz: (z) => pzProcent(z.pSC, 0), sort: (z) => z.pSC, liczba: true },
  evOpcji: { naglowek: "EV opcji", dymek: "Premia minus oczekiwany koszt spreadu (USD).", pokaz: (z) => pzLiczba(z.evOpcji, 0), sort: (z) => z.evOpcji, liczba: true, klasa: (z) => pzKlasaZnaku(z.evOpcji) },
  evRyPowyzej: { naglowek: "EV r/r, indeks wyżej", dymek: "Roczna stopa EV całej pozycji w scenariuszu: indeks na wygaśnięciu powyżej strike'u sprzedanego.", pokaz: (z) => pzProcent(z.evRyPowyzej, 1), sort: (z) => z.evRyPowyzej, liczba: true },
  evRyPonizej: { naglowek: "EV r/r, indeks niżej", dymek: "Roczna stopa EV całej pozycji w scenariuszu: indeks na wygaśnięciu poniżej strike'u sprzedanego.", pokaz: (z) => pzProcent(z.evRyPonizej, 1), sort: (z) => z.evRyPonizej, liczba: true },
  evPozycji: { naglowek: "EV pozycji", dymek: "EV opcji plus oczekiwany wynik ETF do wygaśnięcia (USD).", pokaz: (z) => pzLiczba(z.evPozycji, 0), sort: (z) => z.evPozycji, liczba: true, klasa: (z) => pzKlasaZnaku(z.evPozycji) },
  punkty: { naglowek: "Punkty EV", dymek: "Punkty 0-5 z arkusza EV.", pokaz: (z) => (z.punkty == null ? "–" : `${z.punkty}/5`), sort: (z) => z.punkty, liczba: true },
  premiaRynkowaUsd: { naglowek: "Premia od razu", dymek: "Premia po cenach rynkowych: sprzedaż po bid, kupno po ask (USD).", pokaz: (z) => pzLiczba(z.premiaRynkowaUsd, 0), sort: (z) => z.premiaRynkowaUsd, liczba: true, klasa: (z) => pzKlasaZnaku(z.premiaRynkowaUsd) },
  kosztPlynnosciProc: { naglowek: "Koszt płynności", dymek: "Jaką część premii z cen środkowych zjada natychmiastowe wykonanie.", pokaz: (z) => pzProcent(z.kosztPlynnosciProc, 0), sort: (z) => z.kosztPlynnosciProc, liczba: true },
  spreadSprzedanejProc: { naglowek: "Widełki sprzedanej", dymek: "Ask minus bid nogi sprzedanej w % jej ceny środkowej.", pokaz: (z) => pzProcent(z.spreadSprzedanejProc, 0), sort: (z) => z.spreadSprzedanejProc, liczba: true },
  spreadKupionejProc: { naglowek: "Widełki kupionej", dymek: "Ask minus bid nogi kupionej w % jej ceny środkowej.", pokaz: (z) => pzProcent(z.spreadKupionejProc, 0), sort: (z) => z.spreadKupionejProc, liczba: true },
  glebokoscKwotowania: { naglowek: "Kwotowanie mieści", dymek: "Ile kontraktów da się zawrzeć od razu po cenach rynkowych.", pokaz: (z) => pzLiczba(z.glebokoscKwotowania, 0), sort: (z) => z.glebokoscKwotowania, liczba: true },
  oiSprzedanej: { naglowek: "OI sprzedanej", dymek: "Otwarte kontrakty nogi sprzedanej.", pokaz: (z) => pzLiczba(z.oiSprzedanej, 0), sort: (z) => z.oiSprzedanej, liczba: true },
  punktyPlynnosci: { naglowek: "Płynność", dymek: "Punkty płynności 0-5 (zadanie 033).", pokaz: (z) => `${z.punktyPlynnosci}/5`, sort: (z) => z.punktyPlynnosci, liczba: true },
  deltaUsd: { naglowek: "Delta portfela", dymek: "Ile USD zarobi cała pozycja (ETF razem z tym zakładem) na wzroście indeksu o 1 punkt: wartość ETF / indeks + delta spreadu × 100 × kontrakty (zadanie 007).", pokaz: (z) => pzLiczba(z.deltaUsd, 1), sort: (z) => z.deltaUsd, liczba: true },
  ocena: { naglowek: "Ocena", dymek: "Ocena 0–10 (jak w propozycjach). Pogrubione wiersze to kandydaci do propozycji.", pokaz: (z) => `${z.ocena}/10`, sort: (z) => z.ocena, liczba: true },
};
const PZ_ZESTAWY = {
  podstawowe: ["zaklad", "expiry", "days", "premiaUsd", "dailyPremia", "maxStrata", "pSC", "evOpcji", "deltaUsd", "punktyPlynnosci", "ocena"],
  ev: ["zaklad", "typ", "days", "pSC", "evOpcji", "evRyPowyzej", "evRyPonizej", "evPozycji", "punkty", "ocena"],
  plynnosc: ["zaklad", "days", "premiaUsd", "premiaRynkowaUsd", "kosztPlynnosciProc", "spreadSprzedanejProc", "spreadKupionejProc", "glebokoscKwotowania", "oiSprzedanej", "punktyPlynnosci"],
};

function pzFiltrTabeli(z, u) {
  if (u.pokaz === "kandydaci" && !z.kandydat) return false;
  if (u.typ !== "wszystkie" && z.typZakladu !== u.typ) return false;
  if (u.termin === "do30" && z.days > 30) return false;
  if (u.termin === "7-60" && (z.days < 7 || z.days > 60)) return false;
  if (u.termin === "ponad60" && z.days <= 60) return false;
  return true;
}

function pzRysujTabele() {
  const u = pz.ustawienia.tabela;
  for (const [id, klucz] of [["pz-t-zestaw", "zestaw"], ["pz-t-pokaz", "pokaz"], ["pz-t-termin", "termin"], ["pz-t-typ", "typ"]]) pzEl(id).value = u[klucz];
  const tabela = pzEl("pz-tabela");
  const licznik = pzEl("pz-zaklady-licznik");
  const w = pz.wynik;
  if (!w || !w.zaklady || !w.zaklady.length) {
    tabela.innerHTML = `<tbody><tr><td class="pusto">${pzEsc(w?.komunikatZakladow || "Pobieranie danych…")}</td></tr></tbody>`;
    licznik.textContent = "";
    return;
  }
  const kolumny = PZ_ZESTAWY[u.zestaw] || PZ_ZESTAWY.podstawowe;
  const sortKol = PZ_KOLUMNY[u.sortuj] ? u.sortuj : "ocena";
  const def = PZ_KOLUMNY[sortKol];
  const lista = w.zaklady.filter((z) => pzFiltrTabeli(z, u));
  lista.sort((a, b) => {
    const va = def.sort(a);
    const vb = def.sort(b);
    if (va == null || (typeof va === "number" && !Number.isFinite(va))) return 1;
    if (vb == null || (typeof vb === "number" && !Number.isFinite(vb))) return -1;
    const r = def.tekst ? String(va).localeCompare(String(vb), "pl") : va - vb;
    return (u.malejaco ? -r : r) || b.ocena - a.ocena || b.dailyPremia - a.dailyPremia;
  });
  const pokazane = lista.slice(0, PZ_LIMIT_WIERSZY);
  const naglowek = kolumny.map((k) => {
    const d = PZ_KOLUMNY[k];
    const strzalka = k === sortKol ? (u.malejaco ? " ▾" : " ▴") : "";
    return `<th class="${d.liczba ? "t-liczba " : ""}pz-sortowalny${k === sortKol ? " pz-sortowany" : ""}" data-sort="${k}" title="${pzEsc(d.dymek)} Kliknij, żeby sortować.">${pzEsc(d.naglowek)}${strzalka}</th>`;
  }).join("");
  const wiersze = pokazane.map((z) => `<tr data-klucz="${pzEsc(z.klucz)}" class="${z.klucz === pz.wybrany?.klucz ? "pz-wybrany " : ""}${z.kandydat ? "pz-kandydat" : ""}">${kolumny.map((k) => {
    const d = PZ_KOLUMNY[k];
    return `<td class="${d.liczba ? "t-liczba " : ""}${d.klasa ? d.klasa(z) : ""}">${d.pokaz(z)}</td>`;
  }).join("")}</tr>`).join("");
  tabela.innerHTML = `<thead><tr>${naglowek}</tr></thead><tbody>${wiersze || `<tr><td class="pusto" colspan="${kolumny.length}">Żaden zakład nie pasuje do filtrów.</td></tr>`}</tbody>`;
  const poFiltrach = lista.length < w.zaklady.length ? `${lista.length} z ${w.zaklady.length} zakładów` : `${lista.length} zakładów`;
  licznik.textContent = pokazane.length < lista.length ? `${poFiltrach}, pokazane pierwsze ${pokazane.length}` : poFiltrach;
}

function pzZakladyInicjuj() {
  const zmien = (klucz, wartosc) => {
    pz.ustawienia.tabela[klucz] = wartosc;
    pzZaplanujZapis(`tabela zakładów: ${klucz}`);
    pzRysujTabele();
  };
  pzEl("pz-t-zestaw").addEventListener("change", (e) => zmien("zestaw", e.target.value));
  pzEl("pz-t-pokaz").addEventListener("change", (e) => zmien("pokaz", e.target.value));
  pzEl("pz-t-termin").addEventListener("change", (e) => zmien("termin", e.target.value));
  pzEl("pz-t-typ").addEventListener("change", (e) => zmien("typ", e.target.value));
  pzEl("pz-tabela").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]");
    if (th) {
      const t = pz.ustawienia.tabela;
      if (t.sortuj === th.dataset.sort) t.malejaco = !t.malejaco;
      else {
        t.sortuj = th.dataset.sort;
        t.malejaco = !PZ_KOLUMNY[th.dataset.sort].tekst;
      }
      pzZaplanujZapis(`tabela zakładów: sortowanie ${t.sortuj}`);
      pzRysujTabele();
      return;
    }
    const tr = e.target.closest("tr[data-klucz]");
    if (tr) pzWybierzZaklad(tr.dataset.klucz);
  });
}

// ===========================================================================
// ELEMENT: okno 6 „Otwarte pozycje"
// ===========================================================================
function pzRysujOtwarte() {
  const host = pzEl("pz-otwarte");
  const w = pz.wynik;
  if (pz.historiaStan) {
    host.innerHTML = `<div class="pz-pusto">${pzEsc(pz.historiaStan)}</div>`;
    return;
  }
  const otwarte = w?.otwarte || [];
  const czesci = [];
  if (!otwarte.length) czesci.push(`<div class="pz-pusto">Brak otwartych zakładów. Zakład zapiszesz przyciskiem „Zapisz jako otwarty" w propozycjach.</div>`);
  else {
    const zWynikiem = otwarte.filter((o) => o.wynikTeraz != null);
    const suma = zWynikiem.reduce((a, o) => a + o.wynikTeraz, 0);
    czesci.push(`<div class="pz-otwarte-suma">Otwarte: <b>${otwarte.length}</b>${zWynikiem.length ? ` · wynik teraz: <b class="${pzKlasaZnaku(suma)}">${pzZeZnakiem(suma, 0)} USD</b>` : ""}</div>`);
    for (const o of otwarte) {
      const r = o.wiersz;
      const tytul = `${o.n > 1 ? `${o.n}x ` : ""}${pzEsc(r.strike_dlugi)}/${pzEsc(r.strike_krotki)}`;
      const termin = r.expiry ? `${pzEsc(r.symbol || "")} · ${pzEsc(r.expiry.slice(8, 10))}.${pzEsc(r.expiry.slice(5, 7))}${o.dni != null ? ` (${o.dni} dni)` : ""}` : "brak symbolu i daty (zakład ze starej karty)";
      const liczby = o.wycena != null
        ? `premia ${pzUsd(o.premia)} · odkupienie teraz ${pzUsd(o.wycena)} · delta ${pzLiczba(o.delta, 3)} · theta ${pzZeZnakiem(o.theta, 1)} USD/dzień`
        : `premia ${pzUsd(o.premia)} · ${o.tenProfil || !r.symbol ? "brak wyceny w bieżącym łańcuchu" : `wycena w profilu ${pzEsc(r.symbol)}`}`;
      czesci.push(`<div class="pz-otwarta" data-id="${pzEsc(r.id)}">
        <div class="pz-otwarta-gora"><b>${tytul}</b><small>${termin}</small>${o.wynikTeraz != null ? `<span class="${pzKlasaZnaku(o.wynikTeraz)}" title="Premia minus koszt odkupienia spreadu po cenach środkowych">${pzZeZnakiem(o.wynikTeraz, 0)} USD</span>` : ""}</div>
        <div class="pz-otwarta-liczby">${liczby}</div>
        <div class="pz-zamknij"><input type="date" value="${pzDzisiajIso()}" aria-label="Data zamknięcia" /><input type="number" step="0.01" placeholder="wynik USD" value="${o.wynikTeraz != null ? Math.round(o.wynikTeraz * 100) / 100 : ""}" aria-label="Wynik w USD" /><button type="button" class="t-mini" data-akcja="zamknij" title="Zapisz zamknięcie w historii zakładów">Zamknij</button></div>
      </div>`);
    }
  }
  if (pz.zamkniete.length) {
    czesci.push(`<h3>Ostatnio zamknięte</h3><ul class="pz-zamkniete">${pz.zamkniete.map((r) => {
      const wynik = Number(r.wynik_dolary);
      return `<li><span>${Number(r.kontrakty) > 1 ? `${pzEsc(r.kontrakty)}x ` : ""}${pzEsc(r.strike_dlugi)}/${pzEsc(r.strike_krotki)}</span><small>${pzEsc(r.data_zamkniecia)}</small><b class="${pzKlasaZnaku(wynik)}">${pzZeZnakiem(wynik, 0)} USD</b></li>`;
    }).join("")}</ul>`);
  }
  host.innerHTML = czesci.join("");
}

function pzOtwarteInicjuj() {
  pzEl("pz-otwarte-odswiez").addEventListener("click", async () => {
    await pzWczytajHistorie();
    pzPrzelicz();
  });
  pzEl("pz-otwarte").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-akcja='zamknij']");
    if (!b) return;
    const wiersz = b.closest(".pz-otwarta");
    const [data, wynik] = wiersz.querySelectorAll("input");
    if (!data.value || wynik.value === "") {
      alert("Podaj datę zamknięcia i wynik w USD.");
      return;
    }
    pzZamknijZaklad(wiersz.dataset.id, data.value, Number(wynik.value), b);
  });
}

// ===========================================================================
// ELEMENT: przestrzeń robocza (okna z zakładkami, wspólny moduł web/shared/przestrzen.js)
// ===========================================================================
const PZ_KOLEJNOSC = ["pozycja", "wskazniki", "propozycje", "wykres", "zaklady", "otwarte"];
const PZ_ELEMENTY = {
  pozycja: { nazwa: "Pozycja", opis: "Profile pozycji, parametry, token i stan danych", szer: 4, wys: 310, wezel: ".pz-okno-pozycja" },
  wskazniki: { nazwa: "Wskaźniki rynku opcji", opis: "Barometr i dziesięć wskaźników dla call spreadu", szer: 8, wys: 310, wezel: ".pz-okno-wskazniki" },
  propozycje: { nazwa: "Propozycje zakładów", opis: "Trzy najlepiej ocenione zakłady z generatora", szer: 7, wys: 430, wezel: ".pz-okno-propozycje" },
  wykres: { nazwa: "Wykres wypłaty", opis: "Wynik wybranego zakładu na dzień wygaśnięcia", szer: 5, wys: 430, wezel: ".pz-okno-wykres" },
  zaklady: { nazwa: "Wszystkie zakłady", opis: "Tabela zakładów z filtrami i zestawami kolumn", szer: 8, wys: 650, wezel: ".pz-okno-zaklady" },
  otwarte: { nazwa: "Otwarte pozycje", opis: "Otwarte spready z historii zakładów i ich wycena", szer: 4, wys: 650, wezel: ".pz-okno-otwarte" },
};
const PZ_UKLAD_DOMYSLNY = [["pozycja", 4, 310], ["wskazniki", 8, 310], ["propozycje", 7, 430], ["wykres", 5, 430], ["zaklady", 8, 650], ["otwarte", 4, 650]];
let pzPrzestrzen = null;

function pzPrzestrzenInicjuj() {
  const korzen = document.getElementById("pz-przestrzen");
  // Bez modułu (np. nie wczytał się plik) pokazujemy okna jedno pod drugim, żeby karta działała.
  if (typeof PRZESTRZEN === "undefined") { korzen.querySelector(".prz-magazyn").hidden = false; return; }
  pzPrzestrzen = PRZESTRZEN.utworz({
    korzen,
    elementy: PZ_ELEMENTY,
    kolejnosc: PZ_KOLEJNOSC,
    ukladDomyslny: PZ_UKLAD_DOMYSLNY,
    start: "domyslny",
    klucz: "pozycja-przestrzen",
    cache: "pz_przestrzen_cache",   // tylko podręczna kopia; zapis główny w repozytorium
    opisZapisu: "układ okien karty Pozycja",
    napisy: {
      dodajTytul: "Dodaj okno z jednym z sześciu elementów karty",
      domyslnyTytul: "Ustaw sześć okien karty w układzie domyślnym",
      potwierdzDomyslny: "Zastąpić obecne okna układem domyślnym (sześć okien)?",
    },
  });
  pzPrzestrzen.przywroc();
}

if (typeof document !== "undefined" && document.getElementById("pz-przestrzen")) pzPrzestrzenInicjuj();

// ===========================================================================
// START: profile -> historia zakładów -> dane rynkowe; okna wiążą zdarzenia raz.
// ===========================================================================
async function pzStart() {
  pzPozycjaInicjuj();
  pzPropozycjeInicjuj();
  pzWykresInicjuj();
  pzZakladyInicjuj();
  pzOtwarteInicjuj();
  await pzWczytajUstawienia();
  pzPrzelicz();
  await Promise.all([pzWczytajHistorie(), pzOdswiez(true)]);
  pzPrzelicz();
}

if (typeof document !== "undefined" && document.getElementById("pz-profile")) pzStart();
