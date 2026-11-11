# Specyfikacja: karta „Stan rynku” (zadanie 037)

Status: ukończona (etap 1, zbudowany 2026-11-01; punkty do decyzji użytkownika w sekcji 9)

**Baner stanu.** Karta `docs/stan-rynku/` („Stan rynku” w szynie nawigacji, zaraz pod „Pozycją”)
działa na realnych danych z 30.10.2026: 54 wskaźniki (27 ocenianych w sygnale, 27
informacyjnych) w trzech grupach, jeden sygnał rynku w skali od -100 do +100 z pięcioma
poziomami, indeks nastrojów, historia sygnału od 2000 r. i jego sprawdzenie na danych. Dane
odświeża raz dziennie skrypt w GitHub Actions, niezależnie od rutyny Claude, która rano pisze
słowną ocenę dnia (pierwszą napisała ta sesja). Otwarte zostają decyzje z sekcji 9; najpilniejsza
jest pierwsza (sekret z kluczem FRED i wymiana klucza, który trafił do repozytorium).

<details>
<summary>1. Audyt polecenia: co było jasne, czego brakowało i jak to rozstrzygnąłem</summary>

Polecenie jasno określa cel (statystyczny stan rynku z kilkunastu do kilkudziesięciu
wskaźników, z jednym sygnałem i opisem), trzy grupy (makro, rynek, technika) z przykładami,
źródło VaR (karta VaR) i podział pracy: dane aktualizuje skrypt raz dziennie, a ocena jest
rutyną Claude. Użytkownik nie mógł odpowiadać na pytania, więc każda luka dostała
rozstrzygnięcie zamiast pytania.

1. **Czyimi oczami oceniać?** Przyjąłem perspektywę inwestora indeksowego S&P 500, tak jak w
   `docs/social/poglad-rynkowy.md`: „pozytywny” znaczy dobre warunki dla trzymania indeksu.
2. **Co ma znaczyć „jasny sygnał”?** Pięć poziomów (silnie pozytywny, pozytywny, neutralny,
   negatywny, silnie negatywny) z wyniku od -100 do +100, czyli te same słowa, którymi karta
   Social opisuje sentyment postów. Sprawdzenie na danych (sekcja 6) pokazało, że sygnał mierzy
   **ryzyko**, a nie przyszły zwrot, i tak jest opisany na karcie.
3. **„Sentyment z danych”.** Obok sygnału powstał osobny indeks nastrojów od 0 (skrajny strach)
   do 100 (skrajna chciwość) z siedmiu składników rynkowych, wzorowany na znanym indeksie strachu
   i chciwości, ale liczony z naszych danych.
4. **„Przy danych o opcjach korzystaj z API i realnych obliczeń” (polecenie z rozmowy).**
   Put/call liczony jest z oficjalnych dziennych statystyk Cboe (wolumeny putów i calli całej
   giełdy, akcji, indeksów i SPX, archiwum od 7.10.2019 zapisane w repozytorium), a ekspozycja
   gamma, skośność 25 delta i put/call z otwartych pozycji z pełnego łańcucha opcji SPX (ok. 28
   tys. kontraktów, API Cboe). Premia za ryzyko to VIX minus zmienność policzona z notowań, a
   percentyl zmienności to pozycja VIX w jego historii z roku.
5. **„Aktualizuj dane raz na dzień, nie uwzględniając twojej rutyny” (polecenie z rozmowy).**
   Dane liczy skrypt `docs/stan-rynku/stan_rynku.py aktualizuj` w workflow
   `stan-rynku-aktualizuj.yml` (dni robocze, 22:40 UTC). Rutyna Claude tylko czyta wynik i pisze
   ocenę; instrukcja zabrania jej uruchamiania aktualizacji.
6. **„VaR weź z zakładki VaR”.** Skrypt importuje funkcję `oblicz_var_kroczaco()` z
   `docs/VaR/VaR.py` i woła ją z domyślnymi parametrami karty (SPY, 99%, okna 756 sesji,
   horyzonty 1 i 21 sesji) na tych samych notowaniach co karta (Yahoo przez Worker). Jedyna zmiana
   w `VaR.py`: import biblioteki `yfinance` przeniesiony do funkcji, która go używa, żeby funkcję
   liczącą dało się zaimportować bez tej biblioteki.
