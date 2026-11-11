"use strict";

/**
 * Wspólny moduł „Przestrzeń robocza" (zadanie 041): okna z zakładkami, które użytkownik
 * sam układa na karcie. Wydzielony 2026-11-01 z karty Social (zadanie 035, runda 2), żeby
 * Social, Stan rynku i Pozycja działały tak samo. Ładuje się zwykłym tagiem <script>
 * przed app.js karty (razem z projekty.js i ustawienia.js, bo zapisuje przez USTAW).
 *
 * Co widzi użytkownik: pasek „+ Dodaj okno", „Przywróć układ …" i „Wyczyść ekran"; każde
 * okno ma zakładki (numer i nazwa elementu, „×" zamyka element), „+" dokłada kolejny element
 * jako zakładkę, a „⧉" przenosi aktywną zakładkę do nowego okna obok. Prawa krawędź okna
 * zmienia szerokość (w 12 kolumnach), dolna wysokość (w pikselach), róg obie naraz, a
 * przeciągnięcie za pasek zakładek zmienia kolejność okien. Na ekranie do 900 px okna stoją
 * jedno pod drugim, bez uchwytów. Ten sam element można otworzyć tylko raz.
 *
 * Zapis: `ustawienia/<klucz>.json` przez USTAW (shared/ustawienia.js), z podręczną kopią w
 * localStorage; format {wersja: 1, zmieniono, panele: [{id, szer, wys, aktywna, elementy}]}.
 *
 * Dwa rodzaje elementów (definicja: {nazwa, opis, szer, wys, ...}):
 *   - `fragment` (tekst HTML okna): element montuje się dopiero przy pierwszym pokazaniu
 *     zakładki i wtedy woła `init()` i `rysuj()`; nieotwarty nic nie pobiera (Social),
 *   - `wezel` (selektor albo węzeł, który już jest na stronie): element istnieje od początku
 *     w ukrytym „magazynie", karta liczy go i rysuje zawsze, a przestrzeń tylko przenosi go
 *     między oknami (Stan rynku i Pozycja, gdzie jedno przeliczenie obsługuje wszystkie okna).
 * Opcjonalne `klasa` zastępuje klasy okna (Social); bez niej moduł zdejmuje tylko klasy
 * siatki (`karta`, `t-kN`, `t-naroznik`), a `t-okno` zostaje, więc style treści się nie zmieniają.
 *
 * Numerek bloku (oznaczenia.js) dostaje cała przestrzeń jako jeden blok, bo okna powstają
 * dynamicznie; numer elementu (kolejność z `kolejnosc`) widać na jego zakładce.
 *
 * Wystawia jeden globalny obiekt `PRZESTRZEN` z funkcją `utworz(opcje)`; opcje opisuje
 * komentarz nad nią.
 */
