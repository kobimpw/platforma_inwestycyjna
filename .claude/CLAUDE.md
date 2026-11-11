# Instrukcje dla Claude (wersja poglądowa)

To statyczna, poglądowa wersja projektu, przeznaczona dla rekrutera, a nie pełnoprawna platforma. Pełna platforma jest
prywatna. Ten plik zbiera konwencje, według których powstawał kod, w zakresie, który jest w tym repozytorium.

## Zakres wersji poglądowej (najważniejsze)

- W repozytorium są dwie karty (Stan rynku i Biblioteka), warstwa SQL, testy, CI i budowa statycznej strony. Nie dodawaj
  tu kart, danych ani plików z pełnej platformy bez wyraźnej prośby właściciela.
- Repozytorium jest **publiczne**. Nie wpisuj w żaden plik kluczy dostępu, haseł, adresów e-mail, adresów prywatnych usług,
  pozycji i cen kupna, nagrań ani treści osób trzecich (artykułów, transkrypcji). Część tych zasad pilnuje test
  `tests/test_wersja_pogladowa.py`, ale nie zastępuje on myślenia.
- Dane w `data/` to migawka z jednej sesji. Nie opisuj ich jako odświeżanych na żywo.

## Zakaz długiej kreski (pauzy) w tekstach dla użytkownika

Nie używaj w tekstach dla użytkownika długiej kreski (pauzy, znak Unicode U+2014) otoczonej spacjami. Dotyczy to
odpowiedzi w czacie, plików `.md`, komunikatów w interfejsie i opisów. Zamiast niej użyj przecinka, dwukropka, kropki
albo nawiasu. Zwykły łącznik i półpauza w przedziałach liczb (np. 135–145) są dozwolone. Walidator oceny dnia
(`python src/stan_rynku/stan_rynku.py sprawdz`) odrzuca plik z długą kreską.

## Jak pisać wyjaśnienia: opisowo i prostym językiem

Tłumaczenia i uzasadnienia pisz **pełnymi, rozwiniętymi zdaniami i prostym językiem**, nie skrótami myślowymi. Jeśli
zdanie da się zrozumieć tylko wtedy, gdy czytający już wie, o czym mówisz, to nie jest wyjaśnienie, a notatka dla siebie.

1. **Każde pojęcie techniczne rozwiń przy pierwszym użyciu**: jednym zdaniem, co to jest i skąd się bierze.
2. **Nagłówki tabel i kolumn muszą być zrozumiałe same z siebie.**
3. **Dodawaj analogię z życia, kiedy mechanizm jest nieoczywisty** (ubezpieczenie, zakład, wynajem).
4. **Po tabeli z liczbami zawsze napisz, jak ją czytać i co z niej wynika.**
5. **Nie zmyślaj.** Czego nie wiesz albo nie możesz sprawdzić, oznacz `!!!_WERYFIKACJA_!!!`.

Nie dotyczy to komunikatów commitów ani komentarzy w kodzie: tam zwięzłość jest zaletą.

## Układ repozytorium

| Katalog | Co w nim jest |
|---|---|
| `src/` | kod Pythona: generatory kart (`src/<karta>/<karta>.py`), narzędzia (`src/narzedzia/`), warstwa SQL (`src/baza/`) |
| `web/` | strona: HTML, CSS, JS; `index.html` i `app.js` kart są GENEROWANE z `src/`, nie edytuje się ich ręcznie |
| `data/` | migawka danych karty Stan rynku, słownik w `data/README.md` |
| `sql/` | schemat i widoki bazy SQLite, budowanej z `data/` poleceniem `make db` (plik bazy nie trafia do repo) |
| `tests/` | testy (`make test`): rachunki, kontrakty danych, spójność ścieżek, regeneracja kart, straż publicznego repo |
| `docs/` | dokumentacja: `docs/PRZEWODNIK.md`, wpisy biblioteki, instrukcja oceny dnia |
| `projekty/` | zapis procesu pracy (tu tylko specyfikacja karty Stan rynku) |

Zasady pracy:

1. Skrypty uruchamia się z korzenia repo: `python src/<karta>/<karta>.py <polecenie>`. Ścieżki liczą od korzenia
   (`Path(__file__).resolve().parents[2]`), więc nie zależą od bieżącego katalogu.
