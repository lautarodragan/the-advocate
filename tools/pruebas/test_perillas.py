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
