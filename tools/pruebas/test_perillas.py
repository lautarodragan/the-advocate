"""That the project file reader fails clearly instead of falling back to a
default: see `common/perillas.py`. On files built here, not on the game's."""

import pytest

from common import perillas


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nname = "juego"\n[maps]\nbelow = 3\n'
                    'debug = true\n')
    return str(ruta)


def test_lee_una_clave_anidada(archivo):
    assert perillas.valor("rom", "name", ruta=archivo) == "juego"
    assert perillas.valor("maps", "below", tipo=int, ruta=archivo) == 3


def test_una_clave_que_falta_dice_cual(archivo):
    with pytest.raises(perillas.FaltaUnaClave, match=r"missing key rom\.title"):
        perillas.valor("rom", "title", ruta=archivo)
    with pytest.raises(perillas.FaltaUnaClave, match=r"missing key audio$"):
        perillas.valor("audio", "se", ruta=archivo)


def test_un_tipo_equivocado_tambien_falla(archivo):
    with pytest.raises(perillas.FaltaUnaClave, match="must be int"):
        perillas.valor("rom", "name", tipo=int, ruta=archivo)
    # `True` is an `int` to Python, and a boolean setting placed where a
    # number goes is an error in the file.
    with pytest.raises(perillas.FaltaUnaClave, match="must be int"):
        perillas.valor("maps", "debug", tipo=int, ruta=archivo)
    assert perillas.valor("maps", "debug", tipo=bool, ruta=archivo) is True


def test_un_texto_que_va_a_la_rom_se_mide(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nfirma = "ABLS"\ncorta = "ABL"\nacento = "ÁBLS"\n')
    ruta = str(ruta)
    assert perillas.ascii("rom", "firma", largo=4, ruta=ruta) == "ABLS"
    with pytest.raises(perillas.FaltaUnaClave, match="have 4 characters"):
        perillas.ascii("rom", "corta", largo=4, ruta=ruta)
    with pytest.raises(perillas.FaltaUnaClave, match="ASCII"):
        perillas.ascii("rom", "acento", largo=4, ruta=ruta)
    with pytest.raises(perillas.FaltaUnaClave, match="1 to 2"):
        perillas.ascii("rom", "firma", hasta=2, ruta=ruta)


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
        "import render.render_map, render.chipset_del_fork\n"
        "from common import proyecto\n"
        "proyecto.directorio()\n")
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    entorno = dict(os.environ, PYTHONPATH=perillas.proyecto.herramientas())
    hecho = subprocess.run([sys.executable, "-c", codigo], cwd=vacio,
                           env=entorno, capture_output=True, text=True)
    assert hecho.returncode == 1, hecho.stderr[-2000:]
    assert hecho.stderr.startswith("found no rm2k-snes.toml in %s"
                                   % vacio), hecho.stderr[-2000:]
