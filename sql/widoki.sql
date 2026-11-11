-- Widoki analityczne (zapisane zapytania) nad tabelami z schema.sql.
--
-- Widok to zapisane zapytanie, które wygląda jak tabela: `SELECT * FROM v_skutecznosc_sygnalu;`. Poniższe odpowiadają na
-- pytania, które stawia sobie inwestor indeksowy. Używają funkcji okna (LEAD, MIN OVER, COUNT OVER), czyli obliczeń
-- po wierszach bez zwijania tabeli. Widoki nie gwarantują kolejności wierszy, więc przy odczycie dodaj ORDER BY.

-- ---------------------------------------------------------------------------------------------------------
-- Co działo się z S&P 500 po sesjach z danym poziomem sygnału? Odpowiednik tabeli skuteczności na karcie
-- „Stan rynku" (src/stan_rynku/stan_rynku.py, funkcja skutecznosc), policzony oknami SQL na historii
-- ODTWORZONEJ. Test tests/test_baza.py sprawdza, że oba rachunki dają ten sam wynik na tych samych danych.
--   r21, r63  zwrot indeksu po 21 i 63 sesjach, %
--   dd63      największe obsunięcie w kolejnych 63 sesjach względem dzisiejszego zamknięcia, % (0, gdy cena nie spadła)
--   p10       odsetek sesji, po których indeks w ciągu 63 sesji spadł o 10% lub więcej
-- Poziomy sygnału wg progów 40, 15, -15, -40 (stan_rynku.POZIOMY).
-- ---------------------------------------------------------------------------------------------------------
CREATE VIEW v_skutecznosc_sygnalu AS
WITH zwroty AS (
    SELECT data, wynik, spx,
           LEAD(spx, 21) OVER (ORDER BY data) AS spx_21,
           LEAD(spx, 63) OVER (ORDER BY data) AS spx_63,
           MIN(spx)   OVER (ORDER BY data ROWS BETWEEN 1 FOLLOWING AND 63 FOLLOWING) AS min_63,
           COUNT(spx) OVER (ORDER BY data ROWS BETWEEN 1 FOLLOWING AND 63 FOLLOWING) AS n_63
    FROM sygnal_odtworzony
),
poziomy AS (
    SELECT CASE WHEN wynik >= 40  THEN 'silnie-pozytywny'
                WHEN wynik >= 15  THEN 'pozytywny'
                WHEN wynik >= -15 THEN 'neutralny'
                WHEN wynik >= -40 THEN 'negatywny'
                ELSE 'silnie-negatywny' END                           AS poziom,
           100.0 * (spx_21 / spx - 1)                                  AS r21,
           100.0 * (spx_63 / spx - 1)                                  AS r63,
           CASE WHEN n_63 = 63 THEN 100.0 * MIN(min_63 / spx - 1, 0) END AS dd63
    FROM zwroty
)
SELECT poziom,
       COUNT(*)                                                                       AS dni,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM sygnal_odtworzony), 1)           AS udzial_proc,
       ROUND(AVG(r21), 2)                                                              AS sr21,
       ROUND(100.0 * AVG(CASE WHEN r21 > 0 THEN 1.0 WHEN r21 IS NOT NULL THEN 0.0 END), 1) AS plus21,
       ROUND(AVG(r63), 2)                                                              AS sr63,
       ROUND(100.0 * AVG(CASE WHEN r63 > 0 THEN 1.0 WHEN r63 IS NOT NULL THEN 0.0 END), 1) AS plus63,
       ROUND(AVG(dd63), 2)                                                             AS dd63,
       ROUND(100.0 * AVG(CASE WHEN dd63 <= -10 THEN 1.0 WHEN dd63 IS NOT NULL THEN 0.0 END), 1) AS p10
FROM poziomy
GROUP BY poziom;

-- ---------------------------------------------------------------------------------------------------------
-- Czy dane napływają? Ostatnia data i liczba wierszy w każdej tabeli faktów (monitoring potoków).
-- ---------------------------------------------------------------------------------------------------------
CREATE VIEW v_swiezosc_danych AS
WITH ostatnie AS (
    SELECT 'put_call_dzienne' AS tabela, COUNT(*) AS wierszy, MAX(data) AS ostatnia_data FROM put_call_dzienne
    UNION ALL
    SELECT 'opcje_spx_dzienne', COUNT(*), MAX(data) FROM opcje_spx_dzienne
    UNION ALL
    SELECT 'sygnal_odtworzony', COUNT(*), MAX(data) FROM sygnal_odtworzony
    UNION ALL
    SELECT 'sygnal_zapisany', COUNT(*), MAX(data) FROM sygnal_zapisany
    UNION ALL
    SELECT 'wskaznik_zapisany', COUNT(*), MAX(data) FROM wskaznik_zapisany
)
SELECT tabela, wierszy, ostatnia_data,
       CAST(julianday('now') - julianday(ostatnia_data) AS INTEGER) AS dni_temu
FROM ostatnie;
