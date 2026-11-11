"use strict";

/**
 * Próbki danych rynkowych dla kart VaR i Pozycja w wersji poglądowej.
 *
 * W pełnej platformie obie karty pytają własny serwer pośredniczący (Cloudflare Worker) o dwie trasy:
 *   /quote?ticker=<TICKER>&range=<ZAKRES>&interval=1d   odpowiedź wykresu Yahoo Finance,
 *   /options?symbol=<SYMBOL>                            łańcuch opcji Cboe.
 * Wersja poglądowa takiego serwera nie ma: Yahoo i Cboe nie dopuszczają zapytań wprost z przeglądarki w obcej domenie
 * (ich odpowiedzi nie mają nagłówków CORS). Ten moduł odpowiada więc na te same ścieżki zapisanymi próbkami z katalogu
 * data/przyklad/ (powstają poleceniem `make probki`, czyli src/narzedzia/pobierz_probki.py) i oddaje je w tym samym
 * kształcie co źródła. Karty zmieniają się przez to minimalnie: zamiast `fetch(WORKER + ścieżka)` wołają
 * `PROBKA.json(ścieżka)`.
 *
 *   await PROBKA.json("/quote?ticker=SPY&range=1y&interval=1d")   jak Yahoo, przycięte do zakresu
 *   await PROBKA.json("/options?symbol=_XSP")                     jak Cboe (łańcuch przycięty przy zapisie)
 *   await PROBKA.indeks()                                         spis próbek (data/przyklad/indeks.json)
 *   PROBKA.dzisiajUTC()                                           dzień próbki w ms (północ UTC) albo null, dopóki
 *                                                                 spis się nie wczyta
 *
 * Próbka jest zamrożona w czasie: karty liczą dni do wygaśnięcia opcji od dnia próbki, a nie od dzisiaj, więc pokaz nie
 * psuje się, gdy terminy z próbki mijają. Informacja o tym trafia na pasek „Wersja poglądowa" w rogu strony.
 */
