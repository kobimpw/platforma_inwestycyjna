// Testy adaptera próbek (web/shared/probka.js): ten sam kod, który w przeglądarce odpowiada kartom VaR i Pozycja,
// uruchomiony na prawdziwych plikach z data/przyklad/ i z podstawionym pobieraniem plików.
// Uruchomienie: node --test "tests/js/*.test.mjs"  (wchodzi w `make test`)
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const KORZEN = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const KATALOG_PROBEK = path.join(KORZEN, "data", "przyklad");
const ADRES = "http://test.invalid/data/przyklad/";

// Skrypt przeglądarkowy ładujemy w odizolowanym kontekście; bez `window` i `document` eksportuje funkcje przez `module`.
const modul = { exports: {} };
vm.runInNewContext(readFileSync(path.join(KORZEN, "web", "shared", "probka.js"), "utf8"), { module: modul, URL }, { filename: "probka.js" });
const { utworzProbke, przytnijNotowania, rozbierzZakres, dzienProbki } = modul.exports;

// Obiekty z kontekstu vm mają inne prototypy niż w tym pliku, więc porównujemy je przez zapis JSON.
const kopia = (x) => JSON.parse(JSON.stringify(x));

function pobierzZDysku(adres) {
  const plik = path.join(KATALOG_PROBEK, adres.slice(ADRES.length));
  if (!existsSync(plik)) return Promise.resolve({ ok: false, status: 404, text: async () => "" });
  return Promise.resolve({ ok: true, status: 200, text: async () => readFileSync(plik, "utf8") });
}
const probka = () => utworzProbke({ katalog: ADRES, pobierz: pobierzZDysku });
const surowe = (plik) => JSON.parse(readFileSync(path.join(KATALOG_PROBEK, plik), "utf8"));

test("zakres w stylu Yahoo: sesje, kalendarz, ytd, max i błędy", () => {
  assert.equal(kopia(rozbierzZakres("")).punkty, 1);
  assert.equal(kopia(rozbierzZakres(null)).punkty, 1);
  assert.equal(kopia(rozbierzZakres("5d")).punkty, 5);
  assert.equal(kopia(rozbierzZakres("2wk")).dni, 14);
  assert.equal(kopia(rozbierzZakres("3mo")).dni, 91);
  assert.equal(kopia(rozbierzZakres("1y")).dni, 365);
  assert.equal(kopia(rozbierzZakres("MAX")).wszystko, true);
  assert.equal(kopia(rozbierzZakres("ytd")).odPoczatkuRoku, true);
  assert.throws(() => rozbierzZakres("100x"), /nieobsługiwany zakres/);
  assert.throws(() => rozbierzZakres("0y"), /nieobsługiwany zakres/);
});

test("notowania bez zakresu to ostatnia sesja z zamknięciem poprzedniej sesji", async () => {
  const pelne = surowe("quote-SPY.json").chart.result[0];
  const zamkniecia = pelne.indicators.quote[0].close;
  const d = kopia(await probka().json("/quote?ticker=SPY"));
  const r = d.chart.result[0];
  assert.equal(r.timestamp.length, 1);
  assert.equal(r.timestamp[0], pelne.timestamp.at(-1));
  assert.equal(r.indicators.quote[0].close[0], zamkniecia.at(-1));
  assert.equal(r.meta.chartPreviousClose, zamkniecia.at(-2));
  assert.equal(r.meta.regularMarketPrice, pelne.meta.regularMarketPrice);
  assert.equal(d.chart.error, null);
});

test("zakres 1y: około roku sesji, zamknięcie sprzed zakresu i równe tablice", async () => {
  const pelne = surowe("quote-SPY.json").chart.result[0];
  const d = kopia(await probka().json("/quote?ticker=spy&range=1y&interval=1d")); // wielkość liter nie ma znaczenia
  const r = d.chart.result[0];
  const koniec = pelne.timestamp.at(-1);
  assert.ok(r.timestamp.length >= 245 && r.timestamp.length <= 260, `punktów: ${r.timestamp.length}`);
  assert.ok(r.timestamp[0] >= koniec - 366 * 86400);
  for (const k of ["open", "high", "low", "close"]) assert.equal(r.indicators.quote[0][k].length, r.timestamp.length, k);
  const poczatek = pelne.timestamp.length - r.timestamp.length;
  assert.equal(r.meta.chartPreviousClose, pelne.indicators.quote[0].close[poczatek - 1]);
});