const PRZESTRZEN = (function () {
  const MIN_SZER = 3, MAX_SZER = 12, MIN_WYS = 220, MAX_WYS = 2000;
  const ogran = (v, a, b) => Math.max(a, Math.min(b, v));
  const szeroki = () => window.matchMedia("(min-width: 901px)").matches;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[z]));

  function toast(tekst) {
    const t = document.createElement("div");
    t.className = "prz-toast"; t.textContent = tekst;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 4200);
  }

  // --- menu wyboru elementu (jedno naraz na stronie) ----------------------------------
  let menuKotwica = null;
  function menuZamknij() {
    const m = document.getElementById("prz-menu"); if (m) m.remove();
    menuKotwica = null;
    document.removeEventListener("pointerdown", menuPoza, true);
    document.removeEventListener("keydown", menuKlawisz, true);
  }
  function menuPoza(e) {
    if (e.target.closest("#prz-menu") || (menuKotwica && menuKotwica.contains(e.target))) return;
    menuZamknij();
  }
  function menuKlawisz(e) { if (e.key === "Escape") menuZamknij(); }
  // pozycje: [{id, nr, nazwa, opis}]; drugi klik w ten sam przycisk zamyka menu.
  function menu(kotwica, pozycje, naWybor) {
    const ta = menuKotwica === kotwica;
    menuZamknij();
    if (ta) return;
    const m = document.createElement("div");
    m.id = "prz-menu"; m.className = "prz-menu";
    m.innerHTML = pozycje.length
      ? pozycje.map((x) => `<button type="button" data-id="${esc(x.id)}"><b><span class="prz-nr">${x.nr}</span>${esc(x.nazwa)}</b><span>${esc(x.opis)}</span></button>`).join("")
      : '<p class="prz-pusto">Wszystkie elementy są już otwarte.</p>';
    document.body.appendChild(m);
    const r = kotwica.getBoundingClientRect();
    m.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - m.offsetWidth - 8))}px`;
    m.style.top = `${r.bottom + 4}px`;
    m.addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) { menuZamknij(); naWybor(b.dataset.id); } });
    menuKotwica = kotwica;
    setTimeout(() => { document.addEventListener("pointerdown", menuPoza, true); document.addEventListener("keydown", menuKlawisz, true); });
  }

  /**
   * opcje:
   *   korzen        element (albo selektor), w którym ma stanąć przestrzeń; moduł wstawia na
   *                 jego początku pasek i siatkę okien, a węzły elementów `wezel` szuka w nim,
   *   elementy      {id: {nazwa, opis, szer, wys, fragment | wezel, klasa?, init?, rysuj?}},
   *   kolejnosc     lista id, z niej biorą się numery zakładek (1, 2, …) i kolejność w menu,
   *   ukladDomyslny [[id albo [id, …], szerokość w kolumnach, wysokość w px], …],
   *   start         "pusty" (bez zapisu: pusty ekran, jak w Social) albo "domyslny",
   *   klucz, cache  plik `ustawienia/<klucz>.json` i klucz podręcznej kopii w localStorage,
   *   opisZapisu    końcówka opisu commita z zapisem układu,
   *   napisy        {dodajTytul, domyslny, domyslnyTytul, potwierdzDomyslny},
   *   pasekPrawo    HTML dopisany po prawej stronie paska (np. stan danych i „↻"),
   *   powiadom      funkcja krótkiego komunikatu (domyślnie własny dymek u dołu ekranu).
   * Zwraca {przywroc, zamontowane}: `przywroc()` buduje okna z zapisu (wołaj raz, gdy karta
   * jest gotowa), `zamontowane()` podaje id elementów obecnych teraz w oknach.
   */
  function utworz(o) {
    const korzen = typeof o.korzen === "string" ? document.querySelector(o.korzen) : o.korzen;
    const napisy = Object.assign({
      dodajTytul: "Dodaj okno z jednym z elementów karty",
      domyslny: "Przywróć układ domyślny",
      domyslnyTytul: "Ustaw okna w układzie domyślnym karty",
      potwierdzDomyslny: "Zastąpić obecne okna układem domyślnym?",
    }, o.napisy || {});
    const powiadom = o.powiadom || toast;
    const kolejnosc = o.kolejnosc || Object.keys(o.elementy);
    const s = { panele: [], dom: new Map(), licznik: 0, zmieniono: 0, lokalnie: false, timer: null, ostrzezono: false };
    const nr = (id) => kolejnosc.indexOf(id) + 1;

    // --- szkielet: pasek, siatka okien, magazyn elementów stałych ---------------------
    korzen.classList.add("prz-karta");
    // Siatka okien: ta z HTML karty (Stan rynku i Pozycja mają ją od początku, żeby mapa kodu
    // widziała całą przestrzeń jako jeden blok, tak jak oznaczenia.js), a jeśli jej nie ma, nowa.
    let pr = korzen.querySelector(":scope > .prz-przestrzen");
    if (!pr) { pr = document.createElement("div"); pr.className = "prz-przestrzen"; korzen.prepend(pr); }
    korzen.insertAdjacentHTML("afterbegin", '<div class="prz-pasek">'
      + `<button type="button" class="t-mini prz-dodaj" data-prz="dodaj" title="${esc(napisy.dodajTytul)}">+ Dodaj okno</button>`
      + `<button type="button" class="t-mini" data-prz="domyslny" title="${esc(napisy.domyslnyTytul)}">${esc(napisy.domyslny)}</button>`
      + '<button type="button" class="t-mini" data-prz="wyczysc" title="Zamknij wszystkie okna i wróć do pustego ekranu">Wyczyść ekran</button>'
      + (o.pasekPrawo ? `<span class="prz-pasek-prawo">${o.pasekPrawo}</span>` : "")
      + '</div>');
    let magazyn = korzen.querySelector(":scope > .prz-magazyn");
    if (!magazyn) {
      magazyn = document.createElement("div");
      magazyn.className = "prz-magazyn"; magazyn.hidden = true;
      korzen.appendChild(magazyn);
    }

    // Okno elementu bez tytułu (nazwę pokazuje zakładka) i bez klas siatki; nagłówek zostaje
    // jako pasek akcji, gdy ma przyciski albo opis do schowania pod ikoną „i” (dymki.js).
    function przygotuj(el, id) {
      const def = o.elementy[id];
      if (def.klasa != null) el.className = `prz-element ${def.klasa}`;
      else {
        el.classList.remove("karta", "t-naroznik", "blok-numerowany");
        [...el.classList].filter((k) => /^t-k\d+$/.test(k)).forEach((k) => el.classList.remove(k));
        el.classList.add("prz-element");
      }
      el.dataset.element = id;
      const gora = el.querySelector(":scope > .t-naglowek");
      const h2 = gora && gora.querySelector("h2");
      if (h2) h2.remove();
      const akcje = gora && gora.querySelector(".t-akcje");
      const opis = el.querySelector(".t-tresc p.opis");
      if (gora && !(akcje && akcje.children.length) && !opis) gora.remove();
      return el;
    }

    // Elementy stałe („wezel”): od razu do magazynu, karta znajduje je po id jak dotąd.
    const elementy = {}, wezly = new Map();
    for (const [id, def] of Object.entries(o.elementy)) {
      if (def.wezel) {
        const el = typeof def.wezel === "string" ? korzen.querySelector(def.wezel) : def.wezel;
        if (!el) { console.warn(`Przestrzeń robocza: nie ma elementu „${id}” (${def.wezel})`); continue; }
        elementy[id] = def;
        wezly.set(id, przygotuj(el, id));
        magazyn.appendChild(el);
      } else if (def.fragment) elementy[id] = def;
    }
    const lista = () => kolejnosc.filter((id) => elementy[id]);
    const otwarte = () => new Set(s.panele.flatMap((p) => p.elementy));
    const wolne = () => lista().filter((id) => !otwarte().has(id)).map((id) => ({ id, nr: nr(id), nazwa: elementy[id].nazwa, opis: elementy[id].opis || "" }));

    // --- zapis -----------------------------------------------------------------------------
    function stanZapisu() {
      return { wersja: 1, zmieniono: s.zmieniono, panele: s.panele.map((p) => ({ id: p.id, szer: p.szer, wys: p.wys, aktywna: p.aktywna, elementy: [...p.elementy] })) };
    }
    function zapisz() {
      s.lokalnie = true;
      clearTimeout(s.timer);
      s.timer = setTimeout(() => {
        s.zmieniono = Date.now();
        const stan = stanZapisu();
        try { localStorage.setItem(o.cache, JSON.stringify(stan)); } catch (e) { /* tryb prywatny */ }
        if (typeof USTAW !== "undefined" && USTAW.dostepne()) USTAW.zmien(o.klucz, null, () => stan, o.opisZapisu || "układ okien").catch(() => {});
        else if (!s.ostrzezono) { s.ostrzezono = true; powiadom("W wersji poglądowej układ okien zostaje tylko w tej przeglądarce."); }
      }, 700);
    }

    // --- budowa okna -------------------------------------------------------------------------
    const nowyId = () => "p" + (++s.licznik);

    function budujPanel(p) {
      const el = document.createElement("section");
      el.className = "karta prz-panel"; el.dataset.panel = p.id;
      el.innerHTML = '<header class="prz-panel-gora"><div class="prz-karty" role="tablist"></div><div class="prz-panel-akcje">'
        + '<button type="button" class="t-mini" data-akcja="plus" title="Dodaj kolejny element do tego okna jako zakładkę">+</button>'
        + '<button type="button" class="t-mini" data-akcja="osobno" title="Przenieś aktywną zakładkę do nowego okna obok">⧉</button></div></header>'
        + '<div class="prz-panel-tresc"></div>'
        + '<i class="prz-uchwyt prz-uchwyt-p" data-uchwyt="p" title="Przeciągnij, żeby zmienić szerokość"></i>'
        + '<i class="prz-uchwyt prz-uchwyt-d" data-uchwyt="d" title="Przeciągnij, żeby zmienić wysokość"></i>'
        + '<i class="prz-uchwyt prz-uchwyt-r" data-uchwyt="r" title="Przeciągnij, żeby zmienić szerokość i wysokość"></i>';
      el.style.gridColumn = `span ${p.szer}`; el.style.height = `${p.wys}px`;
      s.dom.set(p.id, { el, zamontowane: new Set() });
      return el;
    }

    function karty(p) {
      const dom = s.dom.get(p.id);
      dom.el.querySelector(".prz-karty").innerHTML = p.elementy.map((id) => `<button type="button" role="tab" class="prz-tab${id === p.aktywna ? " aktywna" : ""}" data-el="${id}" aria-selected="${id === p.aktywna}"><span class="prz-nr">${nr(id)}</span>${esc(elementy[id].nazwa)}<span class="prz-x" data-zamknij="${id}" role="button" aria-label="Usuń element" title="Usuń ten element z okna">×</span></button>`).join("");
      dom.el.querySelectorAll(":scope > .prz-panel-tresc > .prz-element").forEach((e) => { e.hidden = e.dataset.element !== p.aktywna; });
      dom.el.querySelector('[data-akcja="osobno"]').hidden = p.elementy.length < 2;
    }

    // Element z fragmentu powstaje przy pierwszym pokazaniu zakładki: dostaje HTML, podpina
    // zdarzenia i rysuje się na wczytanych danych. Element stały tylko przechodzi do okna.
    function montuj(p, id) {
      const dom = s.dom.get(p.id), def = elementy[id];
      let el = wezly.get(id);
      if (!el) {
        const t = document.createElement("div");
        t.innerHTML = def.fragment.trim();
        el = przygotuj(t.firstElementChild, id);
      }
      dom.el.querySelector(".prz-panel-tresc").appendChild(el);
      dom.zamontowane.add(id);
      if (!wezly.has(id)) { if (def.init) def.init(); if (def.rysuj) def.rysuj(); }
    }

    function aktywuj(p, id, cicho) {
      p.aktywna = id;
      if (!s.dom.get(p.id).zamontowane.has(id)) montuj(p, id);
      karty(p);
      if (!cicho) window.dispatchEvent(new Event("resize"));
    }

    function pusty() {
      let e = pr.querySelector(":scope > .prz-pusty-ekran");
      if (s.panele.length) { if (e) e.remove(); return; }
      if (e) return;
      e = document.createElement("div"); e.className = "prz-pusty-ekran";
      e.innerHTML = '<h2>Pusty ekran</h2><p>Złóż własną przestrzeń: dodaj okno z jednego z elementów, zmieniaj mu rozmiar, dokładaj kolejne elementy jako zakładki albo stawiaj nowe okna obok.</p>'
        + `<div class="prz-szybkie">${lista().map((id) => `<button type="button" class="t-mini" data-dodaj="${id}" title="${esc(elementy[id].opis)}">+ ${nr(id)} ${esc(elementy[id].nazwa)}</button>`).join("")}</div>`;
      pr.appendChild(e);
    }

    // --- operacje na oknach --------------------------------------------------------------------
    function dodajPanel(id, za) {
      const def = elementy[id];
      const p = { id: nowyId(), szer: ogran(def.szer || 6, MIN_SZER, MAX_SZER), wys: ogran(def.wys || 520, MIN_WYS, MAX_WYS), aktywna: id, elementy: [id] };
      const poz = za ? s.panele.indexOf(za) + 1 : s.panele.length;
      s.panele.splice(poz, 0, p);
      const el = budujPanel(p);
      const nast = s.panele[poz + 1] && s.dom.get(s.panele[poz + 1].id);
      if (nast) pr.insertBefore(el, nast.el); else pr.appendChild(el);
      pusty(); karty(p); aktywuj(p, id);
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      zapisz();
    }

    function dodajZakladke(p, id) {
      p.elementy.push(id);
      aktywuj(p, id);
      zapisz();
    }

    function usun(p, id) {
      const dom = s.dom.get(p.id);
      const el = dom.el.querySelector(`:scope > .prz-panel-tresc > .prz-element[data-element="${id}"]`);
      if (el) { if (wezly.has(id)) magazyn.appendChild(el); else el.remove(); }
      dom.zamontowane.delete(id);
      const i = p.elementy.indexOf(id);
      p.elementy = p.elementy.filter((x) => x !== id);
      if (!p.elementy.length) {
        dom.el.remove(); s.dom.delete(p.id);
        s.panele = s.panele.filter((x) => x !== p);
        pusty();
      } else {
        aktywuj(p, p.aktywna === id ? p.elementy[Math.max(0, i - 1)] : p.aktywna);
      }
      zapisz();
    }

    function osobno(p) {
      if (p.elementy.length < 2) return;
      const id = p.aktywna;
      usun(p, id);
      dodajPanel(id, p);
    }

    // --- przeciąganie: rozmiar i kolejność -------------------------------------------------------
    function rozmiarPrzeciagnij(e, p, uchwyt) {
      if (!szeroki()) return;
      e.preventDefault();
      const dom = s.dom.get(p.id);
      const kol = (pr.clientWidth - 16) / 12;
      const start = { x: e.clientX, y: e.clientY, szer: p.szer, wys: p.wys };
      document.body.classList.add("prz-zmiana");
      const ruch = (ev) => {
        if (uchwyt !== "d") p.szer = ogran(Math.round(start.szer + (ev.clientX - start.x) / kol), MIN_SZER, MAX_SZER);
        if (uchwyt !== "p") p.wys = ogran(Math.round(start.wys + ev.clientY - start.y), MIN_WYS, MAX_WYS);
        dom.el.style.gridColumn = `span ${p.szer}`; dom.el.style.height = `${p.wys}px`;
      };
      const koniec = () => {
        document.removeEventListener("pointermove", ruch); document.removeEventListener("pointerup", koniec);
        document.body.classList.remove("prz-zmiana");
        window.dispatchEvent(new Event("resize")); zapisz();
      };
      document.addEventListener("pointermove", ruch); document.addEventListener("pointerup", koniec);
    }

    function kolejnoscPrzeciagnij(e, p) {
      if (!szeroki()) return;
      e.preventDefault();
      const dom = s.dom.get(p.id);
      dom.el.classList.add("prz-przeciagany");
      document.body.classList.add("prz-zmiana");
      const ruch = (ev) => {
        const cel = document.elementFromPoint(ev.clientX, ev.clientY);
        const inny = cel && cel.closest(".prz-panel");
        if (!inny || inny === dom.el || !pr.contains(inny)) return;
        const iInny = s.panele.findIndex((x) => x.id === inny.dataset.panel), iMoj = s.panele.indexOf(p);
        s.panele.splice(iMoj, 1); s.panele.splice(iInny, 0, p);
        if (iMoj > iInny) inny.before(dom.el); else inny.after(dom.el);
      };
      const koniec = () => {
        document.removeEventListener("pointermove", ruch); document.removeEventListener("pointerup", koniec);
        dom.el.classList.remove("prz-przeciagany"); document.body.classList.remove("prz-zmiana");
        window.dispatchEvent(new Event("resize")); zapisz();
      };
      document.addEventListener("pointermove", ruch); document.addEventListener("pointerup", koniec);
    }

    // --- stan: budowa z zapisu, układ domyślny, czyszczenie -------------------------------------------
    function stosuj(stan) {
      const widziane = new Set(), ids = new Set(), panele = [];
      for (const x of (stan && stan.panele) || []) {
        const el = (x.elementy || []).filter((id) => elementy[id] && !widziane.has(id) && widziane.add(id));
        if (!el.length) continue;
        let id = String(x.id || ""); if (!id || ids.has(id)) id = nowyId(); ids.add(id);
        panele.push({ id, szer: ogran(+x.szer || 6, MIN_SZER, MAX_SZER), wys: ogran(+x.wys || 520, MIN_WYS, MAX_WYS), aktywna: el.includes(x.aktywna) ? x.aktywna : el[0], elementy: el });
      }
      wezly.forEach((el) => magazyn.appendChild(el));   // elementy stałe wracają do magazynu, zanim zniknie stary układ
      s.dom.forEach((d) => d.el.remove()); s.dom.clear();
      s.panele = panele;
      s.licznik = Math.max(s.licznik, ...panele.map((p) => parseInt(String(p.id).replace(/\D/g, ""), 10) || 0));
      for (const p of panele) { pr.appendChild(budujPanel(p)); karty(p); aktywuj(p, p.aktywna, true); }
      pusty();
    }

    function ukladDomyslny() {
      return { panele: (o.ukladDomyslny || []).map(([el, szer, wys]) => { const ids = [].concat(el); return { id: nowyId(), szer, wys, aktywna: ids[0], elementy: ids }; }) };
    }

    function domyslny() {
      if (s.panele.length && !window.confirm(napisy.potwierdzDomyslny)) return;
      stosuj(ukladDomyslny());
      zapisz();
    }

    function wyczysc() {
      if (!s.panele.length || !window.confirm("Zamknąć wszystkie okna?")) return;
      stosuj({ panele: [] });
      zapisz();
    }

    // Start: najpierw podręczna kopia (od razu), potem zapis z repozytorium, jeśli jest nowszy.
    // Bez żadnego zapisu karta pokazuje pusty ekran albo swój układ domyślny (opcja `start`).
    function przywroc() {
      let lok = null;
      try { lok = JSON.parse(localStorage.getItem(o.cache) || "null"); } catch (e) { /* brak kopii */ }
      if (lok) { s.zmieniono = lok.zmieniono || 0; stosuj(lok); } else if (o.start === "domyslny") stosuj(ukladDomyslny()); else pusty();
      if (typeof USTAW !== "undefined" && USTAW.dostepne()) {
        USTAW.wczytaj(o.klucz, null).then(({ wartosc }) => {
          if (!wartosc || s.lokalnie || !(wartosc.zmieniono > s.zmieniono)) return;
          s.zmieniono = wartosc.zmieniono; stosuj(wartosc);
          try { localStorage.setItem(o.cache, JSON.stringify(wartosc)); } catch (e) { /* tryb prywatny */ }
        }).catch(() => {});
      }
    }

    // --- zdarzenia -------------------------------------------------------------------------------------
    const panel = (el) => { const sk = el.closest(".prz-panel"); return sk && s.panele.find((x) => x.id === sk.dataset.panel); };
    korzen.querySelector('[data-prz="dodaj"]').addEventListener("click", (e) => menu(e.currentTarget, wolne(), (id) => dodajPanel(id)));
    korzen.querySelector('[data-prz="domyslny"]').addEventListener("click", domyslny);
    korzen.querySelector('[data-prz="wyczysc"]').addEventListener("click", wyczysc);
    pr.addEventListener("click", (e) => {
      const sz = e.target.closest("[data-dodaj]");
      if (sz && pr.contains(sz) && !sz.closest(".prz-panel")) { dodajPanel(sz.dataset.dodaj); return; }
      const p = panel(e.target); if (!p) return;
      if (!e.target.closest(".prz-panel-gora")) return;   // kliknięcia w treść elementu obsługuje karta
      const zam = e.target.closest("[data-zamknij]");
      if (zam) { e.stopPropagation(); usun(p, zam.dataset.zamknij); return; }
      const tab = e.target.closest(".prz-tab");
      if (tab) { aktywuj(p, tab.dataset.el); zapisz(); return; }
      const ak = e.target.closest("[data-akcja]");
      if (ak && ak.dataset.akcja === "plus") menu(ak, wolne(), (id) => dodajZakladke(p, id));
      else if (ak && ak.dataset.akcja === "osobno") osobno(p);
    });
    pr.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const p = panel(e.target); if (!p) return;
      const u = e.target.closest("[data-uchwyt]");
      if (u && u.parentElement === s.dom.get(p.id).el) { rozmiarPrzeciagnij(e, p, u.dataset.uchwyt); return; }
      if (e.target.classList.contains("prz-panel-gora") || e.target.classList.contains("prz-karty")) kolejnoscPrzeciagnij(e, p);
    });

    return {
      przywroc,
      zamontowane: () => [...s.dom.values()].flatMap((d) => [...d.zamontowane]),
    };
  }

  return { utworz };
})();
