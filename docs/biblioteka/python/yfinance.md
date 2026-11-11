# yfinance
Język: Python
Kategoria: Dane rynkowe
Status: w użyciu
Pakiet: yfinance
Strona: https://github.com/ranaroussi/yfinance
Gdzie w projekcie: src/var/var.py (funkcja pobierająca notowania do rachunku VaR)
W requirements.txt: nie w requirements.txt, tak w requirements-tools.txt (wersja przypięta)

yfinance to nieoficjalna biblioteka, która pobiera z Yahoo Finance notowania historyczne, dane o spółkach i łańcuchy opcji, zwracając je od razu jako `DataFrame` z pandas.
W projekcie dostarcza ceny do liczenia VaR (ryzyka strat). Karta Stan rynku z niej nie korzysta, bo notowania dla swoich wskaźników bierze przez własne proxy.
Pamiętaj, że to „nieoficjalne" źródło: Yahoo może zmienić format lub zablokować zapytania, więc do rzeczy ważnych warto mieć plan awaryjny.
Użyj jej, gdy potrzebujesz historii cen dowolnego tickera bez zakładania konta ani klucza API.
