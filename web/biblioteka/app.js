"use strict";

// PLIK GENEROWANY przez src/biblioteka/biblioteka.py — nie edytuj ręcznie.

// Filtr bibliotek: ukrywa wpisy, w których nie ma wpisanej frazy (nazwa,
// język, kategoria, opis, status); sekcje bez żadnego widocznego wpisu też znikają.
function bibZastosujFiltr() {
  const fraza = document.getElementById("bib-filtr").value.trim().toLowerCase();
  let widoczne = 0;
  document.querySelectorAll(".bib-wpis").forEach((wpis) => {
    const pasuje = !fraza || wpis.dataset.szukaj.includes(fraza);
    wpis.hidden = !pasuje;
    if (pasuje) widoczne++;
  });
  document.querySelectorAll(".bib-sekcja").forEach((sekcja) => {
    sekcja.hidden = !sekcja.querySelector(".bib-wpis:not([hidden])");
  });
  const licznik = document.getElementById("bib-licznik");
  licznik.textContent = fraza ? "Znaleziono: " + widoczne : "";
}
document.getElementById("bib-filtr").addEventListener("input", bibZastosujFiltr);
