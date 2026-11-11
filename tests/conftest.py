"""Wspólna konfiguracja testów.

Skrypty z `src/` są plikami uruchamianymi wprost (`python src/<karta>/<karta>.py`), a nie pakietem,
więc katalogi z kodem trafiają do `sys.path` i testy importują je po nazwie pliku
(`import stan_rynku`, `import social`). Importy nie wykonują żadnych zapytań do sieci.
"""

import sys
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]

for katalog in sorted((KORZEN / "src").iterdir()):
    if katalog.is_dir() and not katalog.name.startswith("__"):
        sys.path.insert(0, str(katalog))


@pytest.fixture(scope="session")
def korzen() -> Path:
    """Korzeń repozytorium."""
    return KORZEN
