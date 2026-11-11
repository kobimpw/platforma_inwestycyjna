# Lightweight Charts (TradingView)
Język: JavaScript
Kategoria: Wykresy
Status: w użyciu
Pakiet: lightweight-charts 5.2.1 (kopia pliku z pakietu npm dołączona do repozytorium, bez CDN)
Strona: https://tradingview.github.io/lightweight-charts/
Gdzie w projekcie: web/VaR/ (wykres cen i progów VaR, generowany z src/var/var.py); plik biblioteki w web/shared/vendor/
W requirements.txt: nie dotyczy (to biblioteka przeglądarkowa)

Lightweight Charts to darmowa biblioteka TradingView do rysowania wykresów finansowych w przeglądarce: liniowych, słupkowych, świecowych i histogramów, szybkich nawet przy tysiącach punktów.
W projekcie rysuje na karcie VaR świece cen i trzy linie progów ryzyka z interaktywną osią czasu. Wersja jest przypięta na stałe (5.2.1) i dołączona do repozytorium w katalogu `web/shared/vendor/` razem z licencją, żeby strona nie zależała od zewnętrznego serwera ani od tego, czy sieć odwiedzającego go przepuszcza.
Użyj jej, gdy potrzebujesz profesjonalnego wykresu z osią czasu, przybliżaniem i kursorem, bez pisania własnego rysowania na `canvas`. Licencja to Apache 2.0, a wykres domyślnie pokazuje znak TradingView.
Nie jest to biblioteka do dowolnych wykresów (kołowych, radarowych), do takich potrzebna byłaby inna.
