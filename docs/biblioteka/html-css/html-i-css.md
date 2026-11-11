# HTML i CSS: bez bibliotek
Język: HTML i CSS
Kategoria: Interfejs strony
Status: w użyciu (czysty HTML/CSS, bez frameworka)
Pakiet: brak
Strona: https://developer.mozilla.org/pl/docs/Web/CSS
Gdzie w projekcie: web/style.css, web/*/index.html
W requirements.txt: nie dotyczy

Dla HTML i CSS odpowiednikiem „bibliotek" są frameworki wyglądu, takie jak Bootstrap czy Tailwind CSS, które dają gotowe klasy do przycisków, siatek i kolorów.
Ten projekt świadomie z nich nie korzysta: cały wygląd siedzi w jednym pliku `web/style.css`, a kolory pochodzą ze zmiennych (`--tlo`, `--akcent` itd.) zdefiniowanych osobno dla motywu Dzień i Noc.
Dzięki temu strona jest lekka, nie zależy od zewnętrznego serwera, a zmiana palety to edycja kilkunastu linii w jednym miejscu.
Gdybyśmy kiedyś zdecydowali się na framework, ten plik jest właściwym miejscem na dopisanie go i uzasadnienie wyboru.
