# sqlite3
Język: Python
Kategoria: Dane i SQL
Status: w użyciu
Pakiet: sqlite3 (biblioteka standardowa Pythona, nie wymaga instalacji)
Strona: https://docs.python.org/3/library/sqlite3.html
Gdzie w projekcie: src/baza/baza.py, sql/schema.sql, sql/widoki.sql, tests/test_baza.py
W requirements.txt: nie dotyczy (część biblioteki standardowej)

sqlite3 to wbudowana w Pythona baza danych SQL, zapisana w jednym pliku albo trzymana w pamięci. Nie trzeba instalować ani uruchamiać serwera: `sqlite3.connect(":memory:")` daje gotową bazę, do której wysyłasz zwykłe zapytania SQL.
W projekcie buduje z plików w `data/` bazę analityczną (tabele z kluczami i ograniczeniami oraz widoki z funkcjami okna). Liczymy na niej m.in. tabelę skuteczności sygnału rynku i kontrolę świeżości danych. Baza jest pochodna: powstaje od zera poleceniem `make db`, więc nie trafia do repozytorium.
Warto po nią sięgać, gdy pytanie dotyczy historii i grupowania (ranking, udział w sumie, zmiana względem poprzedniego okresu), bo funkcje okna (`LEAD`, `MIN() OVER`, `COUNT() OVER`) robią to w jednym zapytaniu zamiast w pętli.
