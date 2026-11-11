"use strict";

/**
 * Wspólny moduł „Ustawienia" — zapis konfiguracji użytkownika (np. widoków
 * i kolumn tabel) w repozytorium, w katalogu `ustawienia/<klucz>.json`, przez
 * GitHub Contents API tym samym tokenem co „Historia zakładów" i „Projekty i
 * uwagi" (niskopoziomowy zapis daje `PR` z shared/projekty.js, który musi być
 * wczytany wcześniej). Powód: ustawienia mają wyglądać tak samo na każdym
 * urządzeniu, a `localStorage` jest osobny w każdej przeglądarce — patrz
 * `.claude/CLAUDE.md`, sekcja „Ustawienia użytkownika".
 *
 * Wystawia jeden globalny obiekt `USTAW`.
 */
const USTAW = (function () {
  const KATALOG = "ustawienia";
  const sciezka = (klucz) => `${KATALOG}/${klucz}.json`;

  // Zapisy idą jeden po drugim — dwa równoległe PUT na ten sam plik z tym samym
  // `sha` kończyłyby się fałszywym konfliktem.
  let kolejka = Promise.resolve();

  function dostepne() {
    return !!(window.PR && window.PR.token());
  }

  // Zwraca { wartosc, sha }; brak pliku = { wartosc: domyslne, sha: null }.
  async function wczytaj(klucz, domyslne) {
    const plik = await PR.odczytaj(sciezka(klucz));
    if (!plik) return { wartosc: domyslne, sha: null };
    try {
      return { wartosc: JSON.parse(plik.tresc), sha: plik.sha };
    } catch (e) {
      throw new Error(`Plik ${sciezka(klucz)} jest uszkodzony, popraw go albo usuń z repozytorium.`);
    }
  }

  // Odczyt najświeższej wersji → `mutuj(wartosc)` → zapis, z ponowieniem przy
  // konflikcie. Zawsze na świeżej kopii, żeby nie nadpisać zmiany zrobionej na
  // innym urządzeniu. `mutuj` może zmienić argument w miejscu albo zwrócić nowy.
  function zmien(klucz, domyslne, mutuj, opis) {
    const zapis = kolejka.then(async () => {
      for (let proba = 0; proba < 4; proba++) {
        const { wartosc, sha } = await wczytaj(klucz, domyslne);
        const nowa = mutuj(wartosc) || wartosc;
        try {
          await PR.zapiszTekst(sciezka(klucz), JSON.stringify(nowa, null, 2) + "\n", sha, `Ustawienia: ${klucz}: ${opis}`);
          return nowa;
        } catch (e) {
          if (e.kod !== 409 && e.kod !== 422) throw e;
        }
      }
      throw new Error("Nie udało się zapisać ustawień (konflikt), spróbuj ponownie.");
    });
    kolejka = zapis.catch(() => {});
    return zapis;
  }

  return { dostepne, wczytaj, zmien };
})();
