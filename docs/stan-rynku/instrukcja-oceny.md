# Instrukcja dziennej oceny stanu rynku (karta „Stan rynku”)

**Wersja: 1** (2026-11-01, zadanie 037). Ocena zapisuje numer wersji w polu
`wersjaInstrukcji`, więc po poprawce instrukcji widać, które oceny są sprzed niej.
Ulepszanie ocen robi się przez edycję tego pliku i podbicie wersji, a nie przez ręczne
poprawianie starych wpisów.

**Podział pracy.** Dane i wszystkie liczby (wskaźniki, sygnał, nastroje, historia,
skuteczność) liczy raz dziennie skrypt `src/stan_rynku/stan_rynku.py aktualizuj` w workflow GitHub Actions
pełnej platformy (dni robocze, 22:40 UTC). Rutyna Claude
**niczego nie przelicza i nie uruchamia aktualizacji danych**: czyta gotowe
`data/stan-rynku/stan.json` i pisze tylko ocenę słowną do
`data/stan-rynku/ocena.json`.

<details>
<summary>1. Kiedy i po co</summary>

Rutyna (zaplanowane zadanie Claude „Stan rynku: ocena dnia”) uruchamia się rano czasu
polskiego od wtorku do soboty, czyli po każdej sesji w USA.
Jej zadaniem jest zamienić liczby z karty w krótką, zrozumiałą ocenę dla inwestora
indeksowego S&P 500 (kogoś, kto trzyma cały indeks i patrzy na to, co rusza rynkiem, a nie na pojedyncze spółki): co dziś sprzyja indeksowi, co
mu grozi i na co patrzeć w najbliższych dniach. Ocena nie jest prognozą kursu ani poradą
inwestycyjną.

</details>

<details>
<summary>2. Kroki (kolejno)</summary>

1. Przeczytaj ten plik i zasady stylu z `.claude/CLAUDE.md` (pełne zdania, bez długiej kreski).
2. Przeczytaj `data/stan-rynku/stan.json`: `sesja`, `sygnal` (wynik, poziom, grupy,
   `wklad`, `zmienioneOceny`, `zmiana`), `nastroje`, `wskazniki` (wartości, punkty, `pod`,
   `zmiana`, `historycznie`), `skutecznosc` i `zrodla.bledy`.
3. **Sprawdź świeżość danych.** `sesja` powinna być ostatnią sesją w USA przed dniem oceny.
   Jeśli dane są starsze o więcej niż jeden dzień roboczy albo `zrodla.bledy` nie jest puste,
   napisz to wprost w pierwszym zdaniu opisu (np. „Dane są z 30.10.2026, bo nocna
   aktualizacja się nie udała”) i nie uruchamiaj aktualizacji samodzielnie.
4. **Idempotencja.** Jeśli `ocena.json` ma już `aktualna.sesja` równą `sesja` z `stan.json`,
   zakończ bez zmian.
5. Przeczytaj kontekst informacyjny, z którego wolno cytować fakty (w pełnej platformie: ogólny pogląd
   rynkowy i wiadomości z dnia oceny i poprzedniego). Nie szukaj nowych faktów w pamięci; czego nie
   przeczytałeś, tego nie piszesz.
6. Ustal **sygnał końcowy**. Zaczynasz od poziomu liczbowego (`sygnal.poziom`). Wolno go
   przesunąć **najwyżej o jeden poziom** i tylko z konkretnym powodem, którego liczby jeszcze
   nie widzą (np. decyzja Fed z dnia oceny, szok w wiadomościach, błąd danych). Powód wpisujesz
   w `uzasadnienieRoznicy`. Bez takiego powodu sygnał końcowy równa się liczbowemu.
7. Napisz ocenę (pola w punkcie 3), przenieś dotychczasową `aktualna` na początek `archiwum`
   (najnowsze pierwsze, najwyżej 60 wpisów) i wstaw nową `aktualna`.
8. Sprawdź plik: `python src/stan_rynku/stan_rynku.py sprawdz` (musi zakończyć się „ocena.json
   poprawna”).
