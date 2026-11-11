# pytest
Język: Python
Kategoria: Testy i jakość kodu
Status: w użyciu
Pakiet: pytest
Strona: https://docs.pytest.org
Gdzie w projekcie: tests/*.py, konfiguracja w pyproject.toml, uruchamiany przez `make test` i workflow .github/workflows/ci.yml
W requirements.txt: nie w requirements.txt, tak w requirements-dev.txt (wersja przypięta)

pytest to najpopularniejsze narzędzie do pisania i uruchamiania testów w Pythonie: test to zwykła funkcja, której nazwa zaczyna się od `test_`, a sprawdzenie to zwykłe `assert`. Po uruchomieniu pokazuje, który test i dlaczego nie przeszedł.
W projekcie testuje rachunki (VaR, wskaźniki, tabela skuteczności sygnału), kontrakty danych, spójność ścieżek do plików, regenerację stron kart oraz widoki SQL, a te ostatnie porównuje z niezależnym rachunkiem w pandas.
Przydaje się zwłaszcza przy zmianach, które dotykają wielu plików naraz: zielone testy po przeniesieniu katalogów albo zmianie progu to dowód, że nic się nie zepsuło po cichu.
