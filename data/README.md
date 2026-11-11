# Dane: słownik plików

Ten katalog zawiera dane karty „Stan rynku". W pełnej platformie zapisują je codziennie potoki (workflowy GitHub Actions)
i zaplanowane zadanie Claude, a w tej statycznej wersji poglądowej to **jednorazowa migawka z sesji 10.11.2026**.
Pliki są w repozytorium, a nie w bazie, bo w gicie dają czytelną historię zmian (widać, co dopisał potok danego dnia),
a karta czyta je wprost. Z tych plików powstaje też baza SQL (`make db`, patrz `sql/README.md`).

Nie przechowujemy surowych odpowiedzi API (np. pełnego łańcucha opcji, który ma kilka MB na symbol), więc wszystko tu
jest już przetworzone.

## Słownik

| Plik | Co zawiera | Źródło | Kto i jak często zapisuje (w pełnej platformie) |
|---|---|---|---|
| `stan-rynku/stan.json` | stan karty „Stan rynku": sygnał od -100 do 100, 54 wskaźniki (27 ocenianych), historia sygnału, tabela skuteczności | FRED, Cboe, Yahoo Finance | `python src/stan_rynku/stan_rynku.py aktualizuj`, raz dziennie w dni robocze po sesji w USA |
| `stan-rynku/cboe-putcall.json` | dzienne statystyki opcji Cboe (put/call dla całej giełdy), od 2019-10-07; tabela `kolumny` + `wiersze` | Cboe | ten sam skrypt, dopisywane codziennie |
| `stan-rynku/opcje-spx.json` | dzienne metryki łańcucha opcji SPX od 2026-10-30: ekspozycja gamma, skośność, put/call z otwartych pozycji, zmienność implikowana 30 i 90 dni | Cboe | ten sam skrypt, dopisywane codziennie |
| `stan-rynku/ocena.json` | ocena dnia napisana przez Claude (sygnał końcowy, uzasadnienie) i archiwum ocen | wskaźniki z `stan.json` | zaplanowane zadanie Claude, wtorek-sobota rano |
| `historia/sygnal_zapisany.csv` | co karta pokazywała w danym dniu: wynik sygnału, poziom, wyniki grup, nastroje, S&P 500 | `stan-rynku/stan.json` | `python src/baza/baza.py archiwizuj`; jeden wiersz na sesję, od 2026-11-10 |
| `historia/wskaznik_zapisany.csv` | punkty, percentyl i stan każdego wskaźnika w danym dniu | `stan-rynku/stan.json` | to samo polecenie; 54 wiersze na sesję |

Do statycznej strony trafiają tylko dwa pliki, które czyta przeglądarka: `stan-rynku/stan.json` i `stan-rynku/ocena.json`
(lista jest w `src/narzedzia/zbuduj_strone.py`). Pozostałe pliki służą skryptowi aktualizującemu i warstwie SQL.

## Zasady

1. **Nie edytuj ręcznie** plików zapisywanych przez potoki i zadania. Zmieniasz kod w `src/`, a plik odświeża skrypt.
   Jedyna ręczna zmiana względem pełnej platformy: w `stan-rynku/stan.json` źródło wskaźników VaR wskazuje adres notowań
   SPY zamiast linku do karty VaR, której nie ma w tej wersji.
2. **Historia w `historia/` jest tylko dopisywana.** Ponowne uruchomienie archiwizatora tego samego dnia zastępuje wiersze
   tej sesji, ale nie dubluje ich. To zapis tego, co karta pokazywała w danym dniu, więc nie poprawiamy go wstecz.
3. **Format tabel w JSON.** Dane rosnące codziennie (`cboe-putcall.json`, `opcje-spx.json`) mają postać
   `{"kolumny": [...], "wiersze": [[...], ...]}`: kolumny zapisane raz, a każdy dzień to jedna krótka lista. To
   oszczędza miejsce i od razu ładuje się do tabeli SQL.
4. **Dane osobowe i poufne tu nie trafiają.** Pozycje, ceny kupna i ustawienia użytkownika nie należą do tej wersji, a
   test `tests/test_wersja_pogladowa.py` pilnuje, żeby nie wróciły.
5. **Pliki muszą być poprawnym JSON** bez wartości `NaN` (przeglądarka ich nie wczyta); pilnuje tego
   `tests/test_kontrakty_danych.py`.
6. **Zakres i warunki użycia danych wyznaczają ich dostawcy** (FRED, Cboe, Yahoo Finance). Licencja MIT dotyczy kodu, a nie
   danych.