test("zakres 100y i max zwracają całą próbkę z zapisanym zamknięciem sprzed zakresu", async () => {
  const pelne = surowe("quote-_GSPC.json").chart.result[0];
  for (const zakres of ["100y", "max"]) {
    const r = kopia(await probka().json(`/quote?ticker=${encodeURIComponent("^GSPC")}&range=${zakres}&interval=1d`)).chart.result[0];
    assert.equal(r.timestamp.length, pelne.timestamp.length, zakres);
    assert.equal(r.meta.chartPreviousClose, pelne.meta.chartPreviousClose, zakres);
  }
});

test("indeks z jedną sesją (XND) działa bez wyjątku i zachowuje zapisane zamknięcie poprzedniej sesji", async () => {
  const pelne = surowe("quote-_XND.json").chart.result[0];
  const r = kopia(await probka().json(`/quote?ticker=${encodeURIComponent("^XND")}`)).chart.result[0];
  assert.equal(r.timestamp.length, 1);
  assert.equal(r.meta.chartPreviousClose, pelne.meta.chartPreviousClose);
});

test("brakujące zamknięcia (null) nie psują zamknięcia sprzed zakresu", () => {
  const d = {
    chart: { result: [{ meta: { chartPreviousClose: 1 }, timestamp: [100, 200, 300, 400], indicators: { quote: [{ close: [10, null, 30, null], open: [10, null, 30, null] }] } }] },
  };
  const r = kopia(przytnijNotowania(d, "1d")).chart.result[0]; // zakres 1 sesji: zostaje tylko ostatnia
  assert.deepEqual(r.timestamp, [400]);
  assert.equal(r.meta.chartPreviousClose, 30); // pomija null i bierze najbliższe zamknięcie wcześniej
  assert.equal(d.chart.result[0].timestamp.length, 4, "oryginał nie jest zmieniany");
});

test("nieznany ticker i symbol: czytelny błąd z listą dostępnych próbek", async () => {
  const p = probka();
  await assert.rejects(() => p.json("/quote?ticker=AAPL"), /Brak próbki notowań dla „AAPL”.*SPY/);
  await assert.rejects(() => p.json("/options?symbol=_SPX"), /Brak próbki łańcucha opcji „_SPX”.*_XSP/);
  await assert.rejects(() => p.json("/inna?x=1"), /trasa \/inna nie jest obsługiwana/);
});

test("łańcuch opcji ma kształt odpowiedzi Cboe, a dzień próbki to data jego migawki", async () => {
  const p = probka();
  assert.equal(p.dzisiajUTC(), null, "przed wczytaniem spisu dnia próbki jeszcze nie znamy");
  const d = kopia(await p.json("/options?symbol=_XSP"));
  assert.ok(d.data.options.length > 1000);
  assert.ok(d.data.current_price > 0);
  assert.match(d.timestamp, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  const o = d.data.options[0];
  assert.match(o.option, /^[A-Z]+\d{6}[CP]\d{8}$/);
  for (const pole of ["bid", "ask", "iv", "delta", "theta", "open_interest"]) assert.ok(pole in o, pole);
  const spis = await p.indeks();
  const najwczesniejsza = Math.min(...Object.values(spis.lancuchy).map((l) => Date.parse(`${l.timestamp.slice(0, 10)}T00:00:00Z`)));
  assert.equal(p.dzisiajUTC(), najwczesniejsza);
  assert.equal(dzienProbki({ lancuchy: {}, pobrano: "2026-11-11T13:47:47Z" }), Date.UTC(2026, 10, 11));
});

test("błąd pobrania nie zostaje w pamięci podręcznej", async () => {
  let dziala = false;
  const p = utworzProbke({
    katalog: ADRES,
    pobierz: (adres) => (dziala ? pobierzZDysku(adres) : Promise.resolve({ ok: false, status: 503, text: async () => "" })),
  });
  await assert.rejects(() => p.json("/quote?ticker=SPY"), /HTTP 503/);
  dziala = true;
  const d = kopia(await p.json("/quote?ticker=SPY"));
  assert.equal(d.chart.result[0].meta.symbol, "SPY");
});

test("każda próbka ze spisu daje się odczytać przez adapter", async () => {
  const p = probka();
  const spis = await p.indeks();
  for (const ticker of Object.keys(spis.notowania)) {
    const d = kopia(await p.json(`/quote?ticker=${encodeURIComponent(ticker)}&range=max&interval=1d`));
    assert.ok(d.chart.result[0].timestamp.length >= 1, ticker);
  }
  for (const symbol of Object.keys(spis.lancuchy)) {
    const d = kopia(await p.json(`/options?symbol=${encodeURIComponent(symbol)}`));
    assert.ok(d.data.options.length > 0, symbol);
  }
});