7. **Klucz FRED w opisie zadania.** Klucz nie trafił do kodu: skrypt czyta go ze zmiennej
   `FRED_API_KEY` (sekret repozytorium), a bez niej bierze te same serie z publicznych plików CSV
   FRED, więc wszystko działa od razu. Klucz jest jednak zapisany w `opis.md` zadania, czyli w
   historii gita (sekcja 9).
8. **„Rozważ dalszą część analizy”.** Pierwsza część jest już na karcie (sprawdzenie skuteczności
   sygnału i każdego wskaźnika na historii), kolejne kroki opisuje sekcja 8.

</details>

<details>
<summary>2. Ulepszone polecenie (wersja po audycie)</summary>

```
KONTEKST:  Jestem inwestorem indeksowym S&P 500 (ETF).
           Chcę codziennie wiedzieć, w jakim stanie jest rynek USA, na podstawie danych, a nie
           wrażeń. Klucz API do FRED mam (do sekretu repozytorium).
CEL:       Nowa karta „Stan rynku”: kilkadziesiąt wskaźników makro, rynkowych i technicznych,
           jeden jasny sygnał rynku z opisem, indeks nastrojów z danych i audyt wskaźników.
FORMAT:    Karta w stylu terminala: 1 sygnał (wynik, grupy, nastroje), 2 ocena dnia (opis Claude),
           3–5 listy wskaźników Makro, Rynek, Technika (wartość, ocena, wykresik, rozwinięcie
           z regułą i historią), 6 historia sygnału, 7 skuteczność sygnału, 8 źródła danych.
           Dane liczy raz dziennie skrypt w GitHub Actions, ocenę pisze codzienna rutyna Claude.
ZAŁOŻENIA: [zakładam: perspektywa inwestora indeksowego; pięć poziomów sygnału]
           [zakładam: opcje z API Cboe i własnych obliczeń, VaR funkcją z karty VaR]
           [zakładam: progi to pierwsza kalibracja, sprawdzona na historii od 2000 r.]
           [zakładam: rutyna Claude nie aktualizuje danych, tylko je ocenia]
```

</details>

<details>
<summary>3. Część 1, po ludzku: jak działa karta</summary>

**Okno 1, Sygnał rynku.** Duża etykieta poziomu (np. „Pozytywny”) i wynik w skali od -100 do
+100, pasek pięciu poziomów ze wskazówką, zmiana od poprzedniej sesji, tygodnia i miesiąca, jedno
zdanie z historii („po sesjach z takim sygnałem S&P 500 spadał o 10% lub więcej w ciągu 3 mies.
w 9% przypadków”), wyniki trzech grup i pasek nastrojów od strachu do chciwości. Działa to jak
deska rozdzielcza w samochodzie: jedna wskazówka mówi, czy jedziesz bezpiecznie, a kontrolki
pod nią, która część auta wymaga uwagi.

**Okno 2, Ocena dnia.** Tytuł, kilka zdań opisu, listy „Sprzyja indeksowi” i „Ryzyka” oraz „Na
co patrzeć”, napisane rano przez rutynę Claude. Gdy oceny dla bieżącej sesji jeszcze nie ma, okno
pokazuje opis policzony automatycznie z liczb. Starsze oceny są w archiwum.

**Okna 3–5, Makro, Rynek, Technika.** Każdy wskaźnik to jeden wiersz: kolorowy pasek oceny
(zielony sprzyja indeksowi, szary neutralnie, pomarańczowy ostrzega, czerwony wyraźnie nie
sprzyja), wartość, punkty i wykresik z roku. Kliknięcie rozwija opis „jak czytać”, regułę oceny,
percentyl, źródło z linkiem, wykres z 3 lat i tabelę: jak zachowywał się S&P 500 po sesjach z
każdą oceną tego wskaźnika. Wskaźniki informacyjne (bez oceny) są pod kreską w każdym oknie.

**Okno 6, Historia sygnału.** S&P 500 z kolorowym paskiem poziomu sygnału pod spodem i wykres
samego wyniku z nastrojami; zakresy 1 rok, 3 lata i całość, opcjonalnie linie trzech grup.

