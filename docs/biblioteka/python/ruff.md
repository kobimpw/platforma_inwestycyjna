# ruff
Język: Python
Kategoria: Testy i jakość kodu
Status: w użyciu
Pakiet: ruff
Strona: https://docs.astral.sh/ruff/
Gdzie w projekcie: konfiguracja w pyproject.toml, uruchamiany przez `make lint` i workflow .github/workflows/ci.yml
W requirements.txt: nie w requirements.txt, tak w requirements-dev.txt (wersja przypięta)

ruff to bardzo szybki program, który czyta kod Pythona i wskazuje w nim błędy i niedbałości, zanim kod w ogóle się uruchomi: nieużywane importy, odwołania do nieistniejących nazw, błędy składni.
W projekcie działa w trybie samych błędów (reguły `E9` i `F`), bo pliki kart zawierają HTML i JS jako długie teksty i reguły stylu tylko by hałasowały.
Warto go uruchamiać przed każdym commitem (`make lint`), bo błąd w nazwie zmiennej ujawnia się wtedy w sekundę, a nie dopiero podczas nocnego przebiegu workflowu.
