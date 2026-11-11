# Dane: słownik plików

Ten katalog zawiera dane karty „Stan rynku" oraz próbki rynkowe dla kart „Pozycja" i „VaR". W pełnej platformie dane Stanu
rynku zapisują codziennie potoki (workflowy GitHub Actions) i zaplanowane zadanie Claude, a w tej statycznej wersji
poglądowej to **jednorazowa migawka z sesji 10.11.2026**, a próbki dla Pozycji i VaR pochodzą z **11.11.2026**.
Pliki są w repozytorium, a nie w bazie, bo w gicie dają czytelną historię zmian (widać, co dopisał potok danego dnia),
a karta czyta je wprost. Z tych plików powstaje też baza SQL (`make db`, patrz `sql/README.md`).

Nie przechowujemy surowych odpowiedzi API (np. pełnego łańcucha opcji, który ma kilka MB na symbol), więc wszystko tu
jest już przetworzone albo przycięte. Wyjątkiem są próbki w `przyklad/`, które mają kształt odpowiedzi źródeł (opis niżej).

## Słownik

| Plik | Co zawiera | Źródło | Kto i jak często zapisuje (w pełnej platformie) |
|---|---|---|---|
| `stan-rynku/stan.json` | stan karty „Stan rynku": sygnał od -100 do 100, 54 wskaźniki (27 ocenianych), historia sygnału, tabela skuteczności | FRED, Cboe, Yahoo Finance | `python src/stan_rynku/stan_rynku.py aktualizuj`, raz dziennie w dni robocze po sesji w USA |
| `stan-rynku/cboe-putcall.json` | dzienne statystyki opcji Cboe (put/call dla całej giełdy), od 2019-10-07; tabela `kolumny` + `wiersze` | Cboe | ten sam skrypt, dopisywane codziennie |
| `stan-rynku/opcje-spx.json` | dzienne metryki łańcucha opcji SPX od 2026-10-30: ekspozycja gamma, skośność, put/call z otwartych pozycji, zmienność implikowana 30 i 90 dni | Cboe | ten sam skrypt, dopisywane codziennie |
| `stan-rynku/ocena.json` | ocena dnia napisana przez Claude (sygnał końcowy, uzasadnienie) i archiwum ocen | wskaźniki z `stan.json` | zaplanowane zadanie Claude, wtorek-sobota rano |
| `historia/sygnal_zapisany.csv` | co karta pokazywała w danym dniu: wynik sygnału, poziom, wyniki grup, nastroje, S&P 500 | `stan-rynku/stan.json` | `python src/baza/baza.py archiwizuj`; jeden wiersz na sesję, od 2026-11-10 |
| `historia/wskaznik_zapisany.csv` | punkty, percentyl i stan każdego wskaźnika w danym dniu | `stan-rynku/stan.json` | to samo polecenie; 54 wiersze na sesję |
| `przyklad/quote-<TICKER>.json` | dzienne świece (open, high, low, close) z ostatnich 10 lat w kształcie odpowiedzi wykresu Yahoo Finance: SPY, QQQ i indeksy ^GSPC, ^NDX, ^XSP, ^XND | Yahoo Finance | `make probki` (jednorazowo; w pełnej platformie te dane przychodzą przez serwer pośredniczący) |
| `przyklad/options-_XSP.json`, `przyklad/options-_XND.json` | łańcuch opcji Cboe dla indeksów XSP (S&P 500 podzielony przez 10) i XND (Nasdaq-100 podzielony przez 100), przycięty według reguły niżej | Cboe | to samo polecenie |
| `przyklad/indeks.json` | spis próbek: czas pobrania, liczba punktów i zakres dat każdego pliku, opis przycięcia łańcuchów | wynik skryptu | to samo polecenie |

Do statycznej strony trafiają dwa pliki Stanu rynku, które czyta przeglądarka (`stan-rynku/stan.json` i
`stan-rynku/ocena.json`), oraz wszystkie pliki `.json` z `przyklad/` (listy są w `src/narzedzia/zbuduj_strone.py`).
Pozostałe pliki służą skryptowi aktualizującemu i warstwie SQL.

## Próbki dla kart „Pozycja" i „VaR" (`przyklad/`)