**Okno 7, Skuteczność sygnału.** Tabela: po sesjach z każdym poziomem sygnału, jak często
przychodził spadek o 10% w 3 miesiące, jaki był średni zwrot i obsunięcie; trzy okresy do wyboru.

**Okno 8, Źródła danych.** Skąd jest każda liczba, z jakiego dnia, czy ostatnia aktualizacja się
udała i lista błędów, jeśli były.

</details>

<details>
<summary>4. Wskaźniki: audyt, lista, źródła i reguły oceny</summary>

**Z polecenia** (wszystkie są na karcie): PKB i jego tempo (PKB USA oraz GDPNow), stopa
bezrobocia, wnioski o zasiłek, stopy procentowe (stopa Fed, rentowności 2 i 10 lat, krzywe),
put/call ratio (Cboe akcje, całkowity, SPX, z otwartych pozycji SPX), percentyl zmienności, premia
za ryzyko (VIX minus realna zmienność), RSI, VaR (z karty VaR), wstęgi Bollingera i ADX.

**Dodane w audycie, bo pomagają w ocenie** (i dlaczego): reguła Sahm (najprostszy alarm
recesji z rynku pracy), nowe etaty NFP, inflacja CPI i bazowa PCE (od nich zależy kierunek stóp),
CFNAI (zbiorczy indeks 85 danych o aktywności), struktura terminowa VIX/VIX3M (strach krótki
kontra dłuższy), spread kredytowy Baa i spread obligacji śmieciowych (rynek długu pierwszy
wyczuwa kłopoty firm), warunki finansowe NFCI, zmienność obligacji MOVE, szerokość rynku RSP/SPY,
apetyt na ryzyko XLY/XLP, akcje kontra obligacje SPY/IEF, średnie 50 i 200 sesji, MACD, spadek od
szczytu, ekspozycja gamma i skośność 25 delta z łańcucha SPX, SKEW, VVIX, VIX9D, dolar, ropa i
złoto, zmienność zrealizowana, ATR i zwrot z 3 miesięcy.

**Rozważone i odrzucone na tym etapie:** ISM PMI (od 2016 r. nie ma go w FRED, a wydawca nie
udostępnia danych za darmo; jego rolę pełni CFNAI), ankieta AAII i ekspozycja NAAIM (tygodniowe
ankiety bez stabilnego, darmowego API), gotowy indeks strachu i chciwości CNN (brak oficjalnego
API, więc zamiast niego własny indeks nastrojów z tych samych typów składników), odsetek spółek S&P
500 nad średnią 200 sesji (wymaga notowań 500 spółek; możliwe w przyszłości z danych karty ETF
sektorowe), rewizje prognoz zysków, kontrakty na stopę Fed (CME) i wskaźnik wyprzedzający
Conference Board (płatne źródła), wskaźnik CAPE (zmienia się zbyt wolno dla horyzontu 1–3 mies.).

**Lista ocenianych wskaźników** (punkty od -2 do +2, waga w grupie; pełny opis i reguła są w
rozwinięciu wiersza na karcie i w `DEFINICJE` w `stan_rynku.py`):

