# pandas
Język: Python
Kategoria: Dane i obliczenia
Status: w użyciu
Pakiet: pandas
Strona: https://pandas.pydata.org
Gdzie w projekcie: src/stan_rynku/stan_rynku.py, src/var/var.py
W requirements.txt: tak (wersja przypięta)

pandas to podstawowe narzędzie do pracy z danymi tabelarycznymi: jego główny obiekt, `DataFrame`, działa jak arkusz kalkulacyjny w pamięci, w którym każda kolumna ma nazwę i typ, a wiersze można filtrować, sortować, łączyć i grupować jednym poleceniem.
W tym projekcie służy do wszystkiego, co przypomina tabelę: notowania z Yahoo Finance, serie makroekonomiczne z FRED, historia VIX i wskaźniki karty Stan rynku.
Możesz go używać, gdy chcesz szybko przeliczyć kolumnę na podstawie innych (np. zwroty z cen), połączyć dwa zestawy danych po wspólnym kluczu albo policzyć średnią kroczącą bez pisania pętli.
Zasada praktyczna: jeśli dane mają kształt tabeli, najpierw pomyśl o pandas, a dopiero potem o własnych pętlach.
