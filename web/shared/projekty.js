"use strict";

/**
 * Wspólny moduł „Projekty i uwagi" — odczyt i zapis zadań/notatek w
 * repozytorium (katalog `projekty/`) przez GitHub Contents API, tym samym
 * tokenem, którego używa „Historia zakładów" na karcie „Zajęcie pozycji"
 * (jeden wpis tokenu w przeglądarce działa dla wszystkich kart).
 *
 * Powód, dla którego dane siedzą w repo, a nie w Cloudflare KV: do repo mam
 * dostęp w każdej sesji Claude Code, do KV nie. Układ katalogu i model
 * danych: specyfikacja karty w pełnej platformie.
 *
 * Wystawia jeden globalny obiekt `PR`. Nic tu nie odpytuje GitHuba samo z
 * siebie — dopiero wywołanie funkcji z `PR`.
 */
(function () {
  const REPO = "kobimpw/platforma_inwestycyjna";
  const GALAZ = "main";
  const KATALOG = "projekty";
  const TOKEN_KLUCZ = "zp_github_token"; // ten sam co w „Historii zakładów"
  const LIMIT_PLIKU_BAJTY = 5_000_000;
  const API = `https://api.github.com/repos/${REPO}/contents/`;
  const SCIEZKA_INDEKSU = `${KATALOG}/indeks.json`;

  // ------------------------------------------------------------------ karty
  // Jedna lista kart strony (adres katalogu w docs/ -> nazwa w menu), w kolejności
  // z paska bocznego (web/shared/sidebar.js — przy nowej karcie dopisz ją w obu
  // miejscach). Nazwa karty to też DOMYŚLNA SEKCJA zadania tworzonego na tej
  // karcie (zadanie 015): „Youtube" → sekcja „Youtube", „News" → „News".
  const KARTY = [
    ["pozycja", "Pozycja"],
    ["stan-rynku", "Stan rynku"],
    ["VaR", "VaR"],
    ["biblioteka", "Biblioteka"],
  ];

  // Czytelna nazwa karty albo "" (brak karty / nieznana) — wtedy zadanie nie dostaje sekcji.
  function nazwaKarty(id) {
    const wpis = KARTY.find((k) => k[0] === id);
    return wpis ? wpis[1] : "";
  }

  // ------------------------------------------------------------------ token
  function token() {
    try {
      return localStorage.getItem(TOKEN_KLUCZ) || "";
    } catch (e) {
      return "";
    }
  }

  function ustawToken(nowy) {
    localStorage.setItem(TOKEN_KLUCZ, nowy);
  }

  function bladBrakTokenu() {
    const e = new Error("Brak tokenu GitHub, wklej i zapisz token, żeby czytać i zapisywać uwagi.");
    e.kod = "brak-tokenu";
    return e;
  }

  // ----------------------------------------------------------- base64 / UTF-8
  function bajtyNaBase64(bajty) {
    let tekst = "";
    const krok = 0x8000;
    for (let i = 0; i < bajty.length; i += krok) {
      tekst += String.fromCharCode.apply(null, bajty.subarray(i, i + krok));
    }
    return btoa(tekst);
  }

  function tekstNaBase64(tekst) {
    return bajtyNaBase64(new TextEncoder().encode(tekst));
  }

  function base64NaTekst(base64) {
    const binarny = atob(base64.replace(/\s/g, ""));
    const bajty = Uint8Array.from(binarny, (znak) => znak.charCodeAt(0));
    return new TextDecoder().decode(bajty);
  }

  // ------------------------------------------------------------ niski poziom
  function naglowki(accept) {
    return {
      Authorization: `Bearer ${token()}`,
      Accept: accept || "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
  }

  function kodujSciezke(sciezka) {
    return sciezka.split("/").map(encodeURIComponent).join("/");
  }

  async function bladOdpowiedzi(odpowiedz, co) {
    let szczegol = "";
    try {
      szczegol = (await odpowiedz.json()).message || "";
    } catch (e) {
      // brak treści JSON — wystarczy sam kod
    }
    const blad = new Error(`GitHub zwrócił błąd ${odpowiedz.status} (${co})${szczegol ? `: ${szczegol}` : ""}`);
    blad.kod = odpowiedz.status;
    return blad;
  }

  // Zwraca { tresc, sha } albo null, gdy pliku nie ma.
  async function odczytaj(sciezka) {
    if (!token()) throw bladBrakTokenu();
    const odpowiedz = await fetch(`${API}${kodujSciezke(sciezka)}?ref=${GALAZ}`, {
      headers: naglowki(),
      cache: "no-store",
    });
    if (odpowiedz.status === 404) return null;
    if (!odpowiedz.ok) throw await bladOdpowiedzi(odpowiedz, `odczyt ${sciezka}`);
    const dane = await odpowiedz.json();
    return { tresc: base64NaTekst(dane.content), sha: dane.sha };
  }

  // Zawartość pliku jako Blob (także duże i binarne) — do pobrania/podglądu.
  async function pobierzPlik(sciezka) {
    if (!token()) throw bladBrakTokenu();
    const odpowiedz = await fetch(`${API}${kodujSciezke(sciezka)}?ref=${GALAZ}`, {
      headers: naglowki("application/vnd.github.raw+json"),
      cache: "no-store",
    });
    if (!odpowiedz.ok) throw await bladOdpowiedzi(odpowiedz, `pobranie ${sciezka}`);
    return odpowiedz.blob();
  }

  // Zapis (PUT). `sha` = sha nadpisywanego pliku (null przy tworzeniu nowego).
  // Zwraca sha nowej wersji. Konflikt (plik zmieniony w międzyczasie) to błąd
  // z `kod` 409 albo 422 — nigdy nie nadpisujemy po cichu.
  async function zapiszBase64(sciezka, base64, sha, komunikat) {
    if (!token()) throw bladBrakTokenu();
    const cialo = { message: komunikat, content: base64, branch: GALAZ };
    if (sha) cialo.sha = sha;
    const odpowiedz = await fetch(`${API}${kodujSciezke(sciezka)}`, {
      method: "PUT",
      headers: { ...naglowki(), "Content-Type": "application/json" },
      body: JSON.stringify(cialo),
    });
    if (!odpowiedz.ok) throw await bladOdpowiedzi(odpowiedz, `zapis ${sciezka}`);
    return (await odpowiedz.json()).content.sha;
  }

  function zapisz(sciezka, tresc, sha, komunikat) {
    return zapiszBase64(sciezka, tekstNaBase64(tresc), sha, komunikat);
  }

  async function usun(sciezka, komunikat) {
    const plik = await odczytaj(sciezka);
    if (!plik) return;
    const odpowiedz = await fetch(`${API}${kodujSciezke(sciezka)}`, {
      method: "DELETE",
      headers: { ...naglowki(), "Content-Type": "application/json" },
      body: JSON.stringify({ message: komunikat, sha: plik.sha, branch: GALAZ }),
    });
    if (!odpowiedz.ok) throw await bladOdpowiedzi(odpowiedz, `usunięcie ${sciezka}`);
  }

  // ----------------------------------------------------------------- pomocnicze
  function noweId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function slug(tekst) {
    const czysty = String(tekst || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/ł/g, "l")
      .replace(/Ł/g, "L")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40)
      .replace(/-+$/, "");
    return czysty || "zadanie";
  }

  function bezpiecznaNazwaPliku(nazwa) {
    return String(nazwa || "plik").replace(/[\\/:*?"<>|]+/g, "").replace(/\s+/g, "-").slice(0, 80) || "plik";
  }

  // ----------------------------------------------------------- indeks zadań
  function pustyIndeks() {
    return { wersja: 1, zadania: [] };
  }

  async function wczytajIndeks() {
    const plik = await odczytaj(SCIEZKA_INDEKSU);
    if (!plik) return { indeks: pustyIndeks(), sha: null };
    let indeks;
    try {
      indeks = JSON.parse(plik.tresc);
    } catch (e) {
      throw new Error("Indeks zadań jest uszkodzony, napraw go (w pełnej platformie robi to przebuduj_indeks.py).");
    }
    if (!indeks || !Array.isArray(indeks.zadania)) indeks = pustyIndeks();
    return { indeks, sha: plik.sha };
  }

  function wpisIndeksu(projekt) {
    const gotowe = projekt.podzadania.filter((p) => p.gotowe).length;
    return {
      id: projekt.id,
      typ: projekt.typ,
      tytul: projekt.tytul,
      priorytet: projekt.priorytet,
      sekcja: projekt.sekcja || "",
      status: projekt.status,
      zakres: projekt.zakres,
      podzadania: { razem: projekt.podzadania.length, gotowe },
      zmieniono: projekt.zmieniono,
    };
  }

  // Odczyt najnowszego indeksu → zmiana → zapis, z ponowieniem przy konflikcie.
  // Zawsze na świeżej kopii, żeby nie nadpisać wpisu dodanego z innego urządzenia.
  async function zmienIndeks(mutuj, komunikat) {
    for (let proba = 0; proba < 4; proba++) {
      const { indeks, sha } = await wczytajIndeks();
      const nowy = mutuj(indeks) || indeks;
      try {
        await zapisz(SCIEZKA_INDEKSU, JSON.stringify(nowy, null, 2) + "\n", sha, komunikat);
        return nowy;
      } catch (e) {
        if (e.kod !== 409 && e.kod !== 422) throw e;
      }
    }
    throw new Error("Nie udało się zapisać indeksu zadań (konflikt), spróbuj ponownie.");
  }

  function wstawDoIndeksu(indeks, projekt) {
    const wpis = wpisIndeksu(projekt);
    const i = indeks.zadania.findIndex((z) => z.id === projekt.id);
    if (i === -1) indeks.zadania.push(wpis);
    else indeks.zadania[i] = wpis;
    return indeks;
  }

  // ----------------------------------------------------------------- projekt
  const sciezkaProjektu = (id) => `${KATALOG}/${id}/projekt.json`;
  const sciezkaOpisu = (id) => `${KATALOG}/${id}/opis.md`;
  const sciezkaPliku = (id, nazwa) => `${KATALOG}/${id}/pliki/${nazwa}`;

  function normalizujProjekt(p) {
    p.tytul = p.tytul || "Bez tytułu";
    // wpisy sprzed pola „typ" to zadania; „notatnik" to jeden wpis na kartę (zadanie 043)
    p.typ = p.typ === "projekt" || p.typ === "notatnik" ? p.typ : "zadanie";
    p.priorytet = Number(p.priorytet) || 0;
    p.sekcja = p.sekcja || "";
    p.status = p.status === "zrobione" ? "zrobione" : "otwarte";
    p.zakres = p.zakres && p.zakres.karta ? p.zakres : { karta: "", typ: "ogolne", cel: "" };
    p.podzadania = Array.isArray(p.podzadania) ? p.podzadania : [];
    p.materialy = Array.isArray(p.materialy) ? p.materialy : [];
    p.dziennik = Array.isArray(p.dziennik) ? p.dziennik : [];
    return p;
  }

  // Zwraca „stan": { projekt, opis, shaProjektu, shaOpisu } albo null.
  async function wczytajProjekt(id) {
    const plik = await odczytaj(sciezkaProjektu(id));
    if (!plik) return null;
    const opis = await odczytaj(sciezkaOpisu(id));
    return {
      projekt: normalizujProjekt(JSON.parse(plik.tresc)),
      opis: opis ? opis.tresc : "",
      shaProjektu: plik.sha,
      shaOpisu: opis ? opis.sha : null,
    };
  }

  // Zapisy idą jeden po drugim — dwa równoległe PUT na ten sam plik z tym samym
  // `sha` kończyłyby się fałszywym konfliktem.
  let kolejka = Promise.resolve();
  function wKolejce(zadanie) {
    const wynik = kolejka.then(zadanie, zadanie);
    kolejka = wynik.catch(() => {});
    return wynik;
  }

  // Zapisuje projekt.json (i opis.md, gdy `zmienionoOpis`) oraz wpis w indeksie.
  function zapiszProjekt(stan, zmienionoOpis) {
    return wKolejce(async () => {
      const p = stan.projekt;
      p.zmieniono = new Date().toISOString();
      stan.shaProjektu = await zapisz(
        sciezkaProjektu(p.id),
        JSON.stringify(p, null, 2) + "\n",
        stan.shaProjektu,
        `Projekty: ${p.id}: zmiana`
      );
      if (zmienionoOpis) {
        stan.shaOpisu = await zapisz(sciezkaOpisu(p.id), stan.opis, stan.shaOpisu, `Projekty: ${p.id}: opis`);
      }
      await zmienIndeks((indeks) => wstawDoIndeksu(indeks, p), `Projekty: indeks (${p.id})`);
    });
  }

  // Nowe zadanie. Numer = największy z indeksu + 1; kolizja ścieżki (ktoś dodał
  // zadanie w tej samej chwili) kończy się błędem 422 i bierzemy następny numer.
  function nowyProjekt(dane) {
    return wKolejce(async () => {
      const { indeks } = await wczytajIndeks();
      let numer = Math.max(0, ...indeks.zadania.map((z) => parseInt(z.id, 10) || 0)) + 1;
      for (let proba = 0; proba < 5; proba++, numer++) {
        const id = `${String(numer).padStart(3, "0")}-${slug(dane.tytul)}`;
        const teraz = new Date().toISOString();
        const projekt = normalizujProjekt({
          id,
          typ: dane.typ,
          tytul: dane.tytul,
          priorytet: dane.priorytet || 0,
          sekcja: dane.sekcja || "",
          status: "otwarte",
          zakres: dane.zakres,
          podzadania: [],
          materialy: [],
          dziennik: [],
          utworzono: teraz,
          zmieniono: teraz,
        });
        try {
          await zapisz(sciezkaProjektu(id), JSON.stringify(projekt, null, 2) + "\n", null, `Projekty: nowe zadanie ${id}`);
        } catch (e) {
          if (e.kod === 422 || e.kod === 409) continue;
          throw e;
        }
        await zmienIndeks((i) => wstawDoIndeksu(i, projekt), `Projekty: indeks (${id})`);
        return id;
      }
      throw new Error("Nie udało się nadać numeru nowemu zadaniu, spróbuj ponownie.");
    });
  }

  // Zmiana statusu z listy (bez otwierania karty zadania).
  async function ustawStatus(id, status) {
    const stan = await wczytajProjekt(id);
    if (!stan) throw new Error("Nie znaleziono zadania.");
    stan.projekt.status = status;
    await zapiszProjekt(stan, false);
  }


  // ------------------------------------------------- opis i notatnik karty
  // Zadanie 043: zadanie to nazwa + opis (bez dziennika, podzadań i materiałów,
  // te pola zostają w plikach, ale interfejs ich nie pokazuje); pełną formę ma
  // tylko typ „projekt". Notatnik karty to jeden wpis typu „notatnik" na kartę.
  const jestProsty = (z) => (z.typ || "zadanie") === "zadanie"; // projekt i notatnik mają pełną formę

  async function zapiszOpis(id, tekst) {
    const stan = await wczytajProjekt(id);
    if (!stan) throw new Error("Nie znaleziono zadania.");
    stan.opis = tekst;
    await zapiszProjekt(stan, true);
  }

  // Id notatnika karty; gdy go jeszcze nie ma i `utworz`, zakłada go.
  async function notatnikKarty(karta, utworz) {
    const { indeks } = await wczytajIndeks();
    const istniejacy = indeks.zadania.find((z) => z.typ === "notatnik" && z.zakres && z.zakres.karta === karta);
    if (istniejacy) return istniejacy.id;
    if (!utworz) return null;
    return nowyProjekt({
      tytul: `Notatnik ${nazwaKarty(karta) || karta}`,
      typ: "notatnik",
      sekcja: nazwaKarty(karta),
      zakres: { karta, typ: "strona", cel: "", etykieta: "notatnik" },
    });
  }

  // Edytor opisu do wstawienia w listę i w dymek: pole tekstowe + „Zapisz".
  // opcje: { id } albo { zapewnijId: async () => id } (notatnik tworzony przy pierwszym zapisie).
  // Opis wczytuje się leniwie, dopiero po wywołaniu `.wczytaj()` na zwróconym elemencie.
  function edytorOpisu(opcje) {
    const kontener = document.createElement("div");
    kontener.className = "pu-opis-edytor";
    const pole = document.createElement("textarea");
    pole.rows = 5;
    pole.placeholder = "Opis (Markdown)…";
    const pasek = document.createElement("div");
    pasek.className = "pu-opis-pasek";
    const przycisk = document.createElement("button");
    przycisk.type = "button";
    przycisk.textContent = "Zapisz opis";
    const status = document.createElement("span");
    status.className = "pu-dymek-info";
    pasek.append(przycisk, status);
    kontener.append(pole, pasek);
    let id = opcje.id || null;
    let wczytano = false;
    const komunikat = (tekst, blad) => {
      status.textContent = tekst;
      status.classList.toggle("pu-blad", !!blad);
    };
    kontener.wczytaj = async () => {
      if (wczytano) return;
      wczytano = true;
      pole.disabled = true;
      komunikat("Wczytywanie…");
      try {
        if (!id && opcje.znajdzId) id = await opcje.znajdzId();
        if (id) {
          const stan = await wczytajProjekt(id);
          pole.value = stan ? stan.opis : "";
        }
        komunikat("");
      } catch (e) {
        wczytano = false;
        komunikat(e.message, true);
      }
      pole.disabled = false;
    };
    const zapiszZPola = async () => {
      przycisk.disabled = true;
      komunikat("Zapisywanie w repozytorium…");
      try {
        if (!id && opcje.zapewnijId) id = await opcje.zapewnijId();
        await zapiszOpis(id, pole.value);
        komunikat("Zapisano.");
      } catch (e) {
        komunikat(e.message, true);
      }
      przycisk.disabled = false;
    };
    przycisk.addEventListener("click", zapiszZPola);
    pole.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        zapiszZPola();
      }
    });
    return kontener;
  }

  // ------------------------------------------------------------------ pliki
  // Wysyła plik do projekty/<id>/pliki/. Zwraca wpis do `materialy`.
  async function wyslijPlik(stan, plik, nazwa) {
    if (plik.size > LIMIT_PLIKU_BAJTY) {
      throw new Error(`Plik jest większy niż ${LIMIT_PLIKU_BAJTY / 1_000_000} MB, większe trzymaj na Dysku Google i dodaj sam link.`);
    }
    const bajty = new Uint8Array(await plik.arrayBuffer());
    let nazwaDocelowa = bezpiecznaNazwaPliku(nazwa || plik.name);
    const id = stan.projekt.id;
    return wKolejce(async () => {
      for (let proba = 0; proba < 2; proba++) {
        try {
          await zapiszBase64(sciezkaPliku(id, nazwaDocelowa), bajtyNaBase64(bajty), null, `Projekty: ${id}: plik ${nazwaDocelowa}`);
          return {
            id: noweId(),
            rodzaj: "plik",
            nazwa: nazwaDocelowa,
            sciezka: sciezkaPliku(id, nazwaDocelowa),
            rozmiar: plik.size,
            typ: plik.type || "",
            czas: Date.now(),
          };
        } catch (e) {
          if (e.kod !== 422 || proba === 1) throw e;
          nazwaDocelowa = `${Date.now()}-${nazwaDocelowa}`; // plik o tej nazwie już jest
        }
      }
    });
  }

  function usunPlik(material) {
    return wKolejce(() => usun(material.sciezka, `Projekty: usunięto plik ${material.nazwa}`));
  }

  // Lista wszystkich plików pod ścieżką (rekurencyjnie) — GitHub nie ma „katalogów",
  // więc katalog znika dopiero, gdy skasujemy każdy plik w środku. Brak = [].
  async function plikiPodSciezka(sciezka) {
    const odpowiedz = await fetch(`${API}${kodujSciezke(sciezka)}?ref=${GALAZ}`, {
      headers: naglowki(),
      cache: "no-store",
    });
    if (odpowiedz.status === 404) return [];
    if (!odpowiedz.ok) throw await bladOdpowiedzi(odpowiedz, `lista ${sciezka}`);
    const wpisy = await odpowiedz.json();
    const wynik = [];
    for (const w of Array.isArray(wpisy) ? wpisy : []) {
      if (w.type === "dir") wynik.push(...(await plikiPodSciezka(w.path)));
      else wynik.push(w.path);
    }
    return wynik;
  }

  // Trwale usuwa zadanie: wszystkie pliki z projekty/<id>/ i wpis w indeksie.
  // Pliki najpierw, indeks na końcu — gdyby coś padło w połowie, ponowienie
  // dokończy sprzątanie (kasowanie nieistniejącego pliku jest pomijane).
  function usunProjekt(id) {
    if (!/^[\w-]+$/.test(id)) throw new Error("Niepoprawny identyfikator zadania.");
    return wKolejce(async () => {
      if (!token()) throw bladBrakTokenu();
      for (const sciezka of await plikiPodSciezka(`${KATALOG}/${id}`)) {
        await usun(sciezka, `Projekty: usunięto zadanie ${id}`);
      }
      await zmienIndeks((indeks) => {
        indeks.zadania = indeks.zadania.filter((z) => z.id !== id);
        return indeks;
      }, `Projekty: indeks (usunięto ${id})`);
    });
  }

  window.PR = {
    KARTY,
    nazwaKarty,
    token,
    ustawToken,
    odczytaj,
    pobierzPlik,
    wczytajIndeks,
    wczytajProjekt,
    zapiszProjekt,
    nowyProjekt,
    ustawStatus,
    jestProsty,
    zapiszOpis,
    notatnikKarty,
    edytorOpisu,
    wyslijPlik,
    usunPlik,
    usunProjekt,
    zapiszTekst: zapisz,
    zapiszBase64,
    bajtyNaBase64,
    usun,
    noweId,
    LIMIT_PLIKU_BAJTY,
  };
})();