| Grupa | Wskaźnik | Źródło | Reguła oceny (skrót) | Waga |
|---|---|---|---|---|
| Makro | PKB USA (ostatni kwartał) | FRED A191RL1Q225SBEA | od 3%: +2 … poniżej 0: -2 | 1 |
| Makro | GDPNow (bieżący kwartał) | FRED GDPNOW | jak PKB | 1 |
| Makro | Stopa bezrobocia (zmiana r/r) | FRED UNRATE | poniżej -0,2 pkt: +1 … od +0,5: -2 | 1 |
| Makro | Reguła Sahm | FRED SAHMREALTIME | poniżej 0,2: +1 … od 0,5: -2 | 1,5 |
| Makro | Wnioski o zasiłek (r/r) | FRED IC4WSA | poniżej -5%: +1 … od +20%: -2 | 1 |
| Makro | Nowe etaty NFP (średnia 3 mies.) | FRED PAYEMS | od 150 tys.: +1 … poniżej 0: -2 | 1 |
| Makro | Inflacja CPI r/r | FRED CPIAUCSL | poniżej 2,5%: +1 … od 5%: -2 | 1 |
| Makro | Rentowność 10 lat | FRED DGS10 | 3 mies. od +0,75 pkt: -2; od +0,4 albo poziom od 4,75%: -1 | 1 |
| Makro | CFNAI (średnia 3 mies.) | FRED CFNAIMA3 | od +0,2: +1 … poniżej -0,7: -2 | 1 |
| Rynek | Put/call akcji (Cboe, 10 sesji) | Cboe, statystyki dzienne | percentyl z roku od 90: -1 | 1 |
| Rynek | Percentyl zmienności (VIX, 1 rok) | Cboe VIX | poniżej 25: +1 … od 90: -2 | 1 |
| Rynek | Premia za ryzyko (VIX minus realna zmienność) | Cboe VIX, Yahoo ^GSPC | poniżej -2 pkt: -2 … od 6: +1 | 1 |
| Rynek | Struktura terminowa VIX/VIX3M | Cboe, Yahoo | poniżej 0,88: +1 … od 1,05: -2 | 1,5 |
| Rynek | Spread kredytowy Baa | FRED BAA10Y | 3 mies. od +0,5 pkt: -2; od +0,25: -1; percentyl 5 lat poniżej 30: +1 | 1 |
| Rynek | Warunki finansowe NFCI | FRED NFCI | poniżej -0,35: +1 … od 0,5: -2 | 1 |
| Rynek | Zmienność obligacji MOVE | Yahoo ^MOVE | poniżej 80: +1 … od 150: -2 | 0,5 |
| Rynek | Szerokość rynku RSP/SPY (3 mies.) | Yahoo | od +2%: +1 … poniżej -6%: -2 | 0,5 |
| Rynek | Apetyt na ryzyko XLY/XLP (3 mies.) | Yahoo | od +3%: +1 … poniżej -8%: -2 | 1 |
| Rynek | Akcje kontra obligacje SPY minus IEF (20 sesji) | Yahoo | od +3 pkt: +1 … poniżej -6: -2 | 0,5 |
| Technika | Trend 200 sesji (położenie i nachylenie) | Yahoo ^GSPC | nad rosnącą: +2 … pod spadającą: -2 | 2 |
| Technika | Średnie 50 i 200 sesji | Yahoo ^GSPC | 50 nad 200: +1, pod: -1 | 1 |
| Technika | RSI 14 (Wilder) | Yahoo ^GSPC | od 70: -1; poniżej 30: +1 | 0,5 |
| Technika | Wstęgi Bollingera (%B) | Yahoo ^GSPC | powyżej 1: -1; poniżej 0: +1 | 0,5 |
| Technika | ADX 14 z kierunkiem DI | Yahoo ^GSPC | ADX od 25: +1 albo -1 według DI | 1 |
| Technika | MACD (12, 26, 9) | Yahoo ^GSPC | nad sygnałem i zerem: +1; pod oboma: -1 | 1 |
| Technika | Spadek od szczytu 52 tyg. | Yahoo ^GSPC | mniej niż 5%: +1 … od 20%: -2 | 1 |
| Technika | Przekroczenia VaR 99% (63 sesje) | karta VaR (SPY) | 2: -1; od 3: -2 | 1 |

**Wskaźniki informacyjne** (pokazane, ale poza sygnałem): stopa Fed i jej kierunek, inflacja
bazowa PCE, krzywe 10 lat minus 3 mies. i minus 2 lata, rentowność 2 lat, realna rentowność 10
lat, oczekiwania inflacyjne, wnioski kontynuowane, nastroje konsumentów, bilans Fed, put/call
całkowity, SPX i z otwartych pozycji SPX, ekspozycja gamma SPX, skośność 25 delta, spread HY,
SKEW, VVIX, VIX9D/VIX, dolar, ropa, złoto, VaR 1 sesji i próg VaR na 21 sesji (z karty VaR),
zmienność zrealizowana, ATR i zwrot z 3 miesięcy. Trzy z nich (stopa Fed, PCE, krzywa 10 lat
minus 3 mies.) były w pierwszej wersji oceniane; dlaczego już nie są, opisuje sekcja 6.

</details>

<details>
<summary>5. Jak powstaje sygnał i indeks nastrojów</summary>

