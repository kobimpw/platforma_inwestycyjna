"use strict";

/**
 * Wspólna nawigacja dla wszystkich stron w docs/: wąska szyna ikon po lewej
 * (styl TradingView, zadanie 034). Nazwy stron pokazują się w dymkach, grupa
 * „Social" wysuwa podmenu, a na dole szyny są przyciski: motyw Auto/Dzień/Noc i
 * „Przywróć układ okien" (ten drugi dokłada web/shared/okna.js).
 *
 * Strony leżą na różnej głębokości katalogów (web/index.html,
 * web/stan-rynku/index.html, web/biblioteka/index.html, ...), więc każda strona
 * przed wczytaniem tego skryptu ustawia window.SIDEBAR_ROOT na względną
 * ścieżkę do korzenia docs/ (np. "./" albo "../").
 *
 * Nowa strona dochodzi do nawigacji przez dopisanie jej tutaj (z nazwą ikony z
 * IKONY) — nic więcej nie trzeba zmieniać na pozostałych stronach. Wpis z polem
 * `dzieci` to grupa z podmenu (np. „Social" z Earnings, ETF sektorowe, News i
 * Youtube), bez własnego adresu. Ten skrypt dociąga też web/shared/dymki.js
 * (dymki i schowane opisy), więc tego pliku nie trzeba dopisywać do stron.
 */
// Wersja poglądowa (statyczna migawka dla rekrutera). Inne moduły sprawdzają tę flagę, żeby wyłączyć funkcje, które
// w pełnej platformie zapisują dane w repozytorium przez token GitHub (uwagi do bloków, notatniki).
window.WERSJA_POGLADOWA = true;

const IKONY = {
  dom: '<path d="M4 11l8-7 8 7v9H4z"/><path d="M10 20v-6h4v6"/>',
  celownik: '<circle cx="12" cy="12" r="7"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
  suwaki: '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
  swiece: '<path d="M7 3v18M17 3v18"/><rect x="4.5" y="8" width="5" height="8" rx="1"/><rect x="14.5" y="6" width="5" height="9" rx="1"/>',
  rozmowa: '<path d="M4 5h16v11H10l-4 4v-4H4z"/>',
  kalendarz: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
  kolo: '<circle cx="12" cy="12" r="8"/><path d="M12 4v8h8"/>',
  gazeta: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/>',
  odtwarzaj: '<rect x="3" y="6" width="18" height="12" rx="3"/><path d="M10 9.5v5l4.5-2.5z"/>',
  tarcza: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  wykres: '<path d="M3 17l5-6 4 4 8-10"/><path d="M3 21h18"/>',
  lista: '<path d="M4 6l2 2 3-3M4 14l2 2 3-3M13 7h7M13 15h7"/>',
  dokument: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
  ksiazki: '<path d="M5 4h4v16H5zM11 4h4v16h-4z"/><path d="M17 6l3 1-3.5 13-3-1z"/>',
  slonce: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  ksiezyc: '<path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"/>',
  auto: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 010 16z" fill="currentColor"/>',
  uklad: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 9v12"/>',
  teczka: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2M3 12.5h18"/>',
  // kamera: karta „Studio” (zadanie 042)
  kamera: '<rect x="3" y="7" width="12" height="10" rx="2"/><path d="M15 10.5l6-3.5v10l-6-3.5z"/>',
  // barometr: półokrąg skali ze wskazówką (karta „Stan rynku", zadanie 037)
  barometr: '<path d="M3.5 17a8.5 8.5 0 0117 0"/><path d="M12 17l4.5-5.5"/><circle cx="12" cy="17" r="1.4"/><path d="M6 12.5l1.2.9M12 8.5v1.4M18 12.5l-1.2.9"/>',
};

const STRONY = [
  { href: "", etykieta: "Start", ikona: "dom" },
  // Statystyczny stan rynku: makro, rynek i technika w jednym sygnale (zadanie 037).
  { href: "stan-rynku/", etykieta: "Stan rynku", ikona: "barometr" },
  { href: "biblioteka/", etykieta: "Biblioteka", ikona: "ksiazki" },
];

