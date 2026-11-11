"""Próbki danych rynkowych dla kart VaR i Pozycja (src/narzedzia/pobierz_probki.py oraz data/przyklad/).

Karty w wersji poglądowej nie mają serwera pośredniczącego, więc czytają zapisane próbki w kształcie odpowiedzi Yahoo
Finance (notowania) i Cboe (łańcuch opcji). Testy sprawdzają dwie rzeczy: że skrypt przycina odpowiedzi zgodnie z
opisaną regułą (na danych zmyślonych, bez sieci) oraz że zatwierdzone pliki są spójne ze spisem i z tym, czego potrzebują
karty (profile przykładowe Pozycji i ticker domyślny VaR)."""

import json
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone

import pytest

import pobierz_probki as pp

DZIEN = date(2026, 11, 11)
TIMESTAMP = "2026-11-11 11:00:00"


# ---------------------------------------------------------------------------
# dane zmyślone: odpowiedzi w kształcie źródeł
# ---------------------------------------------------------------------------
def _opcja(termin: date, typ: str, strike: float, root: str = "XSP", **pola) -> dict:
    return {"option": f"{root}{termin:%y%m%d}{typ}{round(strike * 1000):08d}", "bid": 1.0, "bid_size": 10.0, "ask": 1.2, "ask_size": 10.0,
            "iv": 0.2, "open_interest": 5.0, "volume": 1.0, "delta": 0.5, "gamma": 0.01, "theta": -0.1, "theo": 1.1,
            "last_trade_time": None, "pole_obce": "do odrzucenia", **pola}


def _lancuch(opcje: list[dict], cena: float = 700.0, timestamp: str = TIMESTAMP) -> dict:
    return {"timestamp": timestamp, "data": {"symbol": "^XSP", "current_price": cena, "iv30": 14.6, "options": opcje}}


def _symbole(przyciety: dict) -> set[str]:
    return {o["option"] for o in przyciety["data"]["options"]}


def _yahoo(ticker: str = "SPY", punkty: int = 3) -> dict:
    t0 = int(datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc).timestamp())
    return {"chart": {"result": [{
        "meta": {"symbol": ticker, "currency": "USD", "regularMarketPrice": 100.123456, "chartPreviousClose": 50.0, "pole_obce": 1},
        "timestamp": [t0 + i * 86400 for i in range(punkty)],
        "indicators": {"quote": [{"open": [1.123456789] * punkty, "high": [2.5] * punkty, "low": [1.0] * punkty, "close": [2.0] * punkty,
                                  "volume": [1000] * punkty}], "adjclose": [{"adjclose": [2.0] * punkty}]},
    }], "error": None}}


# ---------------------------------------------------------------------------
# przycinanie łańcucha opcji
# ---------------------------------------------------------------------------
def test_przycinanie_lancucha_stosuje_regule_terminow_okna_strike_i_siatki():
    za10, za60 = DZIEN + timedelta(days=10), DZIEN + timedelta(days=60)
    opcje = {
        "call_blisko_gesty": _opcja(za10, "C", 701),      # calle 98%-110% ceny i do 45 dni: wszystkie strike'i
        "call_blisko_na_siatce": _opcja(za10, "C", 700),
        "put_poza_siatka": _opcja(za10, "P", 701),        # puty tylko na siatce co 5 punktów
        "put_na_siatce": _opcja(za10, "P", 700),
        "call_daleki_termin_poza_siatka": _opcja(za60, "C", 701),   # po 45 dniach też tylko siatka
        "call_daleki_termin_na_siatce": _opcja(za60, "C", 705),
        "call_ponizej_gestej_strefy_na_siatce": _opcja(za10, "C", 675),   # 675 < 98% ceny, ale leży na siatce
        "call_ponizej_gestej_strefy_poza_siatka": _opcja(za10, "C", 676),
        "call_poza_oknem_dol": _opcja(za10, "C", 600),    # poniżej 88% ceny
        "call_poza_oknem_gora": _opcja(za10, "C", 800),   # powyżej 112% ceny
        "call_za_daleki_termin": _opcja(DZIEN + timedelta(days=101), "C", 700),
        "call_wygasly": _opcja(DZIEN - timedelta(days=1), "C", 700),
        "call_wygasa_dzis": _opcja(DZIEN, "C", 700),
    }
    zostaja = _symbole(pp.przytnij_lancuch(_lancuch(list(opcje.values()))))
    oczekiwane = {"call_blisko_gesty", "call_blisko_na_siatce", "put_na_siatce", "call_daleki_termin_na_siatce",
                  "call_ponizej_gestej_strefy_na_siatce", "call_wygasa_dzis"}
    assert {nazwa for nazwa, o in opcje.items() if o["option"] in zostaja} == oczekiwane


def test_przycinanie_lancucha_zostawia_naglowek_i_tylko_pola_czytane_przez_karte():
    wynik = pp.przytnij_lancuch(_lancuch([_opcja(DZIEN + timedelta(days=5), "C", 700)]))
    assert wynik["timestamp"] == TIMESTAMP
    assert (wynik["data"]["current_price"], wynik["data"]["iv30"], wynik["data"]["symbol"]) == (700.0, 14.6, "^XSP")
    (opcja,) = wynik["data"]["options"]
    assert set(opcja) == set(pp.OPCJA_POLA) and "pole_obce" not in opcja


