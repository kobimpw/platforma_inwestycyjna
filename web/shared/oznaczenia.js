"use strict";

/**
 * Numeruje główne bloki wizualne strony (w lewym górnym rogu każdego), żeby
 * dało się w rozmowie jednoznacznie wskazać, o który element chodzi przy
 * zmianach wyglądu — patrz CLAUDE.md, sekcja "Karty: wzorzec jednoplikowy".
 *
 * Blokiem jest każde bezpośrednie dziecko <main> (karta, luźny div z
 * przyciskami, opakowanie nagłówka...), w kolejności odczytu strony od góry.
 * Warstwy układu, które tylko rozkładają kilka kart obok siebie w kolumnach
 * (np. dwie karty w rzędzie), są "przezroczyste" — numerowane są karty w
 * środku, nie sama warstwa układu. Ukryte bloki (atrybut hidden, np. okno
 * modalne ze wzorami) nie dostają numeru.
 *
 * Drugi zestaw oznaczeń (w PRAWYM górnym rogu, litery) dotyczy spraw
 * większych niż jeden element: A, B, C… przy warstwach układu (kilka bloków
 * obok siebie) i jedno oznaczenie "S" przy całej stronie — na uwagi typu
 * "dodaj wykres na samej górze" albo "zmień układ". Miejsce wstawienia
 * (góra strony, między blokami N i N+1, dół) wybiera się w dymku oznaczenia
 * "S", żeby nie wstawiać do strony dodatkowych elementów, które mogłyby
 * rozjechać układ.
 *
 * Klik w dowolne oznaczenie otwiera dymek z uwagami przypiętymi do tego
 * miejsca (zapisanymi w repo przez web/shared/projekty.js) i polem do
 * dodania nowej. Pełna karta zadania istnieje tylko w pełnej platformie.
 */