2. Po zmianie generatora uruchom `make build` (regeneruje karty i mapę kodu), a przed commitem `make check` (to samo robi
   CI). `tests/test_regeneracja_kart.py` pilnuje, żeby `web/` odpowiadał generatorom, a `tests/test_sciezki.py`, żeby
   odwołania do plików nie wskazywały nieistniejących miejsc.
3. Nowy plik danych w `data/` opisz w `data/README.md`. Nowa tabela historii wymaga zmiany `sql/schema.sql`, ładowania w
   `src/baza/baza.py` i testu w `tests/test_baza.py`.
4. Historia zapisana na bieżąco (`data/historia/*.csv`) jest tylko dopisywana przez `python src/baza/baza.py archiwizuj`.
   Nie edytuj jej ręcznie: to zapis tego, co karta pokazywała w danym dniu.
5. Strona publikowana na GitHub Pages składa się poleceniem `make strona` z jawnej listy plików (`src/narzedzia/zbuduj_strone.py`).
   Nowy plik danych dla strony trzeba tam dopisać świadomie.

## Karty: wzorzec jednoplikowy (py, html, js)

Karty (kod w `src/<karta>/<karta>.py`, strona w `web/<karta>/`) buduje się wzorem `src/stan_rynku/stan_rynku.py`: CAŁA
logika (Python, fragment HTML i kod JS jako stałe tekstowe) mieszka w jednym pliku `.py`, a funkcja `generuj()` wypisuje
z niego `index.html` i `app.js`. Tych dwóch plików nigdy nie edytuje się ręcznie.

1. **Funkcje i orkiestrator, nie klasy**, chyba że kilka metod faktycznie współdzieli stan.
2. **Dwie sekcje: „magazyn funkcji" i „elementy".** Magazyn trzyma wszystkie zwykłe funkcje pomocnicze, a „elementy"
   tylko orkiestratory (po jednym na każdy wizualny element strony) razem z ich `HTML_FRAGMENT_X` i `APP_JS_X`.
3. **Nowy element to nowy, niezależny fragment.** Nie modyfikuj istniejącego kodu przy dodawaniu kolejnego elementu:
   buduj osobny blok i łącz go z resztą wyłącznie w `generuj()`.

## Interfejs: styl terminala, motyw, numerki bloków

- Strona to siatka okien (klasy `t-siatka`, `t-okno`, `t-naglowek`, `t-tresc`) sklejonych cienkimi liniami, bez cieni.
  Okna można przesuwać i zmieniać im rozmiar (`web/shared/okna.js`), a na karcie Stan rynku układać w zakładki
  (`web/shared/przestrzen.js`).
- Kolory dodawaj wyłącznie przez zmienne z `:root` w `web/style.css`, w obu paletach naraz (Dzień i Noc), nigdy na sztywno.
- Wspólny skrypt `web/shared/oznaczenia.js` dokleja numerek do każdego głównego bloku strony. Kliknięcie numerka otwiera
  dymek z fragmentami kodu, z których blok powstał (mapa: `src/narzedzia/mapa_kodu.py`, wynik w `web/shared/mapa-kodu.json`).
  Po każdej zmianie kodu karty uruchom `make build`, żeby mapa się zgadzała.
- Nawigacja jest w `web/shared/sidebar.js`. Nowa karta dochodzi tam, w `OZNACZENIA_KARTY` (`oznaczenia.js`), w `KARTY`
  (`web/shared/projekty.js`) i w słowniku `KARTY` w `src/narzedzia/mapa_kodu.py`; test `tests/test_nawigacja.py` pilnuje
  zgodności tych list.

## README i przewodnik mają zgadzać się ze stanem repozytorium

`README.md` to krótka wizytówka dla czytelnika z zewnątrz, a `docs/PRZEWODNIK.md` to ściągawka po strukturze repo. Traktuj
oba jako coś, co trzeba utrzymywać: jeśli dodajesz albo usuwasz katalog w korzeniu, albo zmieniasz jego przeznaczenie,
zaktualizuj odpowiednią sekcję w tym samym zadaniu.
