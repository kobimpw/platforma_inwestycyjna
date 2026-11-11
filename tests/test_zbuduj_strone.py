"""Budowa statycznej strony (src/narzedzia/zbuduj_strone.py): do _site/ trafia dokładnie to, co ma trafić, i nic więcej.

Strona jest publikowana na GitHub Pages przez workflow, który woła ten skrypt, więc błąd w liście plików oznaczałby albo
pustą stronę dla rekrutera, albo opublikowanie czegoś, czego nie planowaliśmy. Dlatego lista jest jawna (dozwolone
pliki danych i dozwolone typy plików), a testy pilnują obu kierunków."""

import pytest

import zbuduj_strone as zs


def test_strona_sklada_sie_i_ma_wszystkie_wymagane_pliki(tmp_path):
    wynik = zs.zbuduj(tmp_path / "_site")
    for wzgledna in zs.WYMAGANE:
        assert (tmp_path / "_site" / wzgledna).is_file(), wzgledna
    assert (tmp_path / "_site" / ".nojekyll").is_file()
    assert wynik["plikow"] > 10 and wynik["rozmiar_kb"] > 0


def test_do_strony_trafiaja_tylko_dozwolone_pliki_danych(tmp_path, korzen):
    """Archiwa pomocnicze (put/call, opcje SPX, historia) służą SQL i skryptowi aktualizującemu, a nie przeglądarce.

    Poza dwoma plikami Stanu rynku idą tylko próbki .json z katalogów wymienionych w DANE_KATALOGI_DLA_STRONY."""
    zs.zbuduj(tmp_path / "_site")
    dane = tmp_path / "_site" / "data"
    opublikowane = sorted(str(p.relative_to(dane)) for p in dane.rglob("*") if p.is_file())
    probki = [f"{k}/{p.name}" for k in zs.DANE_KATALOGI_DLA_STRONY for p in (korzen / "data" / k).glob("*.json")]
    assert opublikowane == sorted([*zs.DANE_DLA_STRONY, *probki])


def test_w_stronie_nie_ma_kodu_pythona_baz_ani_nagran(tmp_path):
    zs.zbuduj(tmp_path / "_site")
    niedozwolone = {".py", ".sqlite", ".db", ".md", ".csv", ".webm", ".mp3", ".m4a", ".mp4", ".wav", ".pdf", ".ipynb", ".yml"}
    znalezione = [str(p.relative_to(tmp_path)) for p in (tmp_path / "_site").rglob("*") if p.is_file() and p.suffix.lower() in niedozwolone]
    assert znalezione == []


def test_kazda_strona_karty_laduje_wspolne_pliki_z_istniejacych_sciezek(tmp_path):
    """Po złożeniu każdy <script src> i <link href> w stronach prowadzi do pliku, który jest w _site/."""
    import re
    zs.zbuduj(tmp_path / "_site")
    korzen = tmp_path / "_site"
    zle = []
    for strona in sorted(korzen.rglob("index.html")):
        for odwolanie in re.findall(r'(?:src|href)="([^"#?]+\.(?:js|css|json))"', strona.read_text(encoding="utf-8")):
            if odwolanie.startswith(("http:", "https:", "data:")):
                continue
            if not (strona.parent / odwolanie).resolve().is_file():
                zle.append(f"{strona.relative_to(korzen)}: {odwolanie}")
    assert zle == []


def test_budowa_odrzuca_niedozwolony_typ_pliku(tmp_path):
    web = tmp_path / "web"
    (web / "karta").mkdir(parents=True)
    (web / "karta" / "nagranie.mp3").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="niedozwolony typ pliku"):
        zs.zbuduj(tmp_path / "_site", web=web, dane=tmp_path / "data")


def test_budowa_zglasza_brak_probek_dla_kart(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    dane = tmp_path / "data"
    for wzgledna in zs.DANE_DLA_STRONY:
        (dane / wzgledna).parent.mkdir(parents=True, exist_ok=True)
        (dane / wzgledna).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="brak plików .json w data/przyklad"):
        zs.zbuduj(tmp_path / "_site", web=web, dane=dane)


def test_budowa_zglasza_brak_pliku_danych(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="brak pliku danych"):
        zs.zbuduj(tmp_path / "_site", web=web, dane=tmp_path / "data")
