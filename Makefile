# Wspólne polecenia projektu (wersja poglądowa). Uruchamiaj z korzenia repozytorium: `make <cel>`; `make help` pokazuje listę.
PY ?= python3
GENERATORY = biblioteka/biblioteka.py stan_rynku/stan_rynku.py

.PHONY: help install lint test build check serve strona db swiezosc

help:  ## lista poleceń
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-9s %s\n", $$1, $$2}'

install:  ## instaluje zależności do pracy nad kodem (testy i linter)
	$(PY) -m pip install -r requirements-dev.txt

lint:  ## ruff (błędy składni i logiki w Pythonie) oraz kontrola składni plików JavaScript
	$(PY) -m ruff check src tests
	find web src tests -not -path '*/node_modules/*' \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' \) -print0 | xargs -0 -n1 node --check

test:  ## testy Pythona (pytest)
	$(PY) -m pytest

build:  ## regeneruje strony kart (index.html, app.js) i mapę kodu z plików .py
	for g in $(GENERATORY); do $(PY) src/$$g generuj || exit 1; done
	$(PY) src/narzedzia/mapa_kodu.py

check: lint test  ## to samo, co sprawdza CI

serve:  ## lokalny podgląd strony: http://127.0.0.1:8000/
	$(PY) src/narzedzia/serwer.py

strona:  ## składa statyczną stronę do publikacji (_site/), tak jak workflow GitHub Pages
	$(PY) src/narzedzia/zbuduj_strone.py

db:  ## buduje bazę SQLite (data/platforma.sqlite) z plików w data/ i sql/
	$(PY) src/baza/baza.py zbuduj

swiezosc:  ## ostatnia data i liczba wierszy w każdej tabeli faktów (monitoring potoków)
	$(PY) src/baza/baza.py swiezosc
