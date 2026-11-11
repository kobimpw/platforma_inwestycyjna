"""Ścieżki, których używają potoki danych i narzędzia (polecenia `aktualizuj`, `sprawdz`, `archiwizuj` i inne).

Test regeneracji kart sprawdza tylko polecenie `generuj`. Tymczasem w pełnej platformie workflowy i nocne zadania Claude
wołają inne polecenia tych samych skryptów, które czytają i zapisują pliki w `data/`. Błąd w jednej stałej ścieżki (np. zły
`parents[N]` po przeniesieniu pliku) wyszedłby dopiero w nocy. Ten test importuje moduły i sprawdza, że każda stała
wskazuje istniejący plik albo katalog, bez uruchamiania czegokolwiek, co łączy się z siecią."""

import importlib

import pytest

# moduł -> (stałe wskazujące istniejące PLIKI, stałe wskazujące istniejące KATALOGI)
OCZEKIWANE = {
    "stan_rynku": (["SCIEZKA_STAN", "SCIEZKA_PUTCALL", "SCIEZKA_OPCJE", "SCIEZKA_OCENA", "SCIEZKA_VAR"], ["KATALOG", "DANE"]),
    "mapa_kodu": ([], ["WEB", "SRC"]),
    "baza": ([], ["DANE", "SQL", "KATALOG_HISTORII"]),
    "zbuduj_strone": ([], ["WEB", "DANE"]),
}


@pytest.mark.parametrize("nazwa", sorted(OCZEKIWANE))
def test_stale_sciezek_wskazuja_istniejace_pliki_i_katalogi(nazwa):
    modul = importlib.import_module(nazwa)
    pliki, katalogi = OCZEKIWANE[nazwa]
    brak_pliku = [s for s in pliki if not getattr(modul, s).is_file()]
    brak_katalogu = [s for s in katalogi if not getattr(modul, s).is_dir()]
    assert brak_pliku == [] and brak_katalogu == [], f"{nazwa}: nie istnieją pliki {brak_pliku} i katalogi {brak_katalogu}"


def test_sciezki_zapisu_bazy_i_historii_leza_w_data_a_schemat_w_sql(korzen):
    import baza
    assert baza.DOMYSLNA_BAZA.parent == korzen / "data" and baza.KATALOG_HISTORII == korzen / "data" / "historia"
    assert (baza.SQL / "schema.sql").is_file() and (baza.SQL / "widoki.sql").is_file()
