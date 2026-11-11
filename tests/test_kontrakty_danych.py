"""Kontrakty danych: co musi zawsze wynikać z plików zapisywanych w repozytorium przez potoki, nocne zadania i stronę.

Dane trafiają do repozytorium bez nadzoru człowieka (boty co kilka godzin), a strona czyta je prosto z plików,
więc jeden zepsuty plik (np. z wartością NaN, której przeglądarka nie wczyta) psuje kartę. Testy nie sprawdzają
świeżości danych (to zadanie widoku SQL `v_swiezosc_danych`), tylko ich budowę."""

import json
import re
import subprocess
from datetime import date

import pytest

RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _pliki_json(korzen):
    try:
        wyjscie = subprocess.check_output(["git", "ls-files", "-z", "*.json"], cwd=korzen, text=True)
        sciezki = [korzen / p for p in wyjscie.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        sciezki = [p for p in korzen.rglob("*.json") if "node_modules" not in p.parts]
    return sorted(p for p in sciezki if p.is_file())


def _wczytaj(korzen, sciezka):
    return json.loads((korzen / sciezka).read_text(encoding="utf-8"))


def test_wszystkie_pliki_json_sa_poprawne_i_nie_zawieraja_nan(korzen):
    zle = []
    for plik in _pliki_json(korzen):
        stale = []
        try:
            json.loads(plik.read_text(encoding="utf-8"), parse_constant=stale.append)   # NaN, Infinity, -Infinity
        except ValueError as blad:
            zle.append(f"{plik.relative_to(korzen)}: niepoprawny JSON ({blad})")
            continue
        if stale:
            zle.append(f"{plik.relative_to(korzen)}: wartości {sorted(set(stale))} (przeglądarka ich nie wczyta)")
    assert zle == []


@pytest.mark.parametrize("sciezka", ["data/stan-rynku/cboe-putcall.json", "data/stan-rynku/opcje-spx.json"])
def test_tabele_kolumny_i_wiersze_sa_spojne_a_daty_rosna(korzen, sciezka):
    d = _wczytaj(korzen, sciezka)
    kolumny, wiersze = d["kolumny"], d["wiersze"]
    assert kolumny[0] == "data" and wiersze
    daty = [w[0] for w in wiersze]
    assert all(len(w) == len(kolumny) for w in wiersze), "wiersz ma inną liczbę pól niż lista kolumn"
    assert all(RE_DATA.match(x) for x in daty)
    assert daty == sorted(set(daty)), "daty muszą być unikalne i rosnące"
    assert date.fromisoformat(daty[-1]) <= date.today()


def test_archiwum_put_call_siega_pazdziernika_2019(korzen):
    wiersze = _wczytaj(korzen, "data/stan-rynku/cboe-putcall.json")["wiersze"]
    assert wiersze[0][0] == "2019-10-07" and len(wiersze) > 1700


def test_stan_rynku_ma_poprawne_wskazniki(korzen):
    stan = _wczytaj(korzen, "data/stan-rynku/stan.json")
    assert RE_DATA.match(stan["sesja"]) and stan["spx"] > 0
    for w in stan["wskazniki"]:
        assert w["grupa"] in {"makro", "rynek", "technika"}, w["id"]
        if w["oceniany"]:
            assert w["punkty"] is None or -w["maks"] <= w["punkty"] <= w["maks"], f"punkty poza zakresem: {w['id']}"
    oceniane = [w for w in stan["wskazniki"] if w["oceniany"]]
    assert sum(g["wynik"] is not None for g in stan["sygnal"]["grupy"]) == 3 and len(oceniane) > 10
