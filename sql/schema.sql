-- Schemat bazy analitycznej projektu (SQLite).
--
-- Baza jest POCHODNA: buduje ją polecenie `python src/baza/baza.py zbuduj` (albo `make db`) z plików w data/,
-- więc plik .sqlite nie trafia do repozytorium. Źródłem prawdy są pliki tekstowe zapisywane przez potoki
-- (JSON i CSV dają w gicie czytelne różnice, a plik binarny bazy powiększałby repozytorium przy każdym commicie).
--
-- Model: wymiary (słowniki, rzadko się zmieniają) i fakty (dzienne obserwacje). Każda tabela
-- faktów ma klucz główny z daty, więc ten sam dzień nie może wystąpić dwa razy; ograniczenia CHECK pilnują
-- zakresów, a klucze obce spójności z wymiarami.

PRAGMA foreign_keys = ON;

-- ===================================================================== wymiary
CREATE TABLE wskaznik (
    id        TEXT PRIMARY KEY,
    grupa     TEXT NOT NULL CHECK (grupa IN ('makro', 'rynek', 'technika')),
    nazwa     TEXT NOT NULL,
    oceniany  INTEGER NOT NULL CHECK (oceniany IN (0, 1)),   -- 1 = wchodzi do sygnału rynku
    waga      REAL,
    maks      INTEGER                 -- największa liczba punktów, jaką wskaźnik może dać (w obie strony)
);

-- ===================================================================== fakty: opcje
CREATE TABLE put_call_dzienne (
    data           TEXT PRIMARY KEY,
    calkowity      REAL,        -- wskaźnik put/call dla całej giełdy (Cboe)
    indeksy        REAL,
    etp            REAL,
    akcje          REAL,
    spx            REAL,
    akcje_call     INTEGER,
    akcje_put      INTEGER,
    indeksy_call   INTEGER,
    indeksy_put    INTEGER
);

CREATE TABLE opcje_spx_dzienne (
    data         TEXT PRIMARY KEY,
    gex_mld_usd  REAL,          -- ekspozycja gamma dealerów, mld USD
    skos_25d     REAL,          -- skośność zmienności (25-delta)
    pc_oi_60     REAL,          -- put/call z otwartych pozycji, terminy do 60 dni
    iv30         REAL,          -- zmienność implikowana, 30 dni
    iv90         REAL,
    spx          REAL
);

-- ===================================================================== fakty: sygnał rynku i wskaźniki
-- Historia ODTWORZONA: liczona dziś według dzisiejszych progów, więc zna przyszłość względem dawnych dni.
-- Dobra do opisu, ale nie do uczciwego sprawdzania skuteczności poza próbą (patrz sygnal_zapisany).
CREATE TABLE sygnal_odtworzony (
    data       TEXT PRIMARY KEY,
    wynik      REAL NOT NULL CHECK (wynik BETWEEN -100 AND 100),
    makro      REAL,
    rynek      REAL,
    technika   REAL,
    nastroje   REAL,
    spx        REAL NOT NULL CHECK (spx > 0)
);

CREATE TABLE wskaznik_odczyt (
    wskaznik_id  TEXT NOT NULL REFERENCES wskaznik (id),
    data         TEXT NOT NULL,
    wartosc      REAL NOT NULL,
    PRIMARY KEY (wskaznik_id, data)
) WITHOUT ROWID;

-- Historia ZAPISANA na bieżąco (data/historia/*.csv, dopisywana codziennie przez `baza.py archiwizuj`):
-- co karta pokazywała w danym dniu, przy ówczesnych progach. Tylko ona nadaje się do oceny poza próbą.
CREATE TABLE sygnal_zapisany (
    data       TEXT PRIMARY KEY,
    wynik      REAL NOT NULL CHECK (wynik BETWEEN -100 AND 100),
    poziom     TEXT NOT NULL,
    makro      REAL,
    rynek      REAL,
    technika   REAL,
    nastroje   REAL,
    spx        REAL
);

CREATE TABLE wskaznik_zapisany (
    data         TEXT NOT NULL,
    wskaznik_id  TEXT NOT NULL REFERENCES wskaznik (id),
    punkty       INTEGER,
    percentyl    REAL,
    stan         TEXT,
    PRIMARY KEY (data, wskaznik_id)
) WITHOUT ROWID;