1. Każdy oceniany wskaźnik dostaje punkty według swojej reguły, a punkty dzielimy przez
   maksimum tego wskaźnika, więc każdy daje od -1 do +1.
2. **Grupa** to średnia ważona dostępnych wskaźników razy 100 (liczona, gdy dostępna jest co
   najmniej połowa wagi grupy), czyli wynik od -100 do +100.
3. **Sygnał** to średnia grup z wagami: makro 30%, rynek 35%, technika 35% (makro zmienia się wolno
   i z opóźnieniem publikacji, więc waży mniej). Poziomy: od +40 silnie pozytywny, od +15
   pozytywny, powyżej -15 neutralny, powyżej -40 negatywny, niżej silnie negatywny.
4. **Historia bez zaglądania w przyszłość.** Dane makro wchodzą do historii dopiero po typowym
   opóźnieniu publikacji (np. bezrobocie 35 dni po miesiącu, PKB 120 dni po początku kwartału,
   wnioski o zasiłek 5 dni), żeby wykres nie korzystał z liczb, których danego dnia jeszcze nie
   znano. Korzysta jednak z danych po rewizjach, więc to przybliżenie.
5. **Indeks nastrojów (0–100)** to średnia z siedmiu składników, każdy jako percentyl z ostatnich 2
   lat (wysoko oznacza chciwość): kurs względem średniej 125 sesji, odległość od szczytu 52 tyg.,
   RSP względem SPY w miesiąc, put/call akcji z 5 sesji (odwrotnie), VIX względem średniej 50 sesji
   (odwrotnie), akcje kontra obligacje i obligacje śmieciowe kontra skarbowe z 20 sesji. Pasma:
   do 25 skrajny strach, do 45 strach, do 55 neutralnie, do 75 chciwość, wyżej skrajna chciwość.

</details>

<details>
<summary>6. Sprawdzenie na danych i kalibracja (co pokazała historia od 2000 r.)</summary>

Dla każdej sesji od grudnia 2000 r. policzyłem sygnał tymi samymi regułami co dziś i sprawdziłem,
co działo się z S&P 500 w kolejnych 63 sesjach (ok. 3 miesiące). Wyniki dla całej historii:

| Poziom sygnału | Sesji (udział) | Spadek o 10% i więcej w 3 mies. | Średni zwrot 1 mies. | Średni zwrot 3 mies. | Na plusie po 3 mies. | Średnie największe obsunięcie |
|---|---|---|---|---|---|---|
| Silnie pozytywny | 652 (10%) | 4,1% | +0,6% | +0,8% | 64% | -4,2% |
| Pozytywny | 3296 (51%) | 8,5% | +0,7% | +2,4% | 74% | -3,9% |
| Neutralny | 1150 (18%) | 19,1% | +1,3% | +3,9% | 76% | -4,8% |
| Negatywny | 896 (14%) | 35,5% | +0,3% | +0,7% | 52% | -8,5% |
| Silnie negatywny | 506 (8%) | 44,3% | +0,4% | +0,1% | 57% | -11,5% |
| Wszystkie sesje | 6500 | 16,5% | +0,7% | +2,1% | 69% | -5,3% |

**Jak czytać tabelę.** Wiersz „Negatywny” mówi: w historii było 896 sesji z takim sygnałem i po
35,5% z nich S&P 500 w ciągu 3 miesięcy choć raz zamknął się co najmniej 10% niżej niż w dniu
sygnału, czyli dwa razy częściej niż przeciętnie (16,5%). **Wniosek:** sygnał bardzo dobrze
porządkuje ryzyko (od 4% do 44% szans na duży spadek), ale nie przewiduje wysokości zwrotu:
średni zwrot po sesjach neutralnych był wyższy niż po silnie pozytywnych, bo najspokojniejsze okresy
(np. styczeń 2018 i przełom 2019 i 2020 r., oba z sygnałem silnie pozytywnym) kończyły się nagłym
powrotem zmienności, a po wyprzedażach rynek bywa tani. Dlatego karta mówi o „warunkach i ryzyku”, a nie o prognozie. To jak prognoza
pogody dla żeglarza: nie mówi, ile mil przepłyniesz, tylko jak często w taką pogodę zrywa się sztorm.