(function () {
const OZNACZENIA_SKRYPT = document.currentScript ? document.currentScript.src : "";

function jestWarstwaUkladu(el) {
  if (el.classList.contains("karta")) return false;
  const dzieci = Array.from(el.children).filter(
    (d) => d.tagName !== "SCRIPT" && d.tagName !== "STYLE"
  );
  if (dzieci.length === 0) return false;
  return dzieci.every(
    (d) => d.classList.contains("karta") || d.querySelector(":scope > .karta")
  );
}

// Zwraca { bloki: [element…], warstwy: [element…] } — warstwy to kontenery
// układu (kilka kart obok siebie), które dostają litery.
function zbierzBlokiDoOznaczenia(main) {
  const bloki = [];
  const warstwy = [];
  for (const dziecko of Array.from(main.children)) {
    if (dziecko.tagName === "SCRIPT" || dziecko.tagName === "STYLE") continue;
    if (dziecko.hidden) continue;
    if (jestWarstwaUkladu(dziecko)) {
      warstwy.push(dziecko);
      for (const wnuk of Array.from(dziecko.children)) {
        const karta = wnuk.classList.contains("karta")
          ? wnuk
          : wnuk.querySelector(":scope > .karta");
        bloki.push(karta || wnuk);
      }
    } else {
      bloki.push(dziecko);
    }
  }
  return { bloki, warstwy };
}

// ---------------------------------------------------------------------------
// Rozpoznanie karty (do przypinania uwag): katalog strony w docs/.
// ---------------------------------------------------------------------------
const OZNACZENIA_KARTY = [
  "biblioteka", "pozycja", "stan-rynku", "VaR",
];

function rozpoznajKarte() {
  const segmenty = window.location.pathname.split("/").filter(Boolean);
  const znaleziona = OZNACZENIA_KARTY.find((k) => segmenty.includes(k));
  return znaleziona || "start";
}

function etykietaBloku(blok) {
  const naglowek = blok.querySelector("h1, h2, h3");
  const tekst = (naglowek ? naglowek.textContent : blok.textContent) || "";
  return tekst.replace(/\s+/g, " ").trim().slice(0, 50);
}

// ---------------------------------------------------------------------------
// Dymek z uwagami.
// ---------------------------------------------------------------------------
function tworz(tag, klasa, tekst) {
  const el = document.createElement(tag);
  if (klasa) el.className = klasa;
  if (tekst !== undefined) el.textContent = tekst;
  return el;
}

let aktywnyDymek = null;

function zamknijDymek() {
  if (aktywnyDymek) aktywnyDymek.remove();
  aktywnyDymek = null;
}

function ustawPolozenieDymka(dymek, kotwica, szeroki) {
  const r = kotwica.getBoundingClientRect();
  const szer = Math.min(szeroki ? 780 : 340, window.innerWidth - 16);
  dymek.style.width = `${szer}px`;
  const lewo = Math.max(8, Math.min(r.left, window.innerWidth - szer - 8));
  dymek.style.left = `${lewo}px`;
  dymek.style.top = `${Math.min(r.bottom + 8, window.innerHeight - 120)}px`;
}

function priorytetEtykieta(p) {
  return ["", "niski", "średni", "wysoki"][p] || "";
}

// ---------------------------------------------------------------------------
// Zakładka „Kod” — fragmenty kodu tworzące dany blok, z mapy zbudowanej przez
// src/narzedzia/mapa_kodu.py (web/shared/mapa-kodu.json). To automatyczne
// przybliżenie (dopasowanie nazw), nie analiza programu.
// ---------------------------------------------------------------------------
let mapaKoduObietnica = null;

function wczytajMapeKodu() {
  if (!mapaKoduObietnica) {
    const adres = OZNACZENIA_SKRYPT.replace(/oznaczenia\.js(\?.*)?$/, "mapa-kodu.json");
    mapaKoduObietnica = fetch(adres, { cache: "no-store" }).then((odpowiedz) => {
      if (!odpowiedz.ok) throw new Error(`Brak pliku mapy kodu (${odpowiedz.status}), uruchom: python src/narzedzia/mapa_kodu.py`);
      return odpowiedz.json();
    });
    mapaKoduObietnica.catch(() => {
      mapaKoduObietnica = null;
    });
  }
  return mapaKoduObietnica;
}

const POZIOMY_JS = ["sięga po elementy bloku", "wywoływane przez nie", "wywoływane dalej"];

function opisMiejsca(seg) {
  const zakres = `linie ${seg.od}–${seg.do}`;
  if (seg.zrodlo) {
    return [
      `✎ Edytuj tutaj: ${seg.zrodlo.plik} · linie ${seg.zrodlo.od}–${seg.zrodlo.do} · stała ${seg.zrodlo.nazwa}`,
      `(wygenerowane w ${seg.plik} · ${zakres}, nie edytuj tego pliku ręcznie)`,
    ];
  }
  return [`${seg.plik} · ${zakres}`];
}

function narysujSegment(seg, otwarty) {
  const szczegoly = tworz("details", "pu-kod-segment");
  szczegoly.open = otwarty;
  const naglowek = tworz("summary");
  naglowek.appendChild(tworz("span", `pu-plakietka pu-rola-${seg.rola.toLowerCase()}`, seg.rola));
  naglowek.appendChild(tworz("span", "pu-kod-nazwa", seg.nazwa));
  naglowek.appendChild(tworz("span", "pu-kod-linie", `${seg.od}–${seg.do}`));
  szczegoly.appendChild(naglowek);
  const opis = opisMiejsca(seg);
  const meta = tworz("div", "pu-kod-meta");
  opis.forEach((linia, i) => meta.appendChild(tworz("div", i === 0 && seg.zrodlo ? "pu-kod-edytuj" : "", linia)));
  if (seg.rola === "JS") meta.appendChild(tworz("div", "", `Powiązanie: ${POZIOMY_JS[seg.poziom] || POZIOMY_JS[2]}`));
  szczegoly.appendChild(meta);
  const pre = tworz("pre");
  pre.appendChild(tworz("code", "", seg.kod + (seg.pominieto ? `\n… pominięto ${seg.pominieto} linii (ciąg dalszy w pliku) …` : "")));
  szczegoly.appendChild(pre);
  return szczegoly;
}

function narysujKod(kontener, mapa, opcje) {
  const karta = mapa.karty[opcje.karta];
  if (!karta) {
    kontener.replaceChildren(tworz("p", "pu-dymek-info pu-blad", "Ta karta nie jest w mapie kodu, przebuduj: python src/narzedzia/mapa_kodu.py"));
    return;
  }
  const elementy = [];
  elementy.push(tworz("p", "pu-dymek-info", "Automatyczne przybliżenie (dopasowanie nazw, nie analiza programu). Kliknij fragment, żeby zobaczyć kod."));

  let segmenty = [];
  if (opcje.kod.typ === "blok") {
    const blok = karta.bloki[opcje.kod.cel];
    if (!blok) {
      kontener.replaceChildren(tworz("p", "pu-dymek-info pu-blad", "Brak wpisu dla tego bloku, mapa kodu jest nieaktualna, przebuduj: python src/narzedzia/mapa_kodu.py"));
      return;
    }
    segmenty = blok.segmenty;
  } else if (opcje.kod.typ === "grupa") {
    const numery = karta.grupy[opcje.kod.cel] || [];
    const widziane = new Set();
    for (const numer of numery) {
      for (const seg of (karta.bloki[numer] || { segmenty: [] }).segmenty) {
        const klucz = `${seg.rola}|${seg.plik}|${seg.od}|${seg.do}`;
        if (!widziane.has(klucz)) {
          widziane.add(klucz);
          segmenty.push(seg);
        }
      }
    }
    elementy.push(tworz("p", "pu-dymek-info", `Grupa obejmuje bloki: ${numery.join(", ") || "—"}.`));
  }

  if (opcje.kod.typ === "strona") {
    elementy.push(tworz("p", "pu-dymek-info", "Cała strona: poniżej pliki, z których się składa."));
    if (karta.generuj) {
      elementy.push(tworz("p", "pu-kod-edytuj", `Składanie strony (generuj): ${karta.generuj.plik} · linie ${karta.generuj.od}–${karta.generuj.do}`));
    }
  } else {
    const kolejnosc = { HTML: 0, JS: 1, CSS: 2 };
    segmenty = segmenty.slice().sort((a, b) => kolejnosc[a.rola] - kolejnosc[b.rola] || a.plik.localeCompare(b.plik) || a.od - b.od);
    let poprzedni = null;
    let licznikJs = 0;
    for (const seg of segmenty) {
      if (poprzedni && poprzedni.plik === seg.plik && poprzedni.rola === seg.rola && seg.od - poprzedni.do > 1) {
        elementy.push(tworz("div", "pu-kod-przerwa", `… przerwa w kodzie: ${seg.od - poprzedni.do - 1} linii …`));
      }
      const otwarty = seg.rola === "HTML" || (seg.rola === "JS" && seg.poziom === 0 && licznikJs++ < 2);
      elementy.push(narysujSegment(seg, otwarty));
      poprzedni = seg;
    }
  }

  const pliki = tworz("details", "pu-kod-pliki");
  pliki.appendChild(tworz("summary", "", `Pliki tej karty (${karta.pliki.length})`));
  for (const plik of karta.pliki) {
    pliki.appendChild(tworz("div", "pu-kod-plik", `${plik.sciezka}: ${plik.rola} (${plik.linii} linii)`));
  }
  pliki.open = opcje.kod.typ === "strona";
  elementy.push(pliki);
  kontener.replaceChildren(...elementy);
}

// opcje: { kotwica, tytul, karta, kod: { typ: "blok"|"grupa"|"strona", cel },
//          pasuje(zadanie), nowyZakres(miejsce) -> zakres, miejsca: [...] | null }
async function otworzDymek(opcje) {
  zamknijDymek();
  const dymek = tworz("div", "pu-dymek");
  dymek.setAttribute("role", "dialog");
  const gora = tworz("div", "pu-dymek-gora");
  gora.appendChild(tworz("strong", "", opcje.tytul));
  const zamknij = tworz("button", "przycisk-usun", "×");
  zamknij.type = "button";
  zamknij.title = "Zamknij";
  zamknij.addEventListener("click", zamknijDymek);
  gora.appendChild(zamknij);
  dymek.appendChild(gora);

  const zakladki = tworz("div", "pu-zakladki");
  const przyciskUwagi = tworz("button", "pu-zakladka pu-zakladka-aktywna", "Uwagi");
  const przyciskNotatnika = tworz("button", "pu-zakladka", "Notatnik");
  const przyciskKodu = tworz("button", "pu-zakladka", "Kod");
  for (const p of [przyciskUwagi, przyciskNotatnika, przyciskKodu]) p.type = "button";
  zakladki.append(przyciskUwagi, przyciskNotatnika, przyciskKodu);
  // Wersja poglądowa: uwagi i notatniki zapisują się w repozytorium przez token GitHub, więc zostaje tylko podgląd kodu bloku.
  if (window.WERSJA_POGLADOWA) { przyciskUwagi.style.display = "none"; przyciskNotatnika.style.display = "none"; }
  dymek.appendChild(zakladki);

  const tresc = tworz("div", "pu-dymek-tresc");
  dymek.appendChild(tresc);
  document.body.appendChild(dymek);
  ustawPolozenieDymka(dymek, opcje.kotwica, false);
  aktywnyDymek = dymek;

  const root = window.SIDEBAR_ROOT || "./";

  const odswiezUwagi = async () => {
    tresc.replaceChildren(tworz("p", "pu-dymek-info", "Wczytywanie…"));
    if (!window.PR) {
      tresc.replaceChildren(tworz("p", "pu-dymek-info", "Moduł zapisu uwag jeszcze się wczytuje, spróbuj za chwilę."));
      return;
    }
    if (!PR.token()) {
      pokazFormularzTokenu(tresc, odswiezUwagi);
      return;
    }
    let zadania;
    try {
      const { indeks } = await PR.wczytajIndeks();
      // zrobione zadania znikają z dymka (zostają na liście w „Projekty i uwagi")
      zadania = indeks.zadania.filter((z) => z.typ !== "notatnik" && z.status !== "zrobione" && opcje.pasuje(z));
    } catch (e) {
      tresc.replaceChildren(tworz("p", "pu-dymek-info pu-blad", e.message));
      return;
    }
    zadania.sort((a, b) => (a.status === "zrobione") - (b.status === "zrobione") || b.priorytet - a.priorytet);

    const zawartosc = [];
    if (zadania.length === 0) zawartosc.push(tworz("p", "pu-dymek-info", "Brak uwag przypiętych do tego miejsca."));
    for (const z of zadania) {
      const wiersz = tworz("div", "pu-dymek-wiersz" + (z.status === "zrobione" ? " pu-zrobione" : ""));
      const nazwa = tworz("span", "pu-dymek-nazwa", z.tytul);
      if (z.typ === "projekt") wiersz.appendChild(tworz("span", "pu-plakietka pu-typ-projekt", "PROJEKT"));
      wiersz.appendChild(nazwa);
      if (z.zakres && z.zakres.typ === "miejsce") wiersz.appendChild(tworz("span", "pu-plakietka", z.zakres.etykieta || z.zakres.cel));
      if (z.priorytet > 0) wiersz.appendChild(tworz("span", `pu-plakietka pu-prio-${z.priorytet}`, priorytetEtykieta(z.priorytet)));
      if (z.typ !== "zadanie" && z.podzadania && z.podzadania.razem) wiersz.appendChild(tworz("span", "pu-plakietka", `${z.podzadania.gotowe}/${z.podzadania.razem}`));
      // Opis zadania bez wchodzenia w jego kartę (zadanie 043): ▸ rozwija pole do podglądu i edycji.
      const opis = tworz("button", "pu-dymek-opis", "▸");
      opis.type = "button";
      opis.title = "Pokaż i edytuj opis";
      let edytor = null;
      opis.addEventListener("click", () => {
        if (!edytor) {
          edytor = PR.edytorOpisu({ id: z.id });
          edytor.classList.add("pu-opis-w-dymku");
          wiersz.after(edytor);
        }
        const widoczny = edytor.hidden;
        edytor.hidden = !widoczny;
        opis.textContent = widoczny ? "▾" : "▸";
        if (widoczny) edytor.wczytaj();
      });
      wiersz.prepend(opis);
      const otworz = tworz("a", "pu-dymek-otworz", "⤢");
      otworz.href = `${root}projekty-i-uwagi/zadanie.html?id=${encodeURIComponent(z.id)}`;
      otworz.title = "Otwórz kartę zadania";
      wiersz.appendChild(otworz);
      const usun = tworz("button", "przycisk-usun", "×");
      usun.type = "button";
      usun.title = "Usuń zadanie na stałe";
      usun.addEventListener("click", async () => {
        if (!confirm(`Usunąć zadanie „${z.tytul}" na stałe?`)) return;
        usun.disabled = true;
        try {
          await PR.usunProjekt(z.id);
          await odswiezUwagi();
        } catch (blad) {
          usun.disabled = false;
          tresc.prepend(tworz("p", "pu-dymek-info pu-blad", blad.message));
        }
      });
      wiersz.appendChild(usun);
      zawartosc.push(wiersz);
    }

    const formularz = tworz("form", "pu-dymek-formularz");
    let wybor = null;
    if (opcje.miejsca) {
      wybor = tworz("select");
      for (const m of opcje.miejsca) {
        const o = tworz("option", "", m.etykieta);
        o.value = m.wartosc;
        wybor.appendChild(o);
      }
      formularz.appendChild(wybor);
    }
    const pole = tworz("input");
    pole.type = "text";
    pole.placeholder = "Nowa uwaga…";
    const przycisk = tworz("button", "", "Dodaj");
    przycisk.type = "submit";
    const status = tworz("p", "pu-dymek-info");
    formularz.append(pole, przycisk);
    formularz.addEventListener("submit", async (e) => {
      e.preventDefault();
      const tytul = pole.value.trim();
      if (!tytul) return;
      przycisk.disabled = true;
      status.textContent = "Zapisywanie w repozytorium…";
      try {
        const zakres = opcje.nowyZakres(wybor ? wybor.value : null);
        // Domyślna sekcja = karta, na której zadanie powstaje (zadanie 015); sekcję
        // można potem zmienić ręcznie na karcie zadania.
        await PR.nowyProjekt({ tytul, zakres, sekcja: PR.nazwaKarty(zakres.karta) });
        await odswiezUwagi();
      } catch (blad) {
        status.textContent = blad.message;
        status.classList.add("pu-blad");
        przycisk.disabled = false;
      }
    });
    zawartosc.push(formularz, status);
    tresc.replaceChildren(...zawartosc);
    if (!opcje.miejsca) pole.focus();
  };

  // Notatnik całej karty (jeden na kartę), ten sam we wszystkich dymkach tej karty.
  const pokazNotatnik = async () => {
    tresc.replaceChildren(tworz("p", "pu-dymek-info", "Wczytywanie…"));
    if (!window.PR) {
      tresc.replaceChildren(tworz("p", "pu-dymek-info", "Moduł zapisu jeszcze się wczytuje, spróbuj za chwilę."));
      return;
    }
    if (!PR.token()) {
      pokazFormularzTokenu(tresc, pokazNotatnik);
      return;
    }
    const edytor = PR.edytorOpisu({
      znajdzId: () => PR.notatnikKarty(opcje.karta, false),
      zapewnijId: () => PR.notatnikKarty(opcje.karta, true),
    });
    edytor.classList.add("pu-opis-w-dymku");
    const otworz = tworz("button", "", "Otwórz pełny notatnik ⤢");
    otworz.type = "button";
    otworz.title = "Podzadania, pliki, Docs i arkusze w pełnej karcie notatnika";
    otworz.addEventListener("click", async () => {
      otworz.disabled = true;
      try {
        const id = await PR.notatnikKarty(opcje.karta, true);
        window.location.href = `${root}projekty-i-uwagi/zadanie.html?id=${encodeURIComponent(id)}`;
      } catch (blad) {
        otworz.disabled = false;
        tresc.prepend(tworz("p", "pu-dymek-info pu-blad", blad.message));
      }
    });
    tresc.replaceChildren(tworz("p", "pu-dymek-info", `Notatnik karty: ${PR.nazwaKarty(opcje.karta) || opcje.karta}`), edytor, otworz);
    await edytor.wczytaj();
  };

  const pokazKod = async () => {
    tresc.replaceChildren(tworz("p", "pu-dymek-info", "Wczytywanie mapy kodu…"));
    try {
      narysujKod(tresc, await wczytajMapeKodu(), opcje);
    } catch (e) {
      tresc.replaceChildren(tworz("p", "pu-dymek-info pu-blad", e.message));
    }
  };

  const przelacz = (tryb) => {
    przyciskUwagi.classList.toggle("pu-zakladka-aktywna", tryb === "uwagi");
    przyciskNotatnika.classList.toggle("pu-zakladka-aktywna", tryb === "notatnik");
    przyciskKodu.classList.toggle("pu-zakladka-aktywna", tryb === "kod");
    ustawPolozenieDymka(dymek, opcje.kotwica, tryb === "kod");
    return tryb === "kod" ? pokazKod() : tryb === "notatnik" ? pokazNotatnik() : odswiezUwagi();
  };
  przyciskUwagi.addEventListener("click", () => przelacz("uwagi"));
  przyciskNotatnika.addEventListener("click", () => przelacz("notatnik"));
  przyciskKodu.addEventListener("click", () => przelacz("kod"));
  await przelacz(window.WERSJA_POGLADOWA ? "kod" : "uwagi");
}

function pokazFormularzTokenu(kontener, poZapisie) {
  const info = tworz(
    "p",
    "pu-dymek-info",
    "Uwagi są zapisane w repozytorium, wklej token GitHub (ten sam co w „Historii zakładów”), żeby je zobaczyć i dodawać. Zostaje tylko w tej przeglądarce."
  );
  const formularz = tworz("form", "pu-dymek-formularz");
  const pole = tworz("input");
  pole.type = "password";
  pole.placeholder = "ghp_…";
  pole.autocomplete = "off";
  const przycisk = tworz("button", "", "Zapamiętaj");
  przycisk.type = "submit";
  formularz.append(pole, przycisk);
  formularz.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!pole.value.trim()) return;
    PR.ustawToken(pole.value.trim());
    poZapisie();
  });
  kontener.replaceChildren(info, formularz);
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") zamknijDymek();
});
document.addEventListener("mousedown", (e) => {
  if (aktywnyDymek && !aktywnyDymek.contains(e.target) && !e.target.closest(".oznaczenie-bloku, .oznaczenie-zakres, .oznaczenie-strony")) {
    zamknijDymek();
  }
});