W pełnej platformie te dwie karty pytają o notowania (Yahoo Finance) i łańcuch opcji (Cboe) własny serwer pośredniczący,
bo przeglądarka nie może pytać tych źródeł wprost: ich odpowiedzi nie mają nagłówków CORS, którymi serwer zezwala stronie z
innej domeny na odczyt odpowiedzi. Ta wersja nie ma takiego serwera, więc karty czytają zapisane próbki w **tym samym
kształcie**, jaki zwracają źródła (robi to moduł `web/shared/probka.js`). Próbki pobiera polecenie `make probki`
(`src/narzedzia/pobierz_probki.py`: sama biblioteka standardowa, bez kluczy, wymaga internetu) i **nie odświeżają się same**.

Co warto wiedzieć o próbkach:

- **Są zamrożone w czasie.** Karty liczą dni do wygaśnięcia opcji od dnia próbki, a nie od dzisiaj. Dzięki temu pokaz nie
  psuje się, gdy terminy z próbki mijają, ale też nie pokazuje bieżącego rynku. Łańcuchy opcji to opóźnione notowania Cboe
  z 11.11.2026, a świece Yahoo sięgają sesji 10.11.2026.
- **Łańcuch opcji jest przycięty**, bo pełny ma kilkanaście tysięcy opcji (sam XSP ponad 7 MB). Zostają terminy do 100 dni,
  strike'i od 88% do 112% ceny indeksu, opcje call od 98% do 110% ceny i do 45 dni ze wszystkimi strike'ami (z nich
  generator buduje zakłady), a pozostałe opcje tylko na rzadszej siatce strike'ów (co 5 punktów, a dla indeksów poniżej
  400 punktów co 2). Wskaźniki liczone z CAŁEGO łańcucha (np. ekspozycja gamma albo put/call z otwartych pozycji) mogą się
  więc różnić od wartości z pełnych danych. Dokładny opis jest w `przyklad/indeks.json`.
- **Pozycje w profilach są fikcyjne.** Karta Pozycja ma dwa profile przykładowe (ETF SPY i QQQ) z wymyśloną liczbą jednostek
  i ceną kupna. Ceny kupna dobrano tak, żeby na dzień próbki pozycje były lekko pod wodą: generator zakładów stawia spready
  tam, gdzie zysk z ETF pokrywa ich stratę, więc przy dużym zysku strike'i wypadałyby tuż przy cenie indeksu i żaden zakład
  nie spełniałby filtra propozycji. Po odświeżeniu próbek warto sprawdzić te dwie liczby w `src/pozycja/pozycja.py`.
- **Dostępne tickery** na karcie VaR to te z `indeks.json` (SPY, QQQ, ^GSPC, ^NDX, ^XSP); inny ticker kończy się
  czytelnym komunikatem, że próbki dla niego nie ma.

## Zasady

1. **Nie edytuj ręcznie** plików zapisywanych przez potoki i zadania. Zmieniasz kod w `src/`, a plik odświeża skrypt.
   Jedyna ręczna zmiana względem pełnej platformy: w `stan-rynku/stan.json` źródło wskaźników VaR wskazuje adres notowań
   SPY zamiast linku do karty VaR, której nie ma w tej wersji.
2. **Historia w `historia/` jest tylko dopisywana.** Ponowne uruchomienie archiwizatora tego samego dnia zastępuje wiersze
   tej sesji, ale nie dubluje ich. To zapis tego, co karta pokazywała w danym dniu, więc nie poprawiamy go wstecz.
3. **Format tabel w JSON.** Dane rosnące codziennie (`cboe-putcall.json`, `opcje-spx.json`) mają postać
   `{"kolumny": [...], "wiersze": [[...], ...]}`: kolumny zapisane raz, a każdy dzień to jedna krótka lista. To
   oszczędza miejsce i od razu ładuje się do tabeli SQL.
4. **Dane osobowe i poufne tu nie trafiają.** Pozycje, ceny kupna i ustawienia użytkownika nie należą do tej wersji (profile
   przykładowe karty Pozycja mają fikcyjne liczby), a test `tests/test_wersja_pogladowa.py` pilnuje, żeby prawdziwe nie
   wróciły.
5. **Pliki muszą być poprawnym JSON** bez wartości `NaN` (przeglądarka ich nie wczyta); pilnuje tego
   `tests/test_kontrakty_danych.py`.
6. **Zakres i warunki użycia danych wyznaczają ich dostawcy** (FRED, Cboe, Yahoo Finance). Próbki w `przyklad/` są małe,
   jednorazowe i opisane jako przykładowe. Licencja MIT dotyczy kodu, a nie danych.