def test_siatka_strike_zalezy_od_poziomu_indeksu():
    termin = DZIEN + timedelta(days=60)
    male = _lancuch([_opcja(termin, "P", 270, root="XND"), _opcja(termin, "P", 271, root="XND")], cena=277.4)   # poniżej 400 pkt: co 2
    assert _symbole(pp.przytnij_lancuch(male)) == {_opcja(termin, "P", 270, root="XND")["option"]}


def test_przycinanie_lancucha_odrzuca_zle_odpowiedzi():
    with pytest.raises(RuntimeError, match="nieoczekiwana odpowiedź"):
        pp.przytnij_lancuch({"timestamp": TIMESTAMP, "data": {"current_price": 700.0}})
    with pytest.raises(RuntimeError, match="nieoczekiwana odpowiedź"):
        pp.przytnij_lancuch(_lancuch([], cena=0.0))
    with pytest.raises(RuntimeError, match="nie zostały żadne opcje"):
        pp.przytnij_lancuch(_lancuch([_opcja(DZIEN - timedelta(days=3), "C", 700)]))


# ---------------------------------------------------------------------------
# przycinanie notowań i zapis
# ---------------------------------------------------------------------------
def test_przycinanie_notowan_zostawia_swiece_i_wybrane_pola_meta():
    wynik = pp.przytnij_notowania(_yahoo())
    r = wynik["chart"]["result"][0]
    assert wynik["chart"]["error"] is None
    assert set(r["indicators"]["quote"][0]) == {"open", "high", "low", "close"}, "wolumen i skorygowane zamknięcia karty nie czytają"
    assert r["indicators"]["quote"][0]["open"][0] == 1.1235, "ceny zaokrąglone do 4 miejsc"
    assert "pole_obce" not in r["meta"] and r["meta"]["symbol"] == "SPY" and r["meta"]["regularMarketPrice"] == 100.123456
    assert len(r["timestamp"]) == 3


def test_przycinanie_notowan_odrzuca_pusta_odpowiedz():
    with pytest.raises(RuntimeError, match="pusta odpowiedź"):
        pp.przytnij_notowania({"chart": {"result": None, "error": {"code": "Not Found"}}})


def test_nazwa_pliku_zamienia_znaki_specjalne_na_podkreslenie():
    assert pp.nazwa_pliku("quote", "^XSP") == "quote-_XSP.json"
    assert pp.nazwa_pliku("options", "_XND") == "options-_XND.json"
    assert pp.nazwa_pliku("quote", "BRK-B") == "quote-BRK_B.json"


def test_zapis_probek_z_podstawionym_pobieraniem(tmp_path):
    """Cały przebieg bez sieci: pobranie, przycięcie, zapis plików i spisu z dokładnymi liczbami."""
    opcje = [_opcja(DZIEN + timedelta(days=d), typ, s) for d in (5, 20) for typ in "CP" for s in (690, 700, 710)]

    def pobierz(adres):
        return _lancuch(opcje) if "cboe.com" in adres else _yahoo(ticker=urllib.parse.unquote(adres.split("/chart/")[1].split("?")[0]))

    teraz = datetime(2026, 11, 11, 13, 47, 47, tzinfo=timezone.utc)
    spis = pp.pobierz_i_zapisz(tmp_path / "przyklad", pobierz=pobierz, teraz=teraz)
    assert spis["pobrano"] == "2026-11-11T13:47:47Z"
    assert set(spis["notowania"]) == set(pp.NOTOWANIA) and set(spis["lancuchy"]) == set(pp.LANCUCHY)
    zapisane = {p.name for p in (tmp_path / "przyklad").iterdir()}
    assert zapisane == {"indeks.json", *(w["plik"] for w in spis["notowania"].values()), *(w["plik"] for w in spis["lancuchy"].values())}
    assert json.loads((tmp_path / "przyklad" / "indeks.json").read_text(encoding="utf-8")) == spis
    assert spis["notowania"]["^XSP"]["punktow"] == 3 and spis["lancuchy"]["_XSP"]["opcji"] == 12
    assert all(w["plik"].startswith("quote-") for w in spis["notowania"].values())


# ---------------------------------------------------------------------------
# zatwierdzone pliki w data/przyklad/
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def katalog(korzen):
    return korzen / "data" / "przyklad"


@pytest.fixture(scope="module")
def spis(katalog):
    return json.loads((katalog / "indeks.json").read_text(encoding="utf-8"))


def _json(katalog, plik):
    return json.loads((katalog / plik).read_text(encoding="utf-8"))


def test_spis_probek_zgadza_sie_z_plikami_w_katalogu(katalog, spis):
    assert spis["wersja"] == 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", spis["pobrano"])
    wpisy = [*spis["notowania"].values(), *spis["lancuchy"].values()]
    assert {p.name for p in katalog.iterdir()} == {"indeks.json", *(w["plik"] for w in wpisy)}, "w katalogu są pliki spoza spisu albo brakuje plików"
    for w in wpisy:
        assert (katalog / w["plik"]).stat().st_size < 1_000_000, f"{w['plik']} jest za duży na próbkę"