// ---------------------------------------------------------------------------
// Rysowanie oznaczeń.
// ---------------------------------------------------------------------------
function dodajZnacznik(rodzic, klasa, tekst, tytul, przyKliku) {
  if (getComputedStyle(rodzic).position === "static") {
    rodzic.style.position = "relative";
  }
  const znacznik = document.createElement("span");
  znacznik.className = klasa;
  znacznik.textContent = tekst;
  znacznik.title = tytul;
  znacznik.setAttribute("role", "button");
  znacznik.tabIndex = 0;
  const aktywuj = (e) => {
    e.preventDefault();
    e.stopPropagation();
    przyKliku(znacznik);
  };
  znacznik.addEventListener("click", aktywuj);
  znacznik.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") aktywuj(e);
  });
  rodzic.insertBefore(znacznik, rodzic.firstChild);
}

function oznaczBlokiStrony() {
  const main = document.querySelector("main");
  if (!main) return;
  const karta = rozpoznajKarte();
  const { bloki, warstwy } = zbierzBlokiDoOznaczenia(main);

  bloki.forEach((blok, indeks) => {
    const numer = String(indeks + 1);
    const etykieta = etykietaBloku(blok);
    blok.classList.add("blok-numerowany"); // podświetlenie po najechaniu, patrz style.css
    dodajZnacznik(blok, "oznaczenie-bloku", numer, `Uwagi do bloku ${numer}`, (kotwica) =>
      otworzDymek({
        kotwica,
        karta,
        kod: { typ: "blok", cel: numer },
        tytul: `Blok ${numer}${etykieta ? `: ${etykieta}` : ""}`,
        pasuje: (z) => z.zakres && z.zakres.karta === karta && z.zakres.typ === "blok" && String(z.zakres.cel) === numer,
        nowyZakres: () => ({ karta, typ: "blok", cel: numer, etykieta }),
        miejsca: null,
      })
    );
  });

  warstwy.forEach((warstwa, indeks) => {
    const litera = String.fromCharCode(65 + (indeks % 26));
    dodajZnacznik(warstwa, "oznaczenie-zakres", litera, `Uwagi do grupy bloków ${litera}`, (kotwica) =>
      otworzDymek({
        kotwica,
        karta,
        kod: { typ: "grupa", cel: litera },
        tytul: `Grupa bloków ${litera} (układ kilku bloków obok siebie)`,
        pasuje: (z) => z.zakres && z.zakres.karta === karta && z.zakres.typ === "grupa" && z.zakres.cel === litera,
        nowyZakres: () => ({ karta, typ: "grupa", cel: litera, etykieta: `grupa ${litera}` }),
        miejsca: null,
      })
    );
  });

  const miejsca = [{ wartosc: "strona", etykieta: "Cała strona (układ, ogólne)" }, { wartosc: "gora", etykieta: "Miejsce: góra strony" }];
  for (let i = 1; i < bloki.length; i++) miejsca.push({ wartosc: `${i}-${i + 1}`, etykieta: `Miejsce: między blokiem ${i} a ${i + 1}` });
  miejsca.push({ wartosc: "dol", etykieta: "Miejsce: dół strony" });
  const opisyMiejsc = Object.fromEntries(miejsca.map((m) => [m.wartosc, m.etykieta]));

  dodajZnacznik(main, "oznaczenie-strony", "S", "Uwagi do całej strony i miejsc wstawienia", (kotwica) =>
    otworzDymek({
      kotwica,
      karta,
      kod: { typ: "strona", cel: "" },
      tytul: "Cała strona i miejsca wstawienia",
      pasuje: (z) => z.zakres && z.zakres.karta === karta && (z.zakres.typ === "strona" || z.zakres.typ === "miejsce"),
      nowyZakres: (wartosc) =>
        wartosc === "strona"
          ? { karta, typ: "strona", cel: "", etykieta: "cała strona" }
          : { karta, typ: "miejsce", cel: wartosc, etykieta: opisyMiejsc[wartosc].replace(/^Miejsce: /, "") },
      miejsca,
    })
  );
}

// Moduł zapisu uwag ładuje się sam obok tego skryptu, żeby nie trzeba było
// dopisywać go do każdej karty osobno.
function wczytajModulProjektow() {
  if (window.PR || !OZNACZENIA_SKRYPT) return;
  const skrypt = document.createElement("script");
  skrypt.src = OZNACZENIA_SKRYPT.replace(/oznaczenia\.js(\?.*)?$/, "projekty.js");
  document.head.appendChild(skrypt);
}

function start() {
  wczytajModulProjektow();
  oznaczBlokiStrony();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
})();