**Zależność nie jest stała w czasie.** Od października 2019 r. (pełne dane put/call) po 64 sesjach
silnie negatywnych (marzec–maj 2020, maj–czerwiec 2022 i kwiecień 2025) przychodziło szybkie
odbicie: średnio +13,6% w 3 miesiące. Z kolei sesje silnie pozytywne z grudnia 2019 i stycznia
2020 poprzedziły krach pandemiczny, więc w tym okresie po 22% sesji silnie pozytywnych przyszedł
spadek o 10% i więcej. Okresy nakładają się na siebie, więc niezależnych prób jest dużo mniej niż
sesji. Karta pokazuje trzy
okresy do wyboru (całość, od 2008, od 10.2019), żeby było to widać.

**Każdy wskaźnik osobno** (korelacja rang oceny z późniejszym obsunięciem: dodatnia znaczy, że
lepsza ocena poprzedzała mniejsze spadki; 0 to brak związku):

| Wskaźnik | Od | Korelacja z obsunięciem | Spadek o 10% przy najgorszej ocenie | przy najlepszej |
|---|---|---|---|---|
| PKB USA | 1999 | +0,12 | 32% (-2) | 11% (+2) |
| GDPNow | 2011 | +0,02 | 10% (-2) | 10% (+2) |
| Stopa bezrobocia | 2000 | +0,16 | 33% (-2) | 12% (+1) |
| Reguła Sahm | 1999 | +0,17 | 34% (-2) | 12% (+1) |
| Wnioski o zasiłek | 2000 | +0,08 | 34% (-2) | 13% (+1) |
| Nowe etaty NFP | 1999 | +0,16 | 34% (-2) | 10% (+1) |
| Inflacja CPI | 2000 | +0,19 | 33% (-2) | 13% (+1) |
| Rentowność 10 lat | 1999 | +0,15 | 14% (-2) | 15% (0) |
| CFNAI | 1999 | +0,12 | 48% (-2) | 6% (+1) |
| Put/call akcji | 2020 | +0,17 | 21% (-1) | 10% (0) |
| Percentyl zmienności | 1997 | +0,10 | 20% (-2) | 9% (+1) |
| Premia za ryzyko | 1996 | +0,01 | 32% (-2) | 15% (+1) |
| Struktura VIX/VIX3M | 2006 | +0,09 | 36% (-2) | 11% (+1) |
| Spread Baa | 2000 | +0,20 | 26% (-2) | 7% (+1) |
| NFCI | 1999 | +0,18 | 59% (-2) | 14% (+1) |
| MOVE | 2002 | +0,16 | 49% (-2) | 7% (+1) |
| Szerokość RSP/SPY | 2003 | +0,06 | 27% (-2) | 10% (+1) |
| Apetyt XLY/XLP | 1999 | +0,09 | 35% (-2) | 12% (+1) |
| Akcje kontra obligacje | 2002 | +0,06 | 28% (-2) | 11% (+1) |
| Trend 200 sesji | 1997 | +0,24 | 40% (-2) | 9% (+2) |
| Średnie 50 i 200 | 1997 | +0,19 | 34% (-1) | 10% (+1) |
| RSI | 1996 | -0,03 | 9% (-1) | 27% (+1) |
| Wstęgi Bollingera | 1996 | -0,01 | 8% (-1) | 22% (+1) |
| ADX | 1996 | +0,09 | 24% (-1) | 8% (+1) |
| MACD | 1996 | +0,09 | 26% (-1) | 11% (+1) |
| Spadek od szczytu | 1997 | +0,20 | 39% (-2) | 9% (+1) |
| Przekroczenia VaR | 2000 | +0,12 | 32% (-2) | 13% (0) |

**Jak czytać.** Wiersz „NFCI” mówi, że po sesjach z najgorszą oceną warunków finansowych (-2)
S&P 500 spadał o 10% w 3 miesiące w 59% przypadków, a po najlepszej (+1) w 14%. Najmocniej ryzyko
porządkują trend 200 sesji, spread Baa, spadek od szczytu, CPI i NFCI. RSI i wstęgi Bollingera w
klasycznym odczycie działają odwrotnie jako miara ryzyka (wyprzedanie zdarza się w bessie), choć po
wyprzedaniu średnie zwroty były wyższe; mają małą wagę 0,5 (decyzja 3 w sekcji 9).

