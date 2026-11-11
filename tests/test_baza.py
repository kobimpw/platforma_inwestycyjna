"""Testy warstwy SQL: schemat, ładowanie z plików, widoki analityczne i archiwizator historii.

Najważniejsza zasada: każdy widok sprawdzamy NIEZALEŻNYM rachunkiem w pandas na tych samych danych. Dwie różne
implementacje (zapytanie SQL i kod Pythona), które dają ten sam wynik, to mocniejszy dowód poprawności niż
sprawdzenie, że zapytanie „coś zwraca"."""

import csv
import json
import sqlite3
from datetime import date

import pandas as pd
import pytest

import baza
import stan_rynku as sr


@pytest.fixture(scope="module")
def polaczenie():
    """Baza zbudowana w pamięci z plików zatwierdzonych w data/ (bez zapisu czegokolwiek na dysk)."""
    p = baza.zbuduj()
    yield p
    p.close()


def _wiersze(polaczenie, zapytanie, *parametry):
    return [dict(r) for r in polaczenie.execute(zapytanie, parametry)]


# ------------------------------------------------------------------ budowa bazy
def test_baza_buduje_sie_z_plikow_i_tabele_faktow_maja_dane(polaczenie):
    for tabela in ("wskaznik", "put_call_dzienne", "opcje_spx_dzienne", "sygnal_odtworzony", "wskaznik_odczyt"):
        assert polaczenie.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] > 0, tabela


