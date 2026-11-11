"use strict";

/**
 * Okna przesuwane i zmieniane rozmiarem na wszystkich kartach (zadanie 017,
 * specyfikacja: projekty/017-*\/pliki/specyfikacja-przesuwanie-okien.md).
 *
 * Co robi (tylko na szerokim ekranie, od 901 px; na węższym okna i tak układają
 * się jedno pod drugim):
 *  1. Zmiana szerokości: na prawej krawędzi okna, które ma sąsiada z prawej,
 *     pojawia się cienki uchwyt. Przeciągnięcie przesuwa całą linię podziału
 *     (wszystkie okna, które ją współtworzą), więc w siatce 12 kolumn nie
 *     powstają dziury. Szerokość zmienia się o całe kolumny.
 *  2. Zmiana wysokości: uchwyt na dolnej krawędzi okna zmienia wysokość całego
 *     rzędu siatki (w pikselach).
 *  3. Zamiana miejscami: przeciągnięcie okna za jego nagłówek na inne okno
 *     wymienia ich prostokąty (położenie i rozmiar). Numeracja okien
 *     (oznaczenia.js) idzie za kolejnością w HTML, a ta się nie zmienia —
 *     „okno 3" to zawsze to samo okno.
 *  4. Zapis: układ ląduje w repozytorium (`ustawienia/uklad-<karta>.json`, przez
 *     USTAW z ustawienia.js, tym samym tokenem GitHub co „Projekty i uwagi"),
 *     a w `localStorage` leży tylko podręczna kopia, żeby strona od razu
 *     pokazała się w Twoim układzie. Bez tokenu układ działa do zamknięcia
 *     karty i jest pamiętany w tej przeglądarce.
 *  5. W pasku bocznym jest sekcja „Układ okien" z przyciskiem „Przywróć układ".
 *
 * Model: każde okno ma prostokąt { c: kolumna startowa 1..12, w: liczba kolumn,
 * r: wiersz startowy, h: liczba wierszy }. Ustawiamy go inline jako
 * `grid-column` / `grid-row`, a wysokości wierszy jako `grid-template-rows`.
 * Domyślne prostokąty odczytujemy z tego, jak przeglądarka sama ułożyła siatkę.
 */