// Motyw Auto / Dzień / Noc. Wybór jest cechą URZĄDZENIA i chwili (telefon na
// słońcu vs laptop nocą), nie ustawieniem do synchronizacji między urządzeniami
// — dlatego świadomie zostaje w localStorage (wyjątek od reguły z CLAUDE.md,
// sekcja "Ustawienia użytkownika"). Brak wyboru = zgodnie z ustawieniem systemu.
const KLUCZ_MOTYWU = "motyw";
const MOTYWY = [
  { wartosc: "auto", etykieta: "Auto", ikona: "auto", opis: "zgodnie z ustawieniem systemu" },
  { wartosc: "dzien", etykieta: "Dzień", ikona: "slonce", opis: "jasny, do czytania na słońcu" },
  { wartosc: "noc", etykieta: "Noc", ikona: "ksiezyc", opis: "ciemny, oszczędza oczy po ciemku" },
];

function svgIkony(nazwa) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${IKONY[nazwa] || ""}</svg>`;
}

function odczytajMotyw() {
  try {
    const m = localStorage.getItem(KLUCZ_MOTYWU);
    return MOTYWY.some((x) => x.wartosc === m) ? m : "auto";
  } catch (e) {
    return "auto";
  }
}

function zastosujMotyw(motyw) {
  if (motyw === "auto") document.documentElement.removeAttribute("data-motyw");
  else document.documentElement.setAttribute("data-motyw", motyw);
}

// Jeden przycisk, który po kliknięciu przechodzi Auto -> Dzień -> Noc -> Auto.
function zbudujPrzelacznikMotywu() {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "sidebar-ikona sidebar-motyw-przycisk";
  const odswiez = (aktywny) => {
    const m = MOTYWY.find((x) => x.wartosc === aktywny) || MOTYWY[0];
    b.innerHTML = svgIkony(m.ikona);
    b.dataset.motyw = m.wartosc;
    b.dataset.dymek = `Motyw: ${m.etykieta} (${m.opis})\nKliknij, aby zmienić`;
    b.setAttribute("aria-label", `Motyw: ${m.etykieta}`);
  };
  b.addEventListener("click", () => {
    const obecny = MOTYWY.findIndex((x) => x.wartosc === b.dataset.motyw);
    const nastepny = MOTYWY[(obecny + 1) % MOTYWY.length].wartosc;
    try {
      localStorage.setItem(KLUCZ_MOTYWU, nastepny);
    } catch (e) {
      /* tryb prywatny — motyw działa do końca wizyty */
    }
    zastosujMotyw(nastepny);
    odswiez(nastepny);
    b.dispatchEvent(new CustomEvent("motyw-zmieniony", { bubbles: true, detail: nastepny }));
    // Wykresy Lightweight Charts dostają kolory przy tworzeniu i nie przemalują się same,
    // więc strona z takim wykresem odświeża się po zmianie motywu (ustawienia są w repozytorium).
    if (document.querySelector(".tv-lightweight-charts")) setTimeout(() => location.reload(), 150);
  });
  odswiez(odczytajMotyw());
  return b;
}

function zbudujSidebar() {
  zastosujMotyw(odczytajMotyw());
  const root = window.SIDEBAR_ROOT || "./";
  const biezacaSciezka = window.location.pathname.replace(/index\.html$/, "");

  const nav = document.createElement("nav");
  nav.className = "sidebar";
  nav.setAttribute("aria-label", "Nawigacja");

  const logo = document.createElement("a");
  logo.className = "sidebar-logo";
  logo.href = root;
  logo.textContent = "p";
  logo.dataset.dymek = "Platforma inwestycyjna (wersja poglądowa)";
  logo.setAttribute("aria-label", "Platforma inwestycyjna, strona startowa");
  nav.appendChild(logo);

  const lista = document.createElement("ul");
  lista.className = "sidebar-glowne";
  const czyAktywna = (href) =>
    new URL(root + href, window.location.href).pathname.replace(/index\.html$/, "") === biezacaSciezka;
  const zbudujLink = ({ href, etykieta, ikona }, wPodmenu) => {
    const a = document.createElement("a");
    a.href = root + href;
    a.className = wPodmenu ? "" : "sidebar-ikona";
    a.innerHTML = svgIkony(ikona) + (wPodmenu ? `<span>${etykieta}</span>` : "");
    if (!wPodmenu) a.dataset.dymek = etykieta;
    a.setAttribute("aria-label", etykieta);
    if (czyAktywna(href)) a.classList.add("aktywna");
    return a;
  };
  const zamknijGrupy = (poza) => {
    for (const g of nav.querySelectorAll(".sidebar-grupa-wiersz.otwarta")) {
      if (g !== poza) g.classList.remove("otwarta");
    }
  };
  for (const strona of STRONY) {
    const li = document.createElement("li");
    if (!strona.dzieci) {
      li.appendChild(zbudujLink(strona, false));
      lista.appendChild(li);
      continue;
    }
    // grupa z podmenu: otwiera się po najechaniu, fokusie albo kliknięciu
    li.className = "sidebar-grupa-wiersz";
    const przycisk = document.createElement("button");
    przycisk.type = "button";
    przycisk.className = "sidebar-ikona";
    przycisk.innerHTML = svgIkony(strona.ikona);
    przycisk.setAttribute("aria-haspopup", "true");
    przycisk.setAttribute("aria-label", strona.etykieta);
    if (strona.dzieci.some((d) => czyAktywna(d.href))) przycisk.classList.add("aktywna");
    const podmenu = document.createElement("div");
    podmenu.className = "sidebar-podmenu";
    for (const dziecko of strona.dzieci) podmenu.appendChild(zbudujLink(dziecko, true));
    li.append(przycisk, podmenu);
    let zegar = null;
    const otworz = () => {
      clearTimeout(zegar);
      zamknijGrupy(li);
      li.classList.add("otwarta");
    };
    const zamknijZOpoznieniem = () => {
      clearTimeout(zegar);
      zegar = setTimeout(() => li.classList.remove("otwarta"), 180);
    };
    przycisk.addEventListener("click", () => (li.classList.contains("otwarta") ? li.classList.remove("otwarta") : otworz()));
    li.addEventListener("pointerenter", (e) => e.pointerType === "mouse" && otworz());
    li.addEventListener("pointerleave", (e) => e.pointerType === "mouse" && zamknijZOpoznieniem());
    // fokus z klawiatury otwiera podmenu; fokus po kliknięciu nie (kliknięcie samo przełącza)
    li.addEventListener("focusin", (e) => e.target.matches(":focus-visible") && otworz());
    li.addEventListener("focusout", (e) => {
      if (!li.contains(e.relatedTarget)) zamknijZOpoznieniem();
    });
    lista.appendChild(li);
  }
  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".sidebar-grupa-wiersz")) zamknijGrupy(null);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") zamknijGrupy(null);
  });
  nav.appendChild(lista);

  // Dół szyny: motyw i (dokładany przez okna.js) przycisk „Przywróć układ okien".
  const dol = document.createElement("div");
  dol.className = "sidebar-dol";
  dol.appendChild(zbudujPrzelacznikMotywu());
  nav.appendChild(dol);

  document.body.classList.add("ma-sidebar");
  document.body.insertBefore(nav, document.body.firstChild);
}

// Stały pasek „Wersja poglądowa": przypomina na każdej podstronie, że to statyczna migawka dla rekrutera, a nie pełna
// platforma. Na stronie startowej (body.start) go nie ma, bo cała jej góra mówi to samo.
function dodajBanerPogladowy() {
  if (document.body.classList.contains("start")) return;
  const a = document.createElement("a");
  a.className = "baner-pogladowy";
  a.href = (window.SIDEBAR_ROOT || "./") + "#o-wersji";
  a.dataset.dymek = "To statyczna wersja poglądowa, a nie pełna platforma: dane są zamrożone, nie ma odświeżania na żywo ani zapisu ustawień w repozytorium. Kliknij, żeby przeczytać więcej.";
  a.innerHTML = "<strong>Wersja poglądowa</strong><span>statyczna migawka, nie pełna platforma</span>";
  document.body.appendChild(a);
}

// Dymki i schowane opisy (web/shared/dymki.js) ładują się z tego samego katalogu.
function dociagnijDymki() {
  const biezacy = document.currentScript ? document.currentScript.src : "";
  const src = biezacy ? biezacy.replace(/sidebar\.js(\?.*)?$/, "dymki.js") : (window.SIDEBAR_ROOT || "./") + "shared/dymki.js";
  if (document.querySelector(`script[src$="shared/dymki.js"]`)) return;
  const s = document.createElement("script");
  s.src = src;
  document.head.appendChild(s);
}

zbudujSidebar();
dodajBanerPogladowy();
dociagnijDymki();
