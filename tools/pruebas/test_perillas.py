"""That the project file reader fails clearly instead of falling back to a
default: see `common/settings.py`. On files built here, not on the game's."""

import pytest

from common import settings


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nname = "juego"\n[maps]\nbelow = 3\n'
                    'debug = true\n')
    return str(ruta)


def test_lee_una_clave_anidada(archivo):
    assert settings.value("rom", "name", path=archivo) == "juego"
    assert settings.value("maps", "below", kind=int, path=archivo) == 3


def test_una_clave_que_falta_dice_cual(archivo):
    with pytest.raises(settings.MissingKey, match=r"missing key rom\.title"):
        settings.value("rom", "title", path=archivo)
    with pytest.raises(settings.MissingKey, match=r"missing key audio$"):
        settings.value("audio", "se", path=archivo)


def test_un_tipo_equivocado_tambien_falla(archivo):
    with pytest.raises(settings.MissingKey, match="must be int"):
        settings.value("rom", "name", kind=int, path=archivo)
    # `True` is an `int` to Python, and a boolean setting placed where a
    # number goes is an error in the file.
    with pytest.raises(settings.MissingKey, match="must be int"):
        settings.value("maps", "debug", kind=int, path=archivo)
    assert settings.value("maps", "debug", kind=bool, path=archivo) is True


def test_un_texto_que_va_a_la_rom_se_mide(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nfirma = "ABLS"\ncorta = "ABL"\nacento = "ÁBLS"\n')
    ruta = str(ruta)
    assert settings.ascii("rom", "firma", length=4, path=ruta) == "ABLS"
    with pytest.raises(settings.MissingKey, match="have 4 characters"):
        settings.ascii("rom", "corta", length=4, path=ruta)
    with pytest.raises(settings.MissingKey, match="ASCII"):
        settings.ascii("rom", "acento", length=4, path=ruta)
    with pytest.raises(settings.MissingKey, match="1 to 2"):
        settings.ascii("rom", "firma", max_length=2, path=ruta)


def test_las_herramientas_se_importan_sin_un_juego(tmp_path):
    """The converter and what it uses read the settings and the project paths
    when they use them, not at import: otherwise importing `port.snes_convert`
    —which is what the tests here do— would require a game's project file.
    It runs separately, standing in an empty directory —where searching
    upwards for the file finds none—, because in this process the modules may
    already be imported. And at the end the project is requested, to see that
    there really was none to find."""
    import os
    import subprocess
    import sys
    codigo = (
        "import port.snes_convert, port.eventos, port.escena, port.msu_datos\n"
        "import port.parches, audio.snes_music, audio.msu, rpgmaker.rm2k\n"
        "import render.render_map, render.chipset_recipe\n"
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
