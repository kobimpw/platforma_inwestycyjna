"""Testy rachunku karty „Stan rynku": poziomy sygnału, przyszłe zwroty, tabela skuteczności i format liczb.

Wszystkie przykłady są dobrane tak, żeby poprawny wynik dało się policzyć ręcznie wzorem, a nie
przepisać z samego kodu."""

import json
import math

import numpy as np
import pandas as pd
import pytest

import stan_rynku as sr


# ------------------------------------------------------------------ poziom sygnału
@pytest.mark.parametrize(
    ("wynik", "oczekiwany"),
    [
        (100, "silnie-pozytywny"), (40, "silnie-pozytywny"),     # granica należy do wyższego poziomu
        (39.99, "pozytywny"), (15, "pozytywny"),
        (14.99, "neutralny"), (0, "neutralny"), (-15, "neutralny"),
        (-15.01, "negatywny"), (-40, "negatywny"),
        (-40.01, "silnie-negatywny"), (-100, "silnie-negatywny"), (-2000, "silnie-negatywny"),
    ],
)
def test_poziom_granice_progow(wynik, oczekiwany):
    assert sr.poziom(wynik)[0] == oczekiwany


# ------------------------------------------------------------------ przyszłe zwroty
def _szereg(wartosci):
    return pd.Series(wartosci, index=pd.bdate_range("2020-01-01", periods=len(wartosci)), dtype=float)


def test_przyszle_zwroty_przy_stalym_wzroscie_zgadzaja_sie_ze_wzorem():
    ceny = _szereg(100 * 1.01 ** np.arange(300))
    z = sr.przyszle_zwroty(ceny)
    assert z.iloc[0]["r21"] == pytest.approx((1.01**21 - 1) * 100)
    assert z.iloc[0]["r63"] == pytest.approx((1.01**63 - 1) * 100)
    assert z.iloc[0]["dd63"] == 0.0   # cena tylko rośnie, więc nie ma obsunięcia


def test_przyszle_zwroty_obsuniecie_to_najnizsze_zamkniecie_wzgledem_dzisiejszego():
    ceny = _szereg([100.0] * 10 + [80.0] * 200)
    z = sr.przyszle_zwroty(ceny)
    assert z.iloc[0]["dd63"] == pytest.approx(-20.0)
    assert z.iloc[0]["r63"] == pytest.approx(-20.0)


def test_przyszle_zwroty_koniec_szeregu_nie_ma_jeszcze_wartosci():
    z = sr.przyszle_zwroty(_szereg(100 * 1.001 ** np.arange(200)))
    assert z["r21"].iloc[-21:].isna().all() and z["r21"].iloc[-22] == z["r21"].iloc[-22]
    assert z["r63"].iloc[-63:].isna().all()


def test_statystyki_przyszlosci_licza_udzialy_i_srednie():
    x = pd.DataFrame({"r21": [5.0, -5.0, 10.0, 0.0], "r63": [10.0, -5.0, 20.0, 0.0], "dd63": [0.0, -12.0, -3.0, -10.0]})
    s = sr.statystyki_przyszlosci(x)
    assert s["dni"] == 4
    assert s["sr63"] == 6.25
    assert s["plus63"] == 50.0          # dwa z czterech zwrotów są dodatnie (zero nie liczy się)
    assert s["p10"] == 50.0             # obsunięcie co najmniej 10% w dwóch z czterech przypadków (granica -10 wlicza się)
    assert s["dd63"] == -6.25


def test_statystyki_przyszlosci_dla_pustych_danych_to_brak_wartosci():
    s = sr.statystyki_przyszlosci(pd.DataFrame({"r21": [], "r63": [], "dd63": []}))
    assert s["dni"] == 0 and s["sr63"] is None and s["p10"] is None


# ------------------------------------------------------------------ tabela skuteczności
def test_skutecznosc_rozdziela_sesje_wedlug_poziomu_sygnalu():
    ceny = _szereg(100 * 1.002 ** np.arange(400))
    wynik = _szereg([50.0] * 200 + [-50.0] * 200)
    s = sr.skutecznosc(wynik, ceny)
    udzialy = {w["poziom"]: w["udzial"] for w in s["wiersze"]}
    assert udzialy["silnie-pozytywny"] == 50.0 and udzialy["silnie-negatywny"] == 50.0
    assert udzialy["wszystkie"] == 100.0
    assert s["od"] == "2020-01-01"


def test_skutecznosc_przy_stalym_wyniku_nie_zwraca_nan():
    """Stały sygnał nie ma rozrzutu, więc korelacja jest nieokreślona. Zapis NaN do JSON zepsułby kartę w przeglądarce."""
    ceny = _szereg(100 * 1.01 ** np.arange(300))
    s = sr.skutecznosc(_szereg([50.0] * 300), ceny)
    assert s["korelacja63"] is None and s["korelacjaObsuniecia"] is None
    json.dumps(s, allow_nan=False)   # nie rzuca wyjątku


# ------------------------------------------------------------------ format liczb po polsku
@pytest.mark.parametrize(
    ("wartosc", "miejsca", "oczekiwany"),
    [
        (1234.5, 1, "1234,5"),
        (12345.67, 1, "12 345,7"),      # spacja tysięcy (niełamliwa) od 10 000, jak w pl-PL
        (-3.14159, 2, "-3,14"),
        (-0.04, 1, "0,0"),                   # wartość zaokrąglona do zera nie dostaje minusa
        (None, 1, "–"),
        (float("nan"), 1, "–"),
    ],
)
def test_pl_formatuje_liczby_po_polsku(wartosc, miejsca, oczekiwany):
    assert sr.pl(wartosc, miejsca) == oczekiwany


# ------------------------------------------------------------------ zatwierdzona ocena dnia
def test_ocena_dnia_w_repozytorium_spelnia_reguly_walidacji():
    """Sprawdza budowę ocena.json. Zgodność oceny z bieżącym stan.json pomijamy celowo: dane liczy workflow
    o 22:40 UTC, a ocenę pisze rutyna Claude dopiero rano, więc przez kilka godzin każdej doby te dwa pliki
    mają różne sesje i to nie jest błąd kodu. Świeżość pilnuje osobno widok SQL `v_swiezosc_danych`."""
    bledy = [b for b in sr.element_ocena_sprawdz() if "w stan.json" not in b]
    assert bledy == []


def test_stan_rynku_w_repozytorium_ma_spojny_sygnal(korzen):
    stan = json.loads((korzen / "data/stan-rynku/stan.json").read_text(encoding="utf-8"))
    assert -100 <= stan["sygnal"]["wynik"] <= 100
    assert sr.poziom(stan["sygnal"]["wynik"])[0] == stan["sygnal"]["poziom"]
    assert len({w["id"] for w in stan["wskazniki"]}) == len(stan["wskazniki"])   # identyfikatory wskaźników są unikalne
    assert all(math.isfinite(g["wynik"]) for g in stan["sygnal"]["grupy"] if g["wynik"] is not None)