(function () {
  const DZIEN_S = 86400;
  // Baza potrzebna tylko do rozbioru ścieżki `/quote?ticker=...` na części; nic się pod nią nie pobiera.
  const BAZA_SCIEZKI = "http://probka.invalid";

  function dzienZIso(napis) {
    return /^\d{4}-\d{2}-\d{2}/.test(napis) ? Date.parse(napis.slice(0, 10) + "T00:00:00Z") : null;
  }

  // Dzień próbki: data najwcześniejszej migawki łańcucha opcji (od niej liczy się czas do wygaśnięcia); gdyby spis nie
  // miał łańcuchów, dzień pobrania.
  function dzienProbki(spis) {
    const dni = Object.values(spis.lancuchy || {})
      .map((l) => dzienZIso(String(l.timestamp || "")))
      .filter((d) => d != null);
    if (dni.length) return Math.min(...dni);
    return dzienZIso(String(spis.pobrano || ""));
  }

  // Zakres w stylu Yahoo: 5d (sesje), 2wk, 3mo, 1y, ytd, max. Brak zakresu to ostatnia sesja, jak domyślna odpowiedź Yahoo.
  function rozbierzZakres(zakres) {
    const z = String(zakres == null ? "" : zakres).trim().toLowerCase();
    if (z === "") return { punkty: 1 };
    if (z === "max") return { wszystko: true };
    if (z === "ytd") return { odPoczatkuRoku: true };
    const m = /^(\d+)(d|wk|mo|y)$/.exec(z);
    if (!m || Number(m[1]) <= 0) {
      throw new Error(`Próbka: nieobsługiwany zakres „${zakres}” (obsługiwane np. 1d, 5d, 3mo, 1y, 5y, ytd, max)`);
    }
    const n = Number(m[1]);
    if (m[2] === "d") return { punkty: n };
    if (m[2] === "wk") return { dni: 7 * n };
    if (m[2] === "mo") return { dni: Math.round(30.4375 * n) };
    return { dni: Math.round(365.25 * n) };
  }

  function poczatekZakresu(znaczniki, zakres) {
    const n = znaczniki.length;
    const r = rozbierzZakres(zakres);
    if (r.wszystko) return 0;
    if (r.punkty != null) return Math.max(0, n - r.punkty);
    const ostatni = znaczniki[n - 1];
    const granica = r.odPoczatkuRoku ? Date.UTC(new Date(ostatni * 1000).getUTCFullYear(), 0, 1) / 1000 : ostatni - r.dni * DZIEN_S;
    const i = znaczniki.findIndex((t) => t >= granica);
    return i < 0 ? n - 1 : i;
  }

  // Odpowiedź Yahoo przycięta do zakresu. Jak u Yahoo, `meta.chartPreviousClose` to zamknięcie sprzed początku zakresu
  // (zapis z całych 10 lat ma tam zamknięcie sprzed dekady, więc po przycięciu trzeba je przeliczyć).
  function przytnijNotowania(surowe, zakres) {
    const wynik = surowe && surowe.chart && surowe.chart.result && surowe.chart.result[0];
    if (!wynik || !Array.isArray(wynik.timestamp) || wynik.timestamp.length === 0) {
      throw new Error("Próbka notowań ma nieoczekiwany kształt (brak listy timestamp)");
    }
    const od = poczatekZakresu(wynik.timestamp, zakres);
    const swiece = (wynik.indicators && wynik.indicators.quote && wynik.indicators.quote[0]) || {};
    const przyciete = {};
    for (const [klucz, wartosci] of Object.entries(swiece)) {
      przyciete[klucz] = Array.isArray(wartosci) ? wartosci.slice(od) : wartosci;
    }
    const meta = { ...wynik.meta };
    if (od > 0 && Array.isArray(swiece.close)) {
      for (let i = od - 1; i >= 0; i--) {
        if (typeof swiece.close[i] === "number") {
          meta.chartPreviousClose = swiece.close[i];
          break;
        }
      }
    }
    return { chart: { result: [{ meta, timestamp: wynik.timestamp.slice(od), indicators: { quote: [przyciete] } }], error: null } };
  }

  // Klucz ze słownika spisu: dokładny albo bez rozróżniania wielkości liter („spy" -> „SPY").
  function znajdzKlucz(slownik, wpisane) {
    const klucze = Object.keys(slownik || {});
    const szukane = String(wpisane == null ? "" : wpisane).trim();
    return klucze.find((k) => k === szukane) || klucze.find((k) => k.toUpperCase() === szukane.toUpperCase()) || null;
  }

  // Fabryka z wstrzykniętym pobieraniem plików, żeby moduł dało się sprawdzić testem bez przeglądarki.
  function utworzProbke({ katalog, pobierz }) {
    const teksty = new Map(); // plik -> obietnica z tekstem (błąd nie zostaje w pamięci podręcznej)
    let spis = null;
    let obietnicaSpisu = null;

    function tekst(plik) {
      if (!teksty.has(plik)) {
        const obietnica = Promise.resolve(pobierz(katalog + plik)).then((odp) => {
          if (!odp.ok) throw new Error(`Nie udało się wczytać próbki ${plik} (HTTP ${odp.status})`);
          return odp.text();
        });
        obietnica.catch(() => teksty.delete(plik));
        teksty.set(plik, obietnica);
      }
      return teksty.get(plik);
    }

    function indeks() {
      if (!obietnicaSpisu) {
        obietnicaSpisu = tekst("indeks.json").then((t) => {
          spis = JSON.parse(t);
          return spis;
        });
        obietnicaSpisu.catch(() => {
          obietnicaSpisu = null;
        });
      }
      return obietnicaSpisu;
    }

    async function json(sciezka) {
      const adres = new URL(sciezka, BAZA_SCIEZKI);
      const lista = await indeks();
      if (adres.pathname === "/quote") {
        const ticker = adres.searchParams.get("ticker") || "";
        const klucz = znajdzKlucz(lista.notowania, ticker);
        if (!klucz) {
          throw new Error(`Brak próbki notowań dla „${ticker}”. W wersji poglądowej są tylko: ${Object.keys(lista.notowania).join(", ")}.`);
        }
        const surowe = JSON.parse(await tekst(lista.notowania[klucz].plik));
        return przytnijNotowania(surowe, adres.searchParams.get("range"));
      }
      if (adres.pathname === "/options") {
        const symbol = adres.searchParams.get("symbol") || "";
        const klucz = znajdzKlucz(lista.lancuchy, symbol);
        if (!klucz) {
          throw new Error(`Brak próbki łańcucha opcji „${symbol}”. W wersji poglądowej są tylko: ${Object.keys(lista.lancuchy).join(", ")}.`);
        }
        return JSON.parse(await tekst(lista.lancuchy[klucz].plik));
      }
      throw new Error(`Próbka: trasa ${adres.pathname} nie jest obsługiwana (są /quote i /options)`);
    }

    return { json, indeks, dzisiajUTC: () => (spis ? dzienProbki(spis) : null) };
  }

  // Zdanie na pasek „Wersja poglądowa": skąd są dane rynkowe na kartach VaR i Pozycja.
  function dopiszDoPaska(spis) {
    const pasek = document.querySelector(".baner-pogladowy");
    const dzien = dzienProbki(spis);
    if (!pasek || dzien == null || pasek.querySelector(".baner-probki")) return;
    const iso = new Date(dzien).toISOString().slice(0, 10);
    const dataPl = `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
    const wiersz = document.createElement("span");
    wiersz.className = "baner-probki";
    wiersz.textContent = `dane rynkowe: zapisana próbka z ${dataPl}`;
    pasek.appendChild(wiersz);
    pasek.dataset.dymek += ` Notowania (Yahoo Finance) i łańcuch opcji (Cboe) na kartach VaR i Pozycja to zapisana próbka z ${dataPl}, a nie dane na żywo; terminy opcji liczą się od tego dnia.`;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { utworzProbke, przytnijNotowania, rozbierzZakres, dzienProbki };
  }

  if (typeof window !== "undefined" && typeof document !== "undefined") {
    // Katalog próbek leży obok katalogu shared/ (../data/przyklad/ względem tego pliku), także pod podścieżką GitHub Pages.
    const skrypt = document.currentScript && document.currentScript.src;
    const katalog = new URL("../data/przyklad/", skrypt || document.baseURI).href;
    window.PROBKA = utworzProbke({ katalog, pobierz: (adres) => fetch(adres) });
    const start = () => window.PROBKA.indeks().then(dopiszDoPaska).catch(() => {});
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
  }
})();