def test_budowa_jest_powtarzalna(polaczenie):
    druga = baza.zbuduj()
    tabele = [r[0] for r in polaczenie.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for tabela in tabele:
        assert polaczenie.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == druga.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    zapytanie = "SELECT * FROM v_skutecznosc_sygnalu ORDER BY poziom"
    assert _wiersze(polaczenie, zapytanie) == _wiersze(druga, zapytanie)


def test_zbudowana_na_dysku_baza_przechodzi_kontrole_integralnosci(tmp_path):
    p = baza.zbuduj(tmp_path / "test.sqlite")
    assert p.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert p.execute("PRAGMA foreign_key_check").fetchall() == []
    p.close()


# ------------------------------------------------------------------ ograniczenia schematu
@pytest.mark.parametrize(
    ("zapytanie", "parametry"),
    [
        ("INSERT INTO sygnal_odtworzony (data, wynik, spx) VALUES ('2030-01-01', 150, 5000)", ()),                 # wynik poza -100..100
        ("INSERT INTO sygnal_odtworzony (data, wynik, spx) VALUES ('2030-01-01', 10, -1)", ()),                    # cena nie może być ujemna
        ("INSERT INTO put_call_dzienne (data) SELECT MAX(data) FROM put_call_dzienne", ()),                         # duplikat klucza głównego
        ("INSERT INTO wskaznik_zapisany (data, wskaznik_id) VALUES ('2030-01-01', 'NIEMA')", ()),                   # klucz obcy do wskaznik
        ("INSERT INTO sygnal_zapisany (data, wynik, poziom) VALUES ('2030-01-01', -150, 'x')", ()),                 # wynik poza -100..100
        ("INSERT INTO wskaznik (id, grupa, nazwa, oceniany) VALUES ('x', 'inna', 'X', 1)", ()),                     # nieznana grupa
    ],
)
def test_ograniczenia_odrzucaja_zle_dane(polaczenie, zapytanie, parametry):
    with pytest.raises(sqlite3.IntegrityError):
        polaczenie.execute(zapytanie, parametry)
    polaczenie.rollback()


# ------------------------------------------------------------------ widoki kontra pandas
def test_skutecznosc_sygnalu_w_sql_zgadza_sie_z_rachunkiem_w_pythonie(polaczenie):
    """Tabelę skuteczności liczy na karcie funkcja pandas `skutecznosc`; widok SQL liczy ją oknami (LEAD, MIN OVER)."""
    historia = pd.read_sql_query("SELECT data, wynik, spx FROM sygnal_odtworzony ORDER BY data", polaczenie)
    indeks = pd.to_datetime(historia["data"])
    python = {w["poziom"]: w for w in sr.skutecznosc(pd.Series(historia["wynik"].values, index=indeks),
                                                      pd.Series(historia["spx"].values, index=indeks))["wiersze"] if w["poziom"] != "wszystkie"}
    sql = {w["poziom"]: w for w in _wiersze(polaczenie, "SELECT * FROM v_skutecznosc_sygnalu")}
    assert set(python) == set(sql)
    for poziom, p in python.items():
        s = sql[poziom]
        assert s["dni"] == p["dni"], poziom
        assert s["udzial_proc"] == pytest.approx(p["udzial"], abs=0.051), poziom
        for pole in ("sr21", "sr63", "dd63"):                  # zaokrąglane do 2 miejsc
            assert s[pole] == pytest.approx(p[pole], abs=0.011), (poziom, pole)
        for pole in ("plus21", "plus63", "p10"):                # zaokrąglane do 1 miejsca
            assert s[pole] == pytest.approx(p[pole], abs=0.051), (poziom, pole)


def test_swiezosc_danych_pokazuje_ostatnia_date_kazdej_tabeli_faktow(polaczenie):
    wiersze = {w["tabela"]: w for w in _wiersze(polaczenie, "SELECT * FROM v_swiezosc_danych")}
    for tabela in ("put_call_dzienne", "opcje_spx_dzienne", "sygnal_odtworzony"):
        assert wiersze[tabela]["wierszy"] > 0 and wiersze[tabela]["ostatnia_data"] <= date.today().isoformat()


# ------------------------------------------------------------------ archiwizator historii
def _stan(tmp_path, sesja="2026-11-10", wynik=15.7, ids=("a", "b")):
    stan = {"sesja": sesja, "spx": 7520.93,
            "sygnal": {"wynik": wynik, "poziom": "pozytywny",
                       "grupy": [{"nazwa": "Makro", "wynik": 28.9}, {"nazwa": "Rynek", "wynik": -11.1}, {"nazwa": "Technika", "wynik": 31.2}]},
            "nastroje": {"wartosc": 25.7},
            "wskazniki": [{"id": ids[0], "punkty": 2, "percentyl": 71.0, "stan": "dobrze"},
                          {"id": ids[1], "punkty": None, "percentyl": None, "stan": None}]}
    sciezka = tmp_path / "stan.json"
    sciezka.write_text(json.dumps(stan), encoding="utf-8")
    return sciezka


def test_archiwizacja_dopisuje_sesje_i_jest_idempotentna(tmp_path):
    stan, katalog = _stan(tmp_path), tmp_path / "historia"
    pierwsza = baza.archiwizuj(stan, katalog)
    zawartosc = (katalog / "sygnal_zapisany.csv").read_text(encoding="utf-8")
    druga = baza.archiwizuj(stan, katalog)
    assert (pierwsza["sygnal_dodane"], pierwsza["wskazniki_dodane"]) == (1, 2)
    assert (druga["sygnal_dodane"], druga["sygnal_zmienione"], druga["wskazniki_dodane"], druga["wskazniki_zmienione"]) == (0, 0, 0, 0)
    assert (katalog / "sygnal_zapisany.csv").read_text(encoding="utf-8") == zawartosc     # ponowne uruchomienie nic nie zmienia


def test_archiwizacja_zastepuje_te_sama_sesje_a_nowa_dopisuje_posortowana(tmp_path):
    katalog = tmp_path / "historia"
    baza.archiwizuj(_stan(tmp_path, "2026-11-10", 15.7), katalog)
    zmiana = baza.archiwizuj(_stan(tmp_path, "2026-11-10", 18.0), katalog)
    baza.archiwizuj(_stan(tmp_path, "2026-11-09", 12.0), katalog)
    assert zmiana["sygnal_zmienione"] == 1 and zmiana["sygnal_dodane"] == 0
    with (katalog / "sygnal_zapisany.csv").open(encoding="utf-8", newline="") as f:
        wiersze = list(csv.DictReader(f))
    assert [(w["data"], w["wynik"]) for w in wiersze] == [("2026-11-09", "12.0"), ("2026-11-10", "18.0")]


def test_zapisana_historia_trafia_do_bazy(tmp_path):
    ids = [r["id"] for r in _wiersze(baza.zbuduj(), "SELECT id FROM wskaznik ORDER BY id LIMIT 2")]
    katalog = tmp_path / "historia"
    baza.archiwizuj(_stan(tmp_path, ids=ids), katalog)
    p = baza.zbuduj(katalog_historii=katalog)
    assert _wiersze(p, "SELECT data, wynik, poziom, makro, rynek, technika FROM sygnal_zapisany") == [
        {"data": "2026-11-10", "wynik": 15.7, "poziom": "pozytywny", "makro": 28.9, "rynek": -11.1, "technika": 31.2}]
    zapisane = _wiersze(p, "SELECT wskaznik_id, punkty, percentyl FROM wskaznik_zapisany ORDER BY wskaznik_id")
    assert zapisane == [{"wskaznik_id": ids[0], "punkty": 2, "percentyl": 71.0}, {"wskaznik_id": ids[1], "punkty": None, "percentyl": None}]


def test_archiwizacja_dziala_na_zatwierdzonym_stanie_rynku(tmp_path):
    wynik = baza.archiwizuj(katalog=tmp_path / "historia")
    assert wynik["sygnal_dodane"] == 1 and wynik["wskazniki_dodane"] >= 50
