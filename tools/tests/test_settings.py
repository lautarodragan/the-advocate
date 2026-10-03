"""That the project file reader fails clearly instead of falling back to a
default: see `common/settings.py`. On files built here, not on the game's."""

import pytest

from common import settings


@pytest.fixture
def project_file(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nname = "juego"\n[maps]\nbelow = 3\n'
                    'debug = true\n')
    return str(ruta)


def test_reads_a_nested_key(project_file):
    assert settings.value("rom", "name", path=project_file) == "juego"
    assert settings.value("maps", "below", kind=int, path=project_file) == 3


def test_a_missing_key_says_which(project_file):
    with pytest.raises(settings.MissingKey, match=r"missing key rom\.title"):
        settings.value("rom", "title", path=project_file)
    with pytest.raises(settings.MissingKey, match=r"missing key audio$"):
        settings.value("audio", "se", path=project_file)


def test_a_wrong_type_fails_too(project_file):
    with pytest.raises(settings.MissingKey, match="must be int"):
        settings.value("rom", "name", kind=int, path=project_file)
    # `True` is an `int` to Python, and a boolean setting placed where a
    # number goes is an error in the file.
    with pytest.raises(settings.MissingKey, match="must be int"):
        settings.value("maps", "debug", kind=int, path=project_file)
    assert settings.value("maps", "debug", kind=bool,
                          path=project_file) is True


def test_a_text_that_goes_to_the_rom_is_measured(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nfirma = "GAME"\ncorta = "GAM"\nacento = "GÁME"\n')
    ruta = str(ruta)
    assert settings.ascii("rom", "firma", length=4, path=ruta) == "GAME"
    with pytest.raises(settings.MissingKey, match="have 4 characters"):
        settings.ascii("rom", "corta", length=4, path=ruta)
    with pytest.raises(settings.MissingKey, match="ASCII"):
        settings.ascii("rom", "acento", length=4, path=ruta)
    with pytest.raises(settings.MissingKey, match="1 to 2"):
        settings.ascii("rom", "firma", max_length=2, path=ruta)


def test_the_tools_import_without_a_game(tmp_path):
    """The tools' Python reads the settings and the project paths when it
    uses them, not at import: otherwise importing it —which is what a game's
    tests do— would require a game's project file.
    It runs separately, standing in an empty directory —where searching
    upwards for the file finds none—, because in this process the modules may
    already be imported. And at the end the project is requested, to see that
    there really was none to find."""
    import os
    import subprocess
    import sys
    codigo = (
        "import common.settings, common.environment\n"
        "import emulator.retro\n"
        "from common import project\n"
        "project.directory()\n")
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    entorno = dict(os.environ, PYTHONPATH=settings.project.tools())
    hecho = subprocess.run([sys.executable, "-c", codigo], cwd=vacio,
                           env=entorno, capture_output=True, text=True)
    assert hecho.returncode == 1, hecho.stderr[-2000:]
    assert hecho.stderr.startswith("found no rm2k-snes.toml in %s"
                                   % vacio), hecho.stderr[-2000:]