**Zmiany po sprawdzeniu** (każda ma też uzasadnienie ekonomiczne, nie tylko statystyczne):

1. **Put/call akcji** w podręcznikowym odczycie (dużo putów to sygnał przekorny, czyli plus)
   w danych Cboe 2020–2026 działał odwrotnie: górny decyl roku poprzedzał najsłabsze wyniki i
   najgłębsze spadki na 10, 21 i 63 sesje (trwały popyt na zabezpieczenia towarzyszył bessie 2022).
   Teraz górny decyl daje -1, a beztroska nie dostaje punktów. Próba jest krótka (jedna bessa), więc
   to pierwsza kalibracja !!!_WERYFIKACJA_!!!.
2. **Krzywa 10 lat minus 3 mies.** w horyzoncie 3 miesięcy działała odwrotnie (przy odwróconej
   krzywej akcje zwykle rosły, np. 2006–2007, 2019, 2023–2024), bo to sygnał recesji z
   wyprzedzeniem 6–24 miesięcy. Teraz jest informacyjna.
3. **Inflacja bazowa PCE i kierunek stopy Fed** nie porządkowały ryzyka (obniżki stóp w kryzysach
   2008 i 2020 przychodziły razem ze spadkami), a inflację reprezentuje CPI, stopy rentowność 10 lat.
   Teraz są informacyjne.
4. **Wagi** RSI, wstęg Bollingera i szerokości rynku obniżone do 0,5.

</details>

<details>
<summary>7. Część 2, technicznie: pliki, dane, automatyzacja</summary>

- **Plik karty:** `docs/stan-rynku/stan_rynku.py` (wzorzec jednoplikowy, prefiks `st`). Magazyn
  funkcji: pobieranie (FRED API albo CSV, Yahoo przez Worker, Cboe), formatowanie po polsku,
  szeregi „punkt w czasie”, wskaźniki techniczne (Wilder RSI i ADX, Bollinger, MACD), analiza
  łańcucha SPX, definicje 54 wskaźników (`DEFINICJE`) i funkcje liczące (`licz_<id>`), sygnał,
  nastroje i skuteczność; oraz JS przeglądarki (`APP_JS_MAGAZYN`). Elementy: orkiestratory okien
  (`element_wskazniki`, `element_sygnal`, `element_ocena_sprawdz`, `element_historia`,
  `element_skutecznosc`, `element_zrodla`) z fragmentami `HTML_FRAGMENT_*` i `APP_JS_*`;
  `generuj()` składa `index.html` i `app.js`.
- **Polecenia:** `python docs/stan-rynku/stan_rynku.py` (strona), `… aktualizuj` (dane, ok. 25 s
  przy archiwum put/call na miejscu), `… sprawdz` (walidacja oceny Claude).
- **Dane:** `dane/stan.json` (ok. 300 KB: sygnał, nastroje, wskaźniki z historią 3 lat, historia
  sygnału dzienna z 3 lat i tygodniowa od 2000 r., skuteczność, źródła), `dane/cboe-putcall.json`
  (archiwum dziennych statystyk Cboe od 7.10.2019, dopisywane codziennie), `dane/opcje-spx.json`
  (dzienne odczyty z łańcucha SPX: gamma, skośność, put/call z otwartych pozycji, IV 30 i 90 dni;
  historia zbiera się do przyszłej kalibracji), `dane/ocena.json` (ocena dnia i archiwum 60 ocen).
- **Workflow:** `.github/workflows/stan-rynku-aktualizuj.yml`, dni robocze 22:40 UTC i na żądanie;
  instaluje tylko pandas, klucz FRED z sekretu `FRED_API_KEY` (bez niego pliki CSV), commit
  `github-actions[bot]`. Ok. 1–2 minuty na przebieg, czyli ok. 40 minut miesięcznie limitu Actions.
- **Worker:** nowa trasa `/cboe-statystyki?data=RRRR-MM-DD` (zapasowa, gdyby Cboe blokowało
  serwery GitHub Actions; parametr to tylko data, więc nie przepuszcza dowolnych adresów).
- **Rutyna Claude:** zaplanowane zadanie „Stan rynku: ocena dnia”, wtorek–sobota 5:50 czasu
  polskiego (po sesji w USA i po nocnych postach Social); instrukcja w
  `docs/stan-rynku/instrukcja-oceny.md` (wersja 1), zapis tylko `dane/ocena.json`.
