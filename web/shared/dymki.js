"use strict";

/**
 * Wspólny moduł dymków i schowanych opisów (zadanie 034, styl TradingView).
 * Ładuje go web/shared/sidebar.js, więc działa na każdej stronie bez
 * dopisywania go do HTML. Robi dwie rzeczy:
 *
 * 1. DYMKI. Zamienia atrybuty `title` (natywna podpowiedź przeglądarki, wolna i
 *    brzydka) oraz `data-dymek` na szybki, ciemny dymek jak w TradingView. Działa
 *    na elementach dodawanych później przez JS (delegacja zdarzeń), z klawiatury
 *    (fokus) i na telefonie (dotknięcie ikony „i").
 * 2. SCHOWANE OPISY. Statyczne akapity pomocnicze w oknach (`.opis`, ostrzeżenie o
 *    tokenie) znikają z ekranu, a ich treść trafia do ikony „i" w nagłówku okna,
 *    z dymkiem po najechaniu. Na ekranie zostają dane, wykresy, pola i przyciski.
 *    Akapit z linkiem, polem albo przyciskiem, z `id` (dynamiczna treść) i błędy
 *    zostają widoczne.
 */
(function () {
  const OPOZNIENIE_MS = 280;
  const dymek = document.createElement("div");
  dymek.className = "dymek-tv";
  dymek.setAttribute("role", "tooltip");
  dymek.id = "dymek-tv";
  let cel = null;
  let zegar = null;
  let zegarDotyku = null;

  const jestInfo = (el) => el.classList.contains("zp-info") || el.classList.contains("t-pomoc");

  // `title` przenosimy do `data-dymek`, żeby przeglądarka nie pokazała własnej podpowiedzi.
  function tekstDymka(el) {
    if (el.hasAttribute("title")) {
      const t = el.getAttribute("title");
      el.removeAttribute("title");
      if (t) {
        el.dataset.dymek = t;
        if (!el.getAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", t);
      }
    }
    return el.dataset.dymek || "";
  }

  function znajdzCel(wezel) {
    if (!(wezel instanceof Element) || dymek.contains(wezel)) return null;
    const el = wezel.closest("[data-dymek],[title]");
    if (!el || el.tagName === "IFRAME" || el.tagName === "HTML" || el.tagName === "svg") return null;
    return tekstDymka(el) ? el : null;
  }

  function ustaw(el) {
    const r = el.getBoundingClientRect();
    const w = dymek.offsetWidth;
    const h = dymek.offsetHeight;
    const przySzynie = !!el.closest(".sidebar") && window.innerWidth > 700;
    let lewo;
    let gora;
    if (przySzynie) {
      lewo = r.right + 8;
      gora = r.top + r.height / 2 - h / 2;
    } else {
      lewo = r.left + r.width / 2 - w / 2;
      gora = r.bottom + 8;
      if (gora + h > window.innerHeight - 4) gora = r.top - h - 8;
    }
    lewo = Math.max(4, Math.min(lewo, window.innerWidth - w - 4));
    gora = Math.max(4, Math.min(gora, window.innerHeight - h - 4));
    dymek.style.left = `${Math.round(lewo)}px`;
    dymek.style.top = `${Math.round(gora)}px`;
  }

  function pokaz(el) {
    const tekst = tekstDymka(el);
    if (!tekst) return;
    cel = el;
    dymek.textContent = tekst;
    dymek.style.left = "-9999px";
    dymek.style.top = "0px";
    dymek.classList.add("widoczny");
    ustaw(el);
    if (jestInfo(el)) el.classList.add("dymek-aktywny");
    el.setAttribute("aria-describedby", "dymek-tv");
  }

  function ukryj() {
    clearTimeout(zegar);
    clearTimeout(zegarDotyku);
    dymek.classList.remove("widoczny");
    if (cel) {
      cel.classList.remove("dymek-aktywny");
      cel.removeAttribute("aria-describedby");
    }
    cel = null;
  }

  function zaplanuj(el, opoznienie) {
    clearTimeout(zegar);
    zegar = setTimeout(() => pokaz(el), opoznienie);
  }

  document.addEventListener("pointerover", (e) => {
    if (e.pointerType === "touch") return;
    const el = znajdzCel(e.target);
    if (!el) {
      if (cel) ukryj();
      return;
    }
    if (el === cel) return;
    ukryj();
    zaplanuj(el, OPOZNIENIE_MS);
  });
  document.addEventListener("pointerout", (e) => {
    if (e.pointerType === "touch") return;
    if (cel && !cel.contains(e.relatedTarget)) ukryj();
    else if (!cel) clearTimeout(zegar);
  });
  document.addEventListener("focusin", (e) => {
    const el = znajdzCel(e.target);
    if (el) {
      ukryj();
      zaplanuj(el, 0);
    }
  });
  document.addEventListener("focusout", ukryj);
  // Dotyk: dymek pokazują tylko ikony „i" (inne elementy z dymkiem to przyciski, których
  // dotknięcie ma działać od razu). Zostaje kilka sekund albo do dotknięcia gdzie indziej.
  document.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "touch") {
      ukryj();
      return;
    }
    const el = znajdzCel(e.target);
    ukryj();
    if (el && jestInfo(el)) {
      pokaz(el);
      zegarDotyku = setTimeout(ukryj, 5000);
    }
  });
  document.addEventListener("keydown", (e) => e.key === "Escape" && ukryj());
  window.addEventListener("scroll", ukryj, true);
  window.addEventListener("resize", ukryj);

  // ---- schowane opisy -----------------------------------------------------------
  const SELEKTOR_OPISOW = ".t-tresc p.opis, .t-tresc .zp-token-ostrzezenie, .t-tresc .t-podtytul, .t-tresc .so-opcje-stopka";

  function nadajSieDoSchowania(p) {
    if (p.dataset.opisPrzeniesiony || p.id) return false;
    if (p.querySelector("a, button, input, select, textarea")) return false;
    if (p.classList.contains("blad")) return false;
    return p.textContent.trim().length >= 20;
  }

  function ikonaInfo(okno) {
    let ikona = okno.querySelector(":scope > .t-naglowek .zp-info");
    if (ikona) return ikona;
    const naglowek = okno.querySelector(":scope > .t-naglowek");
    if (!naglowek) return null;
    let akcje = naglowek.querySelector(".t-akcje");
    if (!akcje) {
      akcje = document.createElement("div");
      akcje.className = "t-akcje";
      naglowek.appendChild(akcje);
    }
    ikona = document.createElement("span");
    ikona.className = "zp-info";
    ikona.textContent = "i";
    ikona.setAttribute("role", "img");
    ikona.setAttribute("aria-label", "Opis okna");
    akcje.insertBefore(ikona, akcje.firstChild);
    return ikona;
  }

  function przeniesOpisy(korzen) {
    for (const okno of (korzen || document).querySelectorAll(".t-okno")) {
      const ikona0 = okno.querySelector(":scope > .t-naglowek .zp-info");
      for (const p of okno.querySelectorAll(SELEKTOR_OPISOW)) {
        if (!nadajSieDoSchowania(p)) continue;
        const ikona = ikona0 || ikonaInfo(okno);
        if (!ikona) continue;
        const tekst = p.textContent.replace(/\s+/g, " ").trim();
        const bylo = ikona.dataset.dymek || "";
        ikona.dataset.dymek = bylo ? `${bylo}\n\n${tekst}` : tekst;
        p.dataset.opisPrzeniesiony = "1";
        p.classList.add("opis-schowany");
      }
    }
  }

  let odroczone = null;
  function zaplanujPrzeglad() {
    clearTimeout(odroczone);
    odroczone = setTimeout(() => przeniesOpisy(), 120);
  }

  function start() {
    document.body.appendChild(dymek);
    przeniesOpisy();
    const main = document.querySelector("main") || document.body;
    new MutationObserver(zaplanujPrzeglad).observe(main, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
