"""Regeneracja kart: generatory dają dokładnie te pliki, które są zatwierdzone w web/.

`index.html` i `app.js` kart nie są edytowane ręcznie: powstają z jednego pliku .py na kartę (stałe HTML_FRAGMENT_*
i APP_JS_*). Test uruchamia wszystkie generatory na kopii repozytorium i porównuje wynik z zatwierdzonym `web/`.
Zielony wynik oznacza, że nikt nie poprawił wygenerowanego pliku ręcznie i nie zapomniał go odświeżyć po zmianie
generatora. To też siatka bezpieczeństwa przy przenoszeniu plików: kopia dokumentów zgodna z oryginałem."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

GENERATORY = ["biblioteka/biblioteka.py", "pozycja/pozycja.py", "stan_rynku/stan_rynku.py", "var/var.py"]   # karty w wersji poglądowej (te same, co w Makefile)
POMIJANE = shutil.ignore_patterns("node_modules", "__pycache__")


@pytest.fixture(scope="module")
def kopia(tmp_path_factory, korzen):
    """Kopia tylko tego, co czytają generatory: kod, strona i wpisy biblioteki."""
    cel = tmp_path_factory.mktemp("repo")
    shutil.copytree(korzen / "src", cel / "src", ignore=POMIJANE)
    shutil.copytree(korzen / "web", cel / "web")
    shutil.copytree(korzen / "docs" / "biblioteka", cel / "docs" / "biblioteka")
    return cel


def _uruchom(kopia: Path, skrypt: str, *argumenty: str) -> None:
    wynik = subprocess.run([sys.executable, "-I", str(kopia / "src" / skrypt), *argumenty], cwd=kopia, capture_output=True, text=True, timeout=180)
    assert wynik.returncode == 0, f"{skrypt} {' '.join(argumenty)} zakończył się błędem:\n{wynik.stderr[-1500:]}"


def _roznice(a: Path, b: Path) -> list[str]:
    zle = []
    for plik in sorted(a.rglob("*")):
        if not plik.is_file():
            continue
        wzgledna = plik.relative_to(a)
        if not (b / wzgledna).is_file():
            zle.append(f"brak po regeneracji: {wzgledna}")
        elif plik.read_bytes() != (b / wzgledna).read_bytes():
            zle.append(f"inna treść: {wzgledna}")
    return zle


def test_generatory_odtwarzaja_zatwierdzona_strone(kopia, korzen):
    for generator in GENERATORY:
        _uruchom(kopia, generator, "generuj")
    assert _roznice(korzen / "web", kopia / "web") == [], "wygenerowane pliki różnią się od zatwierdzonych: uruchom `make build` i zacommituj wynik"


def test_mapa_kodu_jest_aktualna(kopia, korzen):
    """Mapa „numerek bloku -> kod” (zakładka Kod w dymku) musi odpowiadać aktualnym plikom (poza datą wygenerowania)."""
    _uruchom(kopia, "narzedzia/mapa_kodu.py")
    zatwierdzona = json.loads((korzen / "web/shared/mapa-kodu.json").read_text(encoding="utf-8"))
    odtworzona = json.loads((kopia / "web/shared/mapa-kodu.json").read_text(encoding="utf-8"))
    zatwierdzona.pop("wygenerowano", None)
    odtworzona.pop("wygenerowano", None)
    assert zatwierdzona == odtworzona, "mapa kodu jest nieaktualna: uruchom `make build`"