- **Zmiany poza kartą:** `docs/VaR/VaR.py` (import `yfinance` w funkcji), rejestracja karty w
  `sidebar.js` (nowa ikona „barometr”), `projekty.js`, `oznaczenia.js` i `mapa_kodu.py`, style w
  bloku „Karta Stan rynku” na końcu `docs/style.css`.
- **Sprawdzone:** Chromium (Playwright), motyw Dzień i Noc, szerokość 1440 px i telefon 390 px,
  bez błędów w konsoli (poza oczekiwanym 404 przed pierwszą oceną); skrypt na Pythonie 3.13 i 3.11
  (jak w workflow), z kluczem FRED i bez niego, z identycznym wynikiem.

</details>

<details>
<summary>8. Dalsza część analizy (propozycje)</summary>

1. **Prawdopodobieństwo dużego spadku zamiast punktów.** Zamiast ręcznych progów można policzyć
   regresję logistyczną: jakie jest prawdopodobieństwo spadku o 10% w 3 miesiące przy dzisiejszych
   wartościach wskaźników, z kalibracją „krocząco do przodu” (model uczy się tylko na danych sprzed
   danego dnia). Dałoby to jedną liczbę w procentach, uczciwie sprawdzoną poza próbą.
   Rekomendacja: zrobić jako drugi etap, gdy karta pobędzie w użyciu kilka tygodni.
2. **Kalibracja wskaźników opcyjnych.** Gamma, skośność i put/call z otwartych pozycji SPX zbierają
   historię w `dane/opcje-spx.json`. Po około 6 miesiącach (ok. 125 sesji) można sprawdzić ich
   związek z późniejszymi spadkami i włączyć do sygnału.
3. **Szerokość rynku z prawdziwych danych.** Odsetek spółek S&P 500 nad średnią 200 sesji z
   notowań spółek (lista z karty ETF sektorowe) byłby lepszy niż proxy RSP/SPY.
4. **Ocena rutyny Claude.** Archiwum ocen pozwoli po kilku miesiącach sprawdzić, czy przesunięcia
   sygnału przez Claude (najwyżej o jeden poziom) poprawiały, czy psuły wynik liczbowy.
5. **Powiązanie z oceną ryzyka portfela.** Sygnał i nastroje mogą wejść do oceny decyzji o
   zabezpieczeniu portfela (np. ostrożniej przy sygnale negatywnym i ujemnej gammie).
6. **Put/call całej giełdy w karcie Social.** Dane z Cboe, uznawane wcześniej za niedostępne, są
   teraz w archiwum, więc kafelek „Put/call” w przeglądzie rynku Social może z nich korzystać.

</details>

<details>
<summary>9. Do decyzji użytkownika</summary>

1. **Klucz FRED.** Dodaj sekret repozytorium `FRED_API_KEY` (GitHub: Settings, Secrets and
   variables, Actions, New repository secret) z kluczem z opisu zadania. Karta działa i bez niego
   (pliki CSV FRED), ale API jest stabilniejsze. Klucz jest zapisany w `opis.md` tego zadania, a
   więc w historii gita: rekomendacja to wygenerować nowy klucz na stronie FRED, wpisać go do
   sekretu i usunąć stary z opisu zadania.
2. **Godzina rutyny.** Ocena dnia powstaje od wtorku do soboty o 5:50 czasu polskiego. Jeśli wolisz
   inną godzinę albo także poniedziałki (wtedy bez nowych danych), zmień to w zaplanowanych
   zadaniach.
3. **RSI i wstęgi Bollingera.** W historii ich klasyczny odczyt działał odwrotnie jako miara ryzyka
   (sekcja 6). Rekomendacja: przenieść je do informacyjnych; dziś są oceniane z wagą 0,5, bo
   były w poleceniu wprost.
4. **Progi i wagi** to pierwsza kalibracja na danych od 2000 r.; po kilku tygodniach warto sprawdzić,
   czy kolory nie zapalają się za często.
5. **Put/call w karcie Social** (sekcja 8, punkt 6): czy podpiąć tam dane Cboe.

</details>
