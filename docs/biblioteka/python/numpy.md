# numpy
Język: Python
Kategoria: Dane i obliczenia
Status: w użyciu
Pakiet: numpy
Strona: https://numpy.org
Gdzie w projekcie: src/stan_rynku/stan_rynku.py
W requirements.txt: tak (przypięta jawnie; numpy 2.4.x to ostatnia linia z obsługą Pythona 3.11)

numpy to biblioteka szybkich obliczeń na tablicach liczb: zamiast liczyć element po elemencie w pętli, wykonujesz działanie na całej tablicy naraz, co jest wielokrotnie szybsze i krótsze w zapisie.
To właśnie numpy stoi „pod spodem" pandas, więc kolumna `DataFrame` jest w gruncie rzeczy tablicą numpy.
W projekcie liczy zmienność zrealizowaną, średnie Wildera (podstawa RSI i ADX) oraz punktację wskaźników według progów, a będzie naturalnym wyborem przy rachunku ryzyka: odchylenie standardowe, korelacje, symulacje Monte Carlo czy generowanie losowych ścieżek cen.
Gdy widzisz w kodzie pętlę po liczbach, zwykle da się ją zastąpić jednym działaniem numpy.
