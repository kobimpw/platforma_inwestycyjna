"""Testy rachunku VaR (Value at Risk) z karty VaR: kwantyl rozkładu normalnego i kroczące progi.

VaR to kwota, której strata w danym horyzoncie nie powinna przekroczyć z zadanym prawdopodobieństwem (tu
99%). Wzór zamknięty: VaR = z · σ · √horyzont · cena, gdzie z to kwantyl rozkładu normalnego, a σ dzienne
odchylenie standardowe zwrotów."""

import math
from statistics import NormalDist

import pandas as pd
import pytest

import var as karta_var


@pytest.mark.parametrize("poziom", [0.5, 0.9, 0.95, 0.975, 0.99, 0.995, 0.999, 0.001])
def test_kwantyl_normalny_zgadza_sie_z_biblioteka_standardowa(poziom):
    # przybliżenie Acklama ma błąd względny rzędu 1e-9; implementacja w bibliotece standardowej jest dokładna
    assert karta_var.kwantyl_normalny(poziom) == pytest.approx(NormalDist().inv_cdf(poziom), rel=1e-7, abs=1e-9)


def _tabela(n_dni: int, cena: float = 100.0) -> pd.DataFrame:
    """Zwroty na przemian +1% i -1%: średnia 0, a odchylenie próbkowe w oknie n (parzystym) to 0,01·√(n/(n-1))."""
    zwroty = [0.01 if i % 2 == 0 else -0.01 for i in range(n_dni)]
    return pd.DataFrame({"data": pd.bdate_range("2024-01-01", periods=n_dni).strftime("%Y-%m-%d"), "close": cena,
                         "open": cena, "high": cena, "low": cena, "zwrot": zwroty})


PARAMETRY = dict(horyzont_bez_korekty=1, horyzont_z_korekta=1, horyzont_percentyl=1, zaufanie=0.99, okno_odchylenia=20, okno_sredniej=20)


def test_var_jednodniowy_to_z_razy_sigma_razy_cena():
    wynik = karta_var.oblicz_var_kroczaco(_tabela(60), **PARAMETRY)
    sigma = 0.01 * math.sqrt(20 / 19)
    oczekiwany = NormalDist().inv_cdf(0.99) * sigma * 100.0
    assert wynik["var_bez_korekty"].iloc[-1] == pytest.approx(oczekiwany, rel=1e-6)


def test_przy_zerowym_dryfie_korekta_na_srednia_nie_zmienia_var():
    wynik = karta_var.oblicz_var_kroczaco(_tabela(60), **PARAMETRY)
    assert wynik["sr_zwrot_dzienny"].iloc[-1] == pytest.approx(0.0, abs=1e-12)
    assert wynik["var_z_korekta"].iloc[-1] == pytest.approx(wynik["var_bez_korekty"].iloc[-1], rel=1e-9)


def test_percentyl_empiryczny_to_minus_kwantyl_zwrotow_razy_cena():
    wynik = karta_var.oblicz_var_kroczaco(_tabela(60), **PARAMETRY)
    assert wynik["percentyl_empiryczny"].iloc[-1] == pytest.approx(0.01 * 100.0, rel=1e-6)   # 1. percentyl zwrotów to -1%


def test_prog_jest_przesuniety_o_horyzont_do_przodu():
    """Próg policzony w dniu t jest prognozą na dzień t+horyzont, więc na wykresie stoi naprzeciw tamtego dnia."""
    parametry = {**PARAMETRY, "horyzont_bez_korekty": 5}
    wynik = karta_var.oblicz_var_kroczaco(_tabela(60), **parametry)
    t = 40
    assert wynik["prog_bez_korekty"].iloc[t + 5] == pytest.approx(wynik["close"].iloc[t] - wynik["var_bez_korekty"].iloc[t])


def test_dluzszy_horyzont_daje_wiekszy_var_proporcjonalnie_do_pierwiastka():
    jeden = karta_var.oblicz_var_kroczaco(_tabela(60), **PARAMETRY)["var_bez_korekty"].iloc[-1]
    dziesiec = karta_var.oblicz_var_kroczaco(_tabela(60), **{**PARAMETRY, "horyzont_bez_korekty": 10})["var_bez_korekty"].iloc[-1]
    assert dziesiec == pytest.approx(jeden * math.sqrt(10), rel=1e-9)
