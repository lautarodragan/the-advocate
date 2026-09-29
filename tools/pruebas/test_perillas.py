"""Que el lector del archivo de proyecto falle claro en vez de caer en un
default: ver `comun/perillas.py`. Sobre archivos armados acá, no sobre el del
juego."""

import pytest

from comun import perillas


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
    with pytest.raises(perillas.FaltaUnaClave, match=r"falta la clave rom\.title"):
        perillas.valor("rom", "title", ruta=archivo)
    with pytest.raises(perillas.FaltaUnaClave, match=r"falta la clave audio$"):
        perillas.valor("audio", "se", ruta=archivo)


def test_un_tipo_equivocado_tambien_falla(archivo):
    with pytest.raises(perillas.FaltaUnaClave, match="tiene que ser int"):
        perillas.valor("rom", "name", tipo=int, ruta=archivo)
    # `True` es un `int` para Python, y una perilla booleana puesta donde va
    # un número es un error del archivo.
    with pytest.raises(perillas.FaltaUnaClave, match="tiene que ser int"):
        perillas.valor("maps", "debug", tipo=int, ruta=archivo)
    assert perillas.valor("maps", "debug", tipo=bool, ruta=archivo) is True


def test_un_texto_que_va_a_la_rom_se_mide(tmp_path):
    ruta = tmp_path / "rm2k-snes.toml"
    ruta.write_text('[rom]\nfirma = "ABLS"\ncorta = "ABL"\nacento = "ÁBLS"\n')
    ruta = str(ruta)
    assert perillas.ascii("rom", "firma", largo=4, ruta=ruta) == "ABLS"
    with pytest.raises(perillas.FaltaUnaClave, match="tener 4 caracteres"):
        perillas.ascii("rom", "corta", largo=4, ruta=ruta)
    with pytest.raises(perillas.FaltaUnaClave, match="ASCII"):
        perillas.ascii("rom", "acento", largo=4, ruta=ruta)
    with pytest.raises(perillas.FaltaUnaClave, match="de 1 a 2"):
        perillas.ascii("rom", "firma", hasta=2, ruta=ruta)


def test_las_herramientas_se_importan_sin_un_juego(tmp_path):
    """El conversor y lo que usa leen las perillas y las rutas del proyecto
    cuando las usan, no al importarse: si no, importar `port.snes_convert`
    —lo que hacen las pruebas de acá— pediría el archivo de proyecto de un
    juego. Se corre aparte, parado en un directorio vacío —donde buscar el
    archivo hacia arriba no encuentra ninguno—, porque en este proceso los
    módulos ya pueden estar importados. Y al final se pide el proyecto, para
    ver que de verdad no había uno que encontrar."""
    import os
    import subprocess
    import sys
    codigo = (
        "import port.snes_convert, port.eventos, port.escena, port.msu_datos\n"
        "import port.parches, audio.snes_music, audio.msu, rpgmaker.rm2k\n"
        "import render.render_map, render.chipset_del_fork\n"
        "from comun import proyecto\n"
        "proyecto.directorio()\n")
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    entorno = dict(os.environ, PYTHONPATH=perillas.proyecto.herramientas())
    hecho = subprocess.run([sys.executable, "-c", codigo], cwd=vacio,
                           env=entorno, capture_output=True, text=True)
    assert hecho.returncode == 1, hecho.stderr[-2000:]
    assert hecho.stderr.startswith("no encontré un rm2k-snes.toml en %s"
                                   % vacio), hecho.stderr[-2000:]