9. Zapisz tylko `data/stan-rynku/ocena.json`: commit „Stan rynku: ocena dnia RRRR-MM-DD”,
   potem `git pull --rebase origin main && git push origin HEAD:main` (praca na `main`).

</details>

<details>
<summary>3. Format pliku dane/ocena.json</summary>

```json
{
  "wersjaInstrukcji": 1,
  "aktualna": {
    "data": "2026-11-03",
    "sesja": "2026-11-02",
    "wynik": 21.2,
    "poziomLiczbowy": "pozytywny",
    "sygnal": "pozytywny",
    "tytul": "Jedno zdanie, do 110 znaków",
    "opis": "Od 3 do 6 zdań, 150 do 1600 znaków; akapity rozdziela pusta linia.",
    "za": ["co sprzyja indeksowi, z liczbą"],
    "przeciw": ["co mu grozi, z liczbą"],
    "naCoPatrzec": ["wydarzenie albo próg z najbliższych dni"],
    "uzasadnienieRoznicy": "tylko gdy sygnal różni się od poziomLiczbowy",
    "wersjaInstrukcji": 1,
    "autor": "claude"
  },
  "archiwum": []
}
```

- `data` to dzień napisania oceny (czas polski), `sesja`, `wynik` i `poziomLiczbowy` kopiujesz
  z `stan.json` (`sesja`, `sygnal.wynik`, `sygnal.poziom`), żeby było wiadomo, na jakich danych
  powstała ocena.
- `sygnal` i `poziomLiczbowy`: `silnie-pozytywny`, `pozytywny`, `neutralny`, `negatywny`
  albo `silnie-negatywny`.
- `za` i `przeciw`: od 1 do 5 punktów, każdy z konkretną liczbą z `stan.json`; `naCoPatrzec`:
  od 0 do 5 punktów (wydarzenia tylko z przeczytanych źródeł, progi z reguł wskaźników).
- Wolno pogrubić najważniejsze liczby `**tak**`; innego formatowania nie używaj.

</details>

<details>
<summary>4. Jak pisać</summary>

1. **Pełne zdania, prosty język, bez żargonu bez wyjaśnienia** (CLAUDE.md, „Jak pisać
   wyjaśnienia”). Gdy używasz pojęcia technicznego (VIX, MACD, put/call), dopowiedz w kilku
   słowach, co znaczy.
2. **Pierwsze zdanie opisu** mówi, jaki jest sygnał i dlaczego (wynik, poziom, najmocniejsza i
   najsłabsza grupa). Dalej: co się zmieniło od poprzedniej oceny (`sygnal.zmiana`,
   `zmienioneOceny`), co mówią nastroje, na końcu jedno zdanie z historii z `skutecznosc`
   (np. jak często po takim sygnale przychodził spadek o 10% w 3 miesiące).
3. **Sygnał opisuje warunki i ryzyko, nie prognozę zwrotu.** Tak to formułuj: „tło sprzyja
   trzymaniu indeksu”, „ryzyko większych spadków wzrosło”, a nie „indeks wzrośnie”.
4. **Wskaźniki informacyjne** (GEX, skośność, put/call z otwartych pozycji, SKEW, ropa) możesz
   przywołać jako tło, ale zaznacz, że nie wchodzą do wyniku, a te z łańcucha SPX nie mają
   jeszcze historii do kalibracji.
5. **Nie zmyślaj.** Liczby tylko z `stan.json` i przeczytanych źródeł, fakty z wiadomości z
   podaniem źródła („według ING”). Niepewne twierdzenia pomiń albo oznacz `!!!_WERYFIKACJA_!!!`.
6. **Bez długiej kreski** (znak U+2014) i bez myślników jako separatorów zdań; `sprawdz`
   odrzuca plik z długą kreską.

</details>

<details>
<summary>5. Historia zmian instrukcji</summary>

- Wersja 1 (2026-11-01): pierwsza wersja razem z kartą (zadanie 037).

</details>