def test_notowania_maja_rosnace_znaczniki_rowne_tablice_i_dodatnie_ceny(katalog, spis):
    for ticker, wpis in spis["notowania"].items():
        r = _json(katalog, wpis["plik"])["chart"]["result"][0]
        ts, swiece = r["timestamp"], r["indicators"]["quote"][0]
        assert r["meta"]["symbol"] == ticker
        assert len(ts) == wpis["punktow"] > 0
        assert all(a < b for a, b in zip(ts, ts[1:])), f"{ticker}: znaczniki czasu nie rosną"
        assert set(swiece) == {"open", "high", "low", "close"}
        for nazwa, wartosci in swiece.items():
            assert len(wartosci) == len(ts), f"{ticker}: tablica {nazwa} ma inną długość niż znaczniki"
            assert all(x is None or x > 0 for x in wartosci), f"{ticker}: niedodatnia cena w {nazwa}"
        assert datetime.fromtimestamp(ts[0], timezone.utc).strftime("%Y-%m-%d") == wpis["od"]
        assert datetime.fromtimestamp(ts[-1], timezone.utc).strftime("%Y-%m-%d") == wpis["do"]
        ostatnie = [x for x in swiece["close"] if x is not None][-1]
        assert abs(r["meta"]["regularMarketPrice"] / ostatnie - 1) < 0.05, f"{ticker}: cena z meta odbiega od ostatniego zamknięcia"


def test_lancuchy_maja_poprawne_symbole_terminy_strike_i_pola(katalog, spis):
    for symbol, wpis in spis["lancuchy"].items():
        surowe = _json(katalog, wpis["plik"])
        dane, dzien = surowe["data"], pp.data_migawki(surowe["timestamp"])
        cena = dane["current_price"]
        assert cena > 0 and wpis["opcji"] == len(dane["options"]) > 100
        for o in dane["options"]:
            m = pp.SYMBOL_OPCJI.match(o["option"])
            assert m, f"{symbol}: zły symbol opcji {o['option']}"
            termin = date(2000 + int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:6]))
            assert 0 <= (termin - dzien).days <= pp.MAKS_DNI, f"{o['option']}: termin poza zakresem próbki"
            strike = int(m.group(4)) / 1000
            assert cena * pp.OKNO_STRIKE[0] <= strike <= cena * pp.OKNO_STRIKE[1], f"{o['option']}: strike poza oknem"
            assert set(pp.OPCJA_POLA) - {"last_trade_time"} <= set(o), f"{o['option']}: brakuje pól"
            assert 0 <= o["bid"] <= o["ask"], f"{o['option']}: bid {o['bid']}, ask {o['ask']}"


def test_cena_lancucha_zgadza_sie_z_cena_indeksu_z_notowan(katalog, spis):
    """Łańcuch i notowanie tego samego indeksu pochodzą z jednej sesji, więc ceny muszą być bliskie."""
    for symbol, wpis in spis["lancuchy"].items():
        ticker = "^" + symbol.lstrip("_")
        cena_indeksu = _json(katalog, spis["notowania"][ticker]["plik"])["chart"]["result"][0]["meta"]["regularMarketPrice"]
        assert abs(wpis["cena"] / cena_indeksu - 1) < 0.02, f"{symbol}: {wpis['cena']} wobec {cena_indeksu} dla {ticker}"


def test_probki_obejmuja_to_czego_potrzebuja_karty(korzen, spis):
    """Profile przykładowe Pozycji (ETF, indeks, historia, łańcuch) i ticker domyślny VaR muszą mieć próbki, inaczej karta pokaże błąd."""
    pozycja = (korzen / "src" / "pozycja" / "pozycja.py").read_text(encoding="utf-8")
    profile = re.findall(r"\{ \.\.\.PZ_PROFIL_PUSTY, id: \"[^\"]+\"[^}]*\}", pozycja)
    assert len(profile) >= 2, "nie znaleziono profili przykładowych w kodzie Pozycji"
    for profil in profile:
        pola = dict(re.findall(r'(\w+): "([^"]*)"', profil))
        for klucz in ("etf", "indeks", "indeksHistoria"):
            assert pola[klucz] in spis["notowania"], f"brak próbki notowań {pola[klucz]} dla pola {klucz} profilu {pola['id']}"
        assert pola["cboe"] in spis["lancuchy"], f"brak próbki łańcucha {pola['cboe']} profilu {pola['id']}"
        assert spis["notowania"][pola["indeksHistoria"]]["punktow"] >= 250, "historia do zmienności zrealizowanej potrzebuje roku sesji"
    var = (korzen / "src" / "var" / "var.py").read_text(encoding="utf-8")
    domyslny = re.search(r'id="v-ticker" type="text" value="([^"]+)"', var).group(1)
    assert spis["notowania"][domyslny]["punktow"] >= 1000, "VaR z oknami po 756 dni potrzebuje co najmniej kilku lat sesji"
