"use strict";

/**
 * Wspólny silnik filtrów (lista krotek) i sortowania dla stron w docs/ —
 * odpowiednik funkcji przygotuj/zastosuj_filtry/posortuj, które ma wcielone
 * bezpośrednio każdy plik .py w docs/, który ich potrzebuje (dawniej
 * wspólny backend/tabela_utils.py — usunięty, patrz historia gita).
 * Ładowany jako zwykły <script> przed app.js danej strony.
 */

const OPERATORY = {
  "<": (a, b) => a < b,
  "<=": (a, b) => a <= b,
  ">": (a, b) => a > b,
  ">=": (a, b) => a >= b,
  "==": (a, b) => a === b,
  "!=": (a, b) => a !== b,
  in: (a, b) => b.includes(a),
  notin: (a, b) => !b.includes(a),
  between: (a, b) => a >= b[0] && a <= b[1],
  contains: (a, b) => String(a ?? "").toLowerCase().includes(String(b).toLowerCase()),
};

function zastosujFiltry(wiersze, filtry) {
  let wynik = wiersze;
  for (const [kolumna, operator, wartosc] of filtry || []) {
    const fn = OPERATORY[operator];
    if (!fn) throw new Error(`Nieznany operator filtra: ${operator}`);
    wynik = wynik.filter((w) => fn(w[kolumna], wartosc));
  }
  return wynik;
}

function posortuj(wiersze, po, malejaco) {
  if (!po) return wiersze;
  const kierunek = malejaco ? -1 : 1;
  return [...wiersze].sort((a, b) => {
    if (a[po] < b[po]) return -1 * kierunek;
    if (a[po] > b[po]) return 1 * kierunek;
    return 0;
  });
}

function przygotuj(wiersze, { filtry, sortujPo, malejaco = true, limit } = {}) {
  let wynik = zastosujFiltry(wiersze, filtry);
  wynik = posortuj(wynik, sortujPo, malejaco);
  if (limit != null) wynik = wynik.slice(0, limit);
  return wynik;
}