(function () {
const KOLUMN = 12;
const MIN_KOL = 2;
const MIN_WYS = 70;
const PROG_PX = 900;
const OPOZNIENIE_ZAPISU = 800;

const mq = window.matchMedia(`(min-width: ${PROG_PX + 1}px)`);
const SKRYPT = document.currentScript ? document.currentScript.src : "";

let siatki = [];
let karta = "";
let kluczUkladu = "";
let przygotowane = false;
let zapisTimer = null;
let stanZapisu = { tekst: "", blad: false };
let elStanu = null;

// ---------- pomocnicze ----------

function nazwaKarty() {
  const root = new URL(window.SIDEBAR_ROOT || "./", window.location.href).pathname;
  const sciezka = window.location.pathname.replace(/index\.html$/, "");
  const wzgledna = sciezka.startsWith(root) ? sciezka.slice(root.length) : sciezka;
  return wzgledna.replace(/\/+$/, "").replace(/\//g, "-") || "zajecie-pozycji";
}

function kopia(o) {
  return JSON.parse(JSON.stringify(o));
}

function ograniczenie(x, min, max) {
  return Math.max(min, Math.min(max, x));
}

// Indeks ścieżki siatki, której początek (po odjęciu odstępów) jest najbliższy `poz`.
function najblizszyTor(poz, tory, odstep) {
  let start = 0;
  let najlepszy = 0;
  let odl = Infinity;
  for (let i = 0; i < tory.length; i++) {
    const d = Math.abs(poz - start);
    if (d < odl) {
      odl = d;
      najlepszy = i;
    }
    start += tory[i] + odstep;
  }
  return najlepszy;
}

function doLiczb(tekst) {
  return tekst.split(/\s+/).map(parseFloat).filter((x) => !isNaN(x));
}

// ---------- model ----------

function zbierzSiatki() {
  const wynik = [];
  document.querySelectorAll("main .t-siatka").forEach((el, gi) => {
    const okna = Array.from(el.children)
      .filter((d) => d.classList.contains("t-okno") && !d.hidden)
      .map((d, oi) => ({ el: d, id: d.dataset.okno || `o${oi}`, domyslny: null, uklad: null }));
    if (okna.length) wynik.push({ el, klucz: `s${gi}`, okna, rzedy: null, wlasny: false });
  });
  return wynik;
}

// Odczytuje prostokąty okien z tego, jak przeglądarka ułożyła siatkę (musi być
// widok szeroki — na wąskim siatka ma jedną kolumnę).
function zmierzDomyslne(s) {
  const cs = getComputedStyle(s.el);
  const kol = doLiczb(cs.gridTemplateColumns);
  const wie = doLiczb(cs.gridTemplateRows);
  const odstK = parseFloat(cs.columnGap) || 0;
  const odstW = parseFloat(cs.rowGap) || 0;
  const r0 = s.el.getBoundingClientRect();
  const lewo = r0.left + s.el.clientLeft;
  const gora = r0.top + s.el.clientTop;
  for (const o of s.okna) {
    const r = o.el.getBoundingClientRect();
    const c = najblizszyTor(r.left - lewo, kol, odstK);
    const prawy = najblizszyTor(r.right - lewo + odstK, kol.concat([0]), odstK);
    const rr = najblizszyTor(r.top - gora, wie, odstW);
    const dol = najblizszyTor(r.bottom - gora + odstW, wie.concat([0]), odstW);
    o.domyslny = { c: c + 1, w: Math.max(1, prawy - c), r: rr + 1, h: Math.max(1, dol - rr) };
    o.uklad = null;
  }
  s.rzedy = null;
}

function poprawny(s, ukl) {
  const zajete = new Set();
  for (const o of s.okna) {
    const p = ukl[o.id];
    if (!p || p.c < 1 || p.w < 1 || p.c + p.w > KOLUMN + 1 || p.r < 1 || p.h < 1) return false;
    for (let x = p.c; x < p.c + p.w; x++) {
      for (let y = p.r; y < p.r + p.h; y++) {
        const k = x + ":" + y;
        if (zajete.has(k)) return false;
        zajete.add(k);
      }
    }
  }
  return true;
}

function biezacy(s) {
  const u = {};
  for (const o of s.okna) u[o.id] = o.uklad || o.domyslny;
  return u;
}

function przyczepUklad(s, ukl) {
  for (const o of s.okna) o.uklad = ukl[o.id] ? { ...ukl[o.id] } : null;
}

// ---------- nakładanie na stronę ----------

function zastosuj() {
  const szeroko = mq.matches;
  for (const s of siatki) {
    s.el.style.gridTemplateRows = szeroko && s.rzedy ? s.rzedy.map((p) => p + "px").join(" ") : "";
    for (const o of s.okna) {
      const p = o.uklad;
      if (szeroko && p) {
        o.el.style.gridColumn = `${p.c} / span ${p.w}`;
        o.el.style.gridRow = `${p.r} / span ${p.h}`;
      } else {
        o.el.style.gridColumn = "";
        o.el.style.gridRow = "";
      }
    }
    if (szeroko && s.wlasny) {
      // Litery „S"/„A" z oznaczenia.js siedzą w prawym górnym rogu siatki —
      // okno, które tam trafi, musi zostawić im miejsce w nagłówku.
      const u = biezacy(s);
      for (const o of s.okna) o.el.classList.toggle("t-naroznik", u[o.id].c + u[o.id].w === KOLUMN + 1 && u[o.id].r === 1);
    }
  }
}

function powiadomOZmianie() {
  window.dispatchEvent(new Event("resize"));
  window.dispatchEvent(new CustomEvent("okna:zmiana"));
}

// ---------- uchwyty ----------

function usunUchwyty() {
  document.querySelectorAll(".t-uchwyt").forEach((u) => u.remove());
}

function zblizone(a, b) {
  return a.r < b.r + b.h && b.r < a.r + a.h;
}

// Grupy okien tworzących jedną, ciągłą linię podziału pionowego na linii x.
function grupyLinii(s, u, x) {
  const dotyka = s.okna.filter((o) => u[o.id].c + u[o.id].w === x || u[o.id].c === x);
  const rodzic = dotyka.map((_, i) => i);
  const znajdz = (i) => (rodzic[i] === i ? i : (rodzic[i] = znajdz(rodzic[i])));
  for (let i = 0; i < dotyka.length; i++) {
    for (let j = i + 1; j < dotyka.length; j++) {
      const a = u[dotyka[i].id];
      const b = u[dotyka[j].id];
      // przecinają się albo stykają wierszami => ta sama, ciągła linia
      if (a.r <= b.r + b.h && b.r <= a.r + a.h) rodzic[znajdz(i)] = znajdz(j);
    }
  }
  const grupy = {};
  dotyka.forEach((o, i) => (grupy[znajdz(i)] = grupy[znajdz(i)] || []).push(o));
  return Object.values(grupy);
}

function zbudujUchwyty(s) {
  const u = biezacy(s);
  let seg = 0;
  // pionowe: na prawej krawędzi okna, które ma po prawej sąsiada
  for (let x = 2; x <= KOLUMN; x++) {
    for (const grupa of grupyLinii(s, u, x)) {
      const lewe = grupa.filter((o) => u[o.id].c + u[o.id].w === x);
      const prawe = grupa.filter((o) => u[o.id].c === x);
      if (!lewe.length || !prawe.length) continue;
      const id = `${s.klucz}-p${seg++}`;
      for (const o of lewe) {
        if (!prawe.some((p) => zblizone(u[o.id], u[p.id]))) continue;
        const el = document.createElement("div");
        el.className = "t-uchwyt t-uchwyt-pion";
        el.dataset.seg = id;
        el.addEventListener("pointerdown", (e) => startPion(e, s, x, grupa));
        el.addEventListener("pointerenter", () => podswietl(id, true));
        el.addEventListener("pointerleave", () => podswietl(id, false));
        o.el.appendChild(el);
      }
    }
  }
  // poziome: na dolnej krawędzi okna (zmienia wysokość wiersza, na którym kończy się okno)
  for (const o of s.okna) {
    const p = u[o.id];
    const tor = p.r + p.h - 1;
    const el = document.createElement("div");
    el.className = "t-uchwyt t-uchwyt-poziom";
    el.dataset.seg = `${s.klucz}-w${tor}`;
    el.addEventListener("pointerdown", (e) => startPoziom(e, s, tor));
    el.addEventListener("pointerenter", () => podswietl(el.dataset.seg, true));
    el.addEventListener("pointerleave", () => podswietl(el.dataset.seg, false));
    o.el.appendChild(el);
  }
}

function podswietl(seg, wlacz) {
  document.querySelectorAll(`.t-uchwyt[data-seg="${seg}"]`).forEach((e) => e.classList.toggle("t-uchwyt-aktywny", wlacz));
}

function odbudujUchwyty() {
  usunUchwyty();
  if (!mq.matches) return;
  for (const s of siatki) zbudujUchwyty(s);
}

// ---------- przeciąganie: szerokość ----------

function przeciaganie(e, przy, koniec, kursor) {
  e.preventDefault();
  const cel = e.currentTarget;
  try {
    cel.setPointerCapture(e.pointerId);
  } catch (err) {
    /* przeglądarka bez przechwytu wskaźnika — przeciąganie nadal działa w obrębie uchwytu */
  }
  document.body.classList.add("t-przeciaganie");
  document.body.style.cursor = kursor;
  let czeka = false;
  let ostatnie = e;
  const ruch = (ev) => {
    ostatnie = ev;
    if (czeka) return;
    czeka = true;
    requestAnimationFrame(() => {
      czeka = false;
      przy(ostatnie);
    });
  };
  const stop = () => {
    cel.removeEventListener("pointermove", ruch);
    cel.removeEventListener("pointerup", stop);
    cel.removeEventListener("pointercancel", stop);
    document.body.classList.remove("t-przeciaganie");
    document.body.style.cursor = "";
    przy(ostatnie);
    koniec();
  };
  cel.addEventListener("pointermove", ruch);
  cel.addEventListener("pointerup", stop);
  cel.addEventListener("pointercancel", stop);
}

function startPion(e, s, x, grupa) {
  const u0 = kopia(biezacy(s));
  const szer = s.el.getBoundingClientRect().width / KOLUMN;
  const startX = e.clientX;
  const lewe = grupa.filter((o) => u0[o.id].c + u0[o.id].w === x);
  const prawe = grupa.filter((o) => u0[o.id].c === x);
  const najmniejLewe = Math.min(...lewe.map((o) => u0[o.id].w));
  const najmniejPrawe = Math.min(...prawe.map((o) => u0[o.id].w));
  const dMin = -(najmniejLewe - MIN_KOL);
  const dMax = najmniejPrawe - MIN_KOL;
  przeciaganie(
    e,
    (ev) => {
      const d = ograniczenie(Math.round((ev.clientX - startX) / szer), dMin, dMax);
      const u = kopia(u0);
      for (const o of lewe) u[o.id].w += d;
      for (const o of prawe) {
        u[o.id].c += d;
        u[o.id].w -= d;
      }
      przyczepUklad(s, u);
      s.wlasny = true;
      zastosuj();
      powiadomOZmianie();
    },
    () => {
      odbudujUchwyty();
      zapiszPozniej();
    },
    "col-resize"
  );
}

// ---------- przeciąganie: wysokość ----------

function biezaceWysokosci(s) {
  if (s.rzedy) return s.rzedy.slice();
  return doLiczb(getComputedStyle(s.el).gridTemplateRows).map((p) => Math.round(p));
}

function startPoziom(e, s, tor) {
  const wys0 = biezaceWysokosci(s);
  const startY = e.clientY;
  przeciaganie(
    e,
    (ev) => {
      const wys = wys0.slice();
      wys[tor - 1] = Math.round(ograniczenie(wys0[tor - 1] + ev.clientY - startY, MIN_WYS, 3000));
      s.rzedy = wys;
      s.wlasny = true;
      zastosuj();
      powiadomOZmianie();
    },
    () => {
      zapiszPozniej();
    },
    "row-resize"
  );
}

// ---------- zamiana okien miejscami (przeciąganie za nagłówek) ----------

function cosInteraktywnego(el) {
  return !!el.closest("button, a, input, select, textarea, label, summary, .oznaczenie-bloku, .t-pomoc");
}

function podlaczZamiane() {
  document.addEventListener("pointerdown", (e) => {
    if (!mq.matches || e.button !== 0 || e.pointerType === "touch") return;
    const naglowek = e.target.closest && e.target.closest(".t-naglowek");
    if (!naglowek || cosInteraktywnego(e.target)) return;
    const okno = naglowek.closest(".t-okno");
    const s = siatki.find((g) => g.okna.some((o) => o.el === okno));
    if (!s || s.okna.length < 2) return;
    zacznijZamiane(e, s, s.okna.find((o) => o.el === okno));
  });
}

function zacznijZamiane(e, s, zrodlo) {
  const startX = e.clientX;
  const startY = e.clientY;
  let trwa = false;
  let cel = null;
  const oznacz = (o) => {
    if (cel === o) return;
    if (cel) cel.el.classList.remove("t-cel-zamiany");
    cel = o;
    if (cel) cel.el.classList.add("t-cel-zamiany");
  };
  const ruch = (ev) => {
    if (!trwa && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 6) return;
    if (!trwa) {
      trwa = true;
      zrodlo.el.classList.add("t-przeciagane");
      document.body.classList.add("t-przeciaganie");
      document.body.style.cursor = "grabbing";
      window.getSelection && window.getSelection().removeAllRanges();
    }
    const pod = document.elementFromPoint(ev.clientX, ev.clientY);
    const okno = pod && pod.closest && pod.closest(".t-okno");
    oznacz(s.okna.find((o) => o.el === okno && o !== zrodlo) || null);
  };
  const stop = () => {
    document.removeEventListener("pointermove", ruch);
    document.removeEventListener("pointerup", stop);
    document.removeEventListener("pointercancel", stop);
    if (!trwa) return;
    zrodlo.el.classList.remove("t-przeciagane");
    document.body.classList.remove("t-przeciaganie");
    document.body.style.cursor = "";
    if (cel) {
      cel.el.classList.remove("t-cel-zamiany");
      const u = kopia(biezacy(s));
      const a = u[zrodlo.id];
      u[zrodlo.id] = u[cel.id];
      u[cel.id] = a;
      przyczepUklad(s, u);
      s.wlasny = true;
      zastosuj();
      odbudujUchwyty();
      powiadomOZmianie();
      zapiszPozniej();
    }
    // klik, który kończy przeciąganie, nie ma robić nic poza zamianą
    const polknij = (ev) => ev.stopPropagation();
    document.addEventListener("click", polknij, { capture: true, once: true });
    setTimeout(() => document.removeEventListener("click", polknij, true), 0);
  };
  document.addEventListener("pointermove", ruch);
  document.addEventListener("pointerup", stop);
  document.addEventListener("pointercancel", stop);
}

// ---------- zapis ----------

// Karta może oznaczyć siatkę atrybutem `data-uklad-wersja`, gdy zmienia się zestaw jej okien (zadanie 028).
// Zapisany układ bez tej samej wersji jest wtedy pomijany, zamiast przyczepiać stare prostokąty do nowych okien.
function wersjaKarty(s) {
  return s.el.dataset.ukladWersja || "";
}

function wartoscDoZapisu() {
  const siatkiOut = {};
  for (const s of siatki) {
    if (!s.wlasny) continue;
    siatkiOut[s.klucz] = { okna: biezacy(s), rzedy: s.rzedy, wersjaKarty: wersjaKarty(s) };
  }
  return { wersja: 1, siatki: siatkiOut };
}

function wczytajZWartosci(w) {
  if (!w || w.wersja !== 1 || !w.siatki) return false;
  let cos = false;
  for (const s of siatki) {
    const d = w.siatki[s.klucz];
    if (!d || !d.okna || !poprawny(s, d.okna)) continue;
    if ((d.wersjaKarty || "") !== wersjaKarty(s)) continue;
    przyczepUklad(s, d.okna);
    s.rzedy = Array.isArray(d.rzedy) && d.rzedy.every((x) => x >= MIN_WYS && x <= 3000) ? d.rzedy : null;
    s.wlasny = true;
    cos = true;
  }
  return cos;
}

function ustawStan(tekst, blad) {
  stanZapisu = { tekst, blad: !!blad };
  if (elStanu) {
    // przycisk w szynie ikon: stan zapisu w dymku, a błąd jako czerwona kropka
    elStanu.dataset.dymek = OPIS_PRZYCISKU + (tekst ? `\n${tekst}` : "");
    const kropka = elStanu.querySelector(".sidebar-uklad-stan-kropka");
    if (kropka) kropka.hidden = !blad;
  }
}

function cacheZapisz(w) {
  try {
    if (w) localStorage.setItem("uklad_cache_" + karta, JSON.stringify(w));
    else localStorage.removeItem("uklad_cache_" + karta);
  } catch (e) {
    /* tryb prywatny — układ działa do końca wizyty */
  }
}

function cacheOdczytaj() {
  try {
    const t = localStorage.getItem("uklad_cache_" + karta);
    return t ? JSON.parse(t) : null;
  } catch (e) {
    return null;
  }
}

function zapiszPozniej() {
  const w = wartoscDoZapisu();
  cacheZapisz(w);
  clearTimeout(zapisTimer);
  if (!(maModul("USTAW") && USTAW.dostepne())) {
    ustawStan("Układ zapamiętany tylko w tej przeglądarce (wersja poglądowa).");
    return;
  }
  ustawStan("Zapisuję układ…");
  zapisTimer = setTimeout(async () => {
    try {
      await USTAW.zmien(kluczUkladu, null, () => wartoscDoZapisu(), "układ okien");
      ustawStan("Układ zapisany w repozytorium.");
    } catch (e) {
      ustawStan("Nie udało się zapisać układu w repozytorium: " + (e && e.message ? e.message : e), true);
    }
  }, OPOZNIENIE_ZAPISU);
}

function przywroc() {
  for (const s of siatki) {
    s.rzedy = null;
    s.wlasny = false;
    for (const o of s.okna) o.uklad = null;
    for (const o of s.okna) o.el.classList.remove("t-naroznik");
  }
  zastosuj();
  // klasę t-naroznik z HTML odtwarzamy z domyślnego układu: prawy górny róg
  for (const s of siatki) {
    for (const o of s.okna) {
      const d = o.domyslny;
      if (d && d.c + d.w === KOLUMN + 1 && d.r === 1) o.el.classList.add("t-naroznik");
    }
  }
  odbudujUchwyty();
  powiadomOZmianie();
  cacheZapisz(null);
  clearTimeout(zapisTimer);
  if (maModul("USTAW") && USTAW.dostepne()) {
    ustawStan("Przywracam układ…");
    USTAW.zmien(kluczUkladu, null, () => ({ wersja: 1, siatki: {} }), "przywrócenie układu")
      .then(() => ustawStan("Przywrócono układ domyślny (zapisano w repozytorium)."))
      .catch((er) => ustawStan("Nie udało się zapisać w repozytorium: " + er.message, true));
  } else {
    ustawStan("Przywrócono układ domyślny.");
  }
}

// ---------- pasek boczny ----------

const OPIS_PRZYCISKU = "Przywróć układ okien\nKrawędź okna zmienia rozmiar, nagłówek zamienia okna miejscami.";
const IKONA_UKLADU = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 9v12"/></svg>';

// Przycisk w dolnej części szyny ikon (sidebar.js tworzy `.sidebar-dol`).
function zbudujPanel() {
  const dol = document.querySelector("nav.sidebar .sidebar-dol");
  if (!dol || dol.querySelector("#uklad-przywroc")) return;
  const b = document.createElement("button");
  b.type = "button";
  b.id = "uklad-przywroc";
  b.className = "sidebar-ikona sidebar-uklad-przycisk";
  b.innerHTML = IKONA_UKLADU + '<span class="sidebar-uklad-stan-kropka" hidden></span>';
  b.setAttribute("aria-label", "Przywróć układ okien");
  b.addEventListener("click", przywroc);
  elStanu = b;
  ustawStan(stanZapisu.tekst, stanZapisu.blad);
  dol.appendChild(b);
}

// ---------- start ----------

function przygotuj() {
  if (przygotowane || !mq.matches) return;
  for (const s of siatki) zmierzDomyslne(s);
  przygotowane = true;
  const z = cacheOdczytaj();
  if (z) wczytajZWartosci(z);
  zastosuj();
  odbudujUchwyty();
  powiadomOZmianie();
  wczytajZRepozytorium();
}

// `USTAW` jest zadeklarowane jako `const` w ustawienia.js, więc nie jest polem
// `window` — sprawdzamy je przez `typeof`, a `PR` przez `window.PR`.
function maModul(nazwa) {
  return nazwa === "USTAW" ? typeof USTAW !== "undefined" : !!window[nazwa];
}

function poczekajNaModul(nazwa, plik) {
  return new Promise((ok) => {
    if (maModul(nazwa)) return ok(true);
    if (!document.querySelector(`script[src$="${plik}"]`) && SKRYPT) {
      const sk = document.createElement("script");
      sk.src = SKRYPT.replace(/okna\.js(\?.*)?$/, plik);
      document.head.appendChild(sk);
    }
    let proby = 0;
    const t = setInterval(() => {
      if (maModul(nazwa) || ++proby > 60) {
        clearInterval(t);
        ok(maModul(nazwa));
      }
    }, 100);
  });
}

async function wczytajZRepozytorium() {
  if (!(await poczekajNaModul("PR", "projekty.js")) || !(await poczekajNaModul("USTAW", "ustawienia.js"))) return;
  if (!USTAW.dostepne()) {
    if (stanZapisu.tekst === "" && przygotowane) ustawStan("Brak tokenu GitHub, układ pamiętany tylko w tej przeglądarce.");
    return;
  }
  try {
    const { wartosc } = await USTAW.wczytaj(kluczUkladu, null);
    if (wartosc && wczytajZWartosci(wartosc)) {
      cacheZapisz(wartosc);
      zastosuj();
      odbudujUchwyty();
      powiadomOZmianie();
    }
    ustawStan("Układ wczytany z repozytorium.");
  } catch (e) {
    ustawStan("Nie udało się wczytać układu z repozytorium: " + e.message, true);
  }
}

function start() {
  siatki = zbierzSiatki();
  if (!siatki.length) return;
  karta = nazwaKarty();
  kluczUkladu = "uklad-" + karta;
  document.body.classList.add("t-ma-uklad");
  zbudujPanel();
  podlaczZamiane();
  przygotuj();
  mq.addEventListener("change", () => {
    if (mq.matches) {
      if (!przygotowane) przygotuj();
      else {
        zastosuj();
        odbudujUchwyty();
      }
    } else {
      zastosuj();
      usunUchwyty();
    }
    powiadomOZmianie();
  });
}

// Pasek boczny i okna muszą już istnieć: skrypt ładuje się po sidebar.js,
// a okna są w HTML od początku.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
})();
