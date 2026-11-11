"""Baza analityczna (SQLite) zbudowana z plików w data/ oraz archiwizator dziennej historii.

Po co baza, skoro karty czytają pliki JSON? Karty pokazują stan na dziś, a historia rośnie z każdym dniem:
tabele z `cboe-putcall.json` i `opcje-spx.json` już dziś są dopisywane codziennie, a archiwizator poniżej
zaczyna zapisywać to, co karta „Stan rynku" pokazywała w danym dniu (sygnał i punkty każdego wskaźnika). Tego
nie da się odtworzyć wstecz, bo progi i reguły będą się zmieniać. Do pytań o historię SQL jest wygodniejszy
niż pętle w Pythonie: zapytania leżą w sql/widoki.sql, a schemat w sql/schema.sql.

Zasada: źródłem prawdy są pliki tekstowe w data/ (w gicie dają czytelne różnice), a baza jest POCHODNA i budowana
od zera, więc zawsze odpowiada plikom i nie trafia do repozytorium (plik binarny powiększałby je z każdym commitem).

Polecenia (z korzenia repozytorium):
  python src/baza/baza.py zbuduj [plik.sqlite]   buduje bazę od zera z data/ (domyślnie data/platforma.sqlite)
  python src/baza/baza.py zapytanie NAZWA        wypisuje tabelę albo widok, np. v_skutecznosc_sygnalu, v_swiezosc_danych
  python src/baza/baza.py swiezosc               ostatnia data i liczba wierszy w każdej tabeli faktów (monitoring)
  python src/baza/baza.py archiwizuj             dopisuje migawkę sygnału i wskaźników z data/stan-rynku/stan.json
                                                 do data/historia/*.csv (wołane po aktualizacji danych Stanu rynku)
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[2]
DANE = KORZEN / "data"
SQL = KORZEN / "sql"
DOMYSLNA_BAZA = DANE / "platforma.sqlite"
KATALOG_HISTORII = DANE / "historia"

KOLUMNY_SYGNALU = ["data", "wynik", "poziom", "makro", "rynek", "technika", "nastroje", "spx"]
KOLUMNY_WSKAZNIKOW = ["data", "wskaznik_id", "punkty", "percentyl", "stan"]

# nazwy pól w plikach JSON (camelCase) -> nazwy kolumn w bazie (snake_case)
MAPA_PUT_CALL = {"data": "data", "calkowity": "calkowity", "indeksy": "indeksy", "etp": "etp", "akcje": "akcje", "spx": "spx",
                 "akcjeCall": "akcje_call", "akcjePut": "akcje_put", "indeksyCall": "indeksy_call", "indeksyPut": "indeksy_put"}
MAPA_OPCJE_SPX = {"data": "data", "gexMldUsd": "gex_mld_usd", "skos25d": "skos_25d", "pcOi60": "pc_oi_60", "iv30": "iv30",
                  "iv90": "iv90", "spx": "spx"}


# ===========================================================================
# magazyn funkcji: wczytywanie plików i ładowanie tabel
# ===========================================================================
def _json(sciezka: Path):
    return json.loads(sciezka.read_text(encoding="utf-8"))


def _liczba(wartosc):
    """Pusty tekst lub brak wartości -> None, w przeciwnym razie liczba (z CSV wszystko wraca jako tekst)."""
    if wartosc is None or wartosc == "":
        return None
    return float(wartosc)


def polacz(sciezka: str | Path = ":memory:") -> sqlite3.Connection:
    polaczenie = sqlite3.connect(str(sciezka))
    polaczenie.row_factory = sqlite3.Row
    polaczenie.execute("PRAGMA foreign_keys = ON")
    return polaczenie


def utworz_schemat(polaczenie: sqlite3.Connection, sql: Path = SQL) -> None:
    polaczenie.executescript((sql / "schema.sql").read_text(encoding="utf-8"))
    polaczenie.executescript((sql / "widoki.sql").read_text(encoding="utf-8"))


def _wstaw_tabele(polaczenie: sqlite3.Connection, tabela: str, kolumny_json: list[str], wiersze: list[list], mapa: dict[str, str]) -> int:
    """Wstawia tabelę zapisaną w JSON jako {kolumny: [...], wiersze: [[...], ...]} według mapy nazw kolumn."""
    indeksy = [(kolumny_json.index(pole), kolumna) for pole, kolumna in mapa.items() if pole in kolumny_json]
    kolumny_sql = ", ".join(k for _, k in indeksy)
    znaki = ", ".join("?" for _ in indeksy)
    polaczenie.executemany(f"INSERT INTO {tabela} ({kolumny_sql}) VALUES ({znaki})", [tuple(w[i] for i, _ in indeksy) for w in wiersze])
    return len(wiersze)


def zaladuj_opcje(polaczenie: sqlite3.Connection, dane: Path = DANE) -> dict:
    put_call = _json(dane / "stan-rynku" / "cboe-putcall.json")
    opcje = _json(dane / "stan-rynku" / "opcje-spx.json")
    return {
        "put_call_dzienne": _wstaw_tabele(polaczenie, "put_call_dzienne", put_call["kolumny"], put_call["wiersze"], MAPA_PUT_CALL),
        "opcje_spx_dzienne": _wstaw_tabele(polaczenie, "opcje_spx_dzienne", opcje["kolumny"], opcje["wiersze"], MAPA_OPCJE_SPX),
    }


def zaladuj_stan_rynku(polaczenie: sqlite3.Connection, dane: Path = DANE) -> dict:
    """Wymiar `wskaznik`, odczyty wskaźników i historia sygnału odtworzona dziś (stan.json)."""
    stan = _json(dane / "stan-rynku" / "stan.json")
    polaczenie.executemany(
        "INSERT INTO wskaznik (id, grupa, nazwa, oceniany, waga, maks) VALUES (?, ?, ?, ?, ?, ?)",
        [(w["id"], w["grupa"], w["nazwa"], int(bool(w["oceniany"])), w.get("waga"), w.get("maks")) for w in stan["wskazniki"]])
    polaczenie.executemany("INSERT INTO wskaznik_odczyt (wskaznik_id, data, wartosc) VALUES (?, ?, ?)",
                           [(w["id"], d, v) for w in stan["wskazniki"] for d, v in (w.get("historia") or []) if v is not None])
    h = stan["historia"]
    odtworzony = _wstaw_tabele(polaczenie, "sygnal_odtworzony", h["kolumny"], h["dzienna"],
                               {k: k for k in ("data", "wynik", "makro", "rynek", "technika", "nastroje", "spx")})
    return {"wskaznikow": len(stan["wskazniki"]), "sygnal_odtworzony": odtworzony}


def zaladuj_historie_zapisana(polaczenie: sqlite3.Connection, katalog: Path = KATALOG_HISTORII) -> dict:
    """Tabele `sygnal_zapisany` i `wskaznik_zapisany` z plików CSV dopisywanych przez `archiwizuj` (mogą jeszcze nie istnieć)."""
    wynik = {"sygnal_zapisany": 0, "wskaznik_zapisany": 0}
    plik = katalog / "sygnal_zapisany.csv"
    if plik.is_file():
        with plik.open(encoding="utf-8", newline="") as f:
            wiersze = [(w["data"], _liczba(w["wynik"]), w["poziom"], _liczba(w["makro"]), _liczba(w["rynek"]), _liczba(w["technika"]),
                        _liczba(w["nastroje"]), _liczba(w["spx"])) for w in csv.DictReader(f)]
        polaczenie.executemany("INSERT INTO sygnal_zapisany (data, wynik, poziom, makro, rynek, technika, nastroje, spx) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", wiersze)
        wynik["sygnal_zapisany"] = len(wiersze)
    plik = katalog / "wskaznik_zapisany.csv"
    if plik.is_file():
        with plik.open(encoding="utf-8", newline="") as f:
            wiersze = [(w["data"], w["wskaznik_id"], None if w["punkty"] == "" else int(float(w["punkty"])), _liczba(w["percentyl"]),
                        w["stan"] or None) for w in csv.DictReader(f)]
        polaczenie.executemany("INSERT INTO wskaznik_zapisany (data, wskaznik_id, punkty, percentyl, stan) VALUES (?, ?, ?, ?, ?)", wiersze)
        wynik["wskaznik_zapisany"] = len(wiersze)
    return wynik


def _upsert_csv(sciezka: Path, kolumny: list[str], klucz: list[str], nowe: list[dict]) -> tuple[int, int]:
    """Dopisuje wiersze do pliku CSV według klucza: nowy klucz dodaje wiersz, istniejący zastępuje go (ponowne
    uruchomienie tego samego dnia nie dubluje danych). Plik zapisywany posortowany, więc w gicie zmienia się tylko
    dopisany fragment. Zwraca (liczba dodanych, liczba zmienionych)."""
    istniejace: dict[tuple, dict] = {}
    if sciezka.is_file():
        with sciezka.open(encoding="utf-8", newline="") as f:
            for w in csv.DictReader(f):
                istniejace[tuple(w[k] for k in klucz)] = w
    dodane = zmienione = 0
    for w in nowe:
        zapis = {k: ("" if w.get(k) is None else str(w[k])) for k in kolumny}
        k = tuple(zapis[x] for x in klucz)
        if k not in istniejace:
            dodane += 1
        elif istniejace[k] != zapis:
            zmienione += 1
        istniejace[k] = zapis
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    with sciezka.open("w", encoding="utf-8", newline="") as f:
        zapisujacy = csv.DictWriter(f, fieldnames=kolumny, lineterminator="\n")
        zapisujacy.writeheader()
        zapisujacy.writerows(istniejace[k] for k in sorted(istniejace))
    return dodane, zmienione


def archiwizuj(stan_json: Path = DANE / "stan-rynku" / "stan.json", katalog: Path = KATALOG_HISTORII) -> dict:
    """Dopisuje do historii zapisanej na bieżąco sygnał i punkty wszystkich wskaźników z sesji ze stan.json."""
    stan = _json(stan_json)
    dzien = stan["sesja"]
    grupy = {g["nazwa"].lower(): g["wynik"] for g in stan["sygnal"]["grupy"]}
    sygnal = {"data": dzien, "wynik": stan["sygnal"]["wynik"], "poziom": stan["sygnal"]["poziom"], "makro": grupy.get("makro"),
              "rynek": grupy.get("rynek"), "technika": grupy.get("technika"), "nastroje": (stan.get("nastroje") or {}).get("wartosc"),
              "spx": stan.get("spx")}
    wskazniki = [{"data": dzien, "wskaznik_id": w["id"], "punkty": w.get("punkty"), "percentyl": w.get("percentyl"), "stan": w.get("stan")}
                 for w in stan["wskazniki"]]
    d1, z1 = _upsert_csv(katalog / "sygnal_zapisany.csv", KOLUMNY_SYGNALU, ["data"], [sygnal])
    d2, z2 = _upsert_csv(katalog / "wskaznik_zapisany.csv", KOLUMNY_WSKAZNIKOW, ["data", "wskaznik_id"], wskazniki)
    return {"sesja": dzien, "sygnal_dodane": d1, "sygnal_zmienione": z1, "wskazniki_dodane": d2, "wskazniki_zmienione": z2}


# ===========================================================================
# orkiestratory
# ===========================================================================
def zbuduj(sciezka: str | Path = ":memory:", dane: Path = DANE, katalog_historii: Path | None = None) -> sqlite3.Connection:
    """Buduje bazę od zera: schemat, widoki i wszystkie tabele z plików. Zwraca otwarte połączenie."""
    if str(sciezka) != ":memory:" and Path(sciezka).exists():
        Path(sciezka).unlink()                 # baza jest pochodna, więc nie łatamy starej, tylko budujemy od nowa
    polaczenie = polacz(sciezka)
    utworz_schemat(polaczenie)
    with polaczenie:                           # jedna transakcja: albo wszystko, albo nic
        zaladuj_opcje(polaczenie, dane)
        zaladuj_stan_rynku(polaczenie, dane)
        zaladuj_historie_zapisana(polaczenie, katalog_historii or dane / "historia")
    return polaczenie


def wypisz(wiersze: list[sqlite3.Row]) -> None:
    if not wiersze:
        print("(brak wierszy)")
        return
    kolumny = wiersze[0].keys()
    tekst = [[("" if w[k] is None else str(w[k])) for k in kolumny] for w in wiersze]
    szerokosci = [max(len(k), *(len(r[i]) for r in tekst)) for i, k in enumerate(kolumny)]
    print("  ".join(k.ljust(szerokosci[i]) for i, k in enumerate(kolumny)))
    print("  ".join("-" * s for s in szerokosci))
    for r in tekst:
        print("  ".join(r[i].ljust(szerokosci[i]) for i in range(len(kolumny))))


def main(argv: list[str]) -> int:
    polecenie = argv[1] if len(argv) > 1 else ""
    if polecenie == "zbuduj":
        sciezka = Path(argv[2]) if len(argv) > 2 else DOMYSLNA_BAZA
        polaczenie = zbuduj(sciezka)
        tabele = [w[0] for w in polaczenie.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        for tabela in tabele:
            print(f"{tabela:20s} {polaczenie.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]:>8d} wierszy")
        print(f"zapisano {sciezka}")
        return 0
    if polecenie == "zapytanie" and len(argv) > 2:
        nazwa = argv[2]
        polaczenie = zbuduj()
        istnieje = polaczenie.execute("SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')", (nazwa,)).fetchone()
        if not re.fullmatch(r"[a-z_0-9]+", nazwa) or not istnieje:
            print(f"nie ma tabeli ani widoku {nazwa!r}")
            return 2
        wypisz(polaczenie.execute(f"SELECT * FROM {nazwa}").fetchall())
        return 0
    if polecenie == "swiezosc":
        wypisz(zbuduj().execute("SELECT * FROM v_swiezosc_danych ORDER BY tabela").fetchall())
        return 0
    if polecenie == "archiwizuj":
        wynik = archiwizuj()
        print("archiwizacja sesji {sesja}: sygnał +{sygnal_dodane}/~{sygnal_zmienione}, wskaźniki +{wskazniki_dodane}/~{wskazniki_zmienione}".format(**wynik))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
