"""Los cuadros de texto rearmados para el ancho de la SNES, sobre los de
`data/`: que todos entren sin perder palabras, y que el conversor le dé al
compilador los rearmados.

No corre ninguna ROM. Lo que la función hace con cuadros armados a mano son
pruebas de las herramientas, y viven con ellas.
"""

import glob
import json
import os
import re

from common import project                               # noqa: E402
import conversor  # noqa: E402
import events  # noqa: E402
import screen_stage  # noqa: E402

# La cola de escapes de un cuadro —`\|` y `\^` al final del último
# renglón—, que no ocupa columnas: ver `escape_tail` en `rm2k-snes-text`.
COLA = re.compile(r"(\\[|^] *)+$")


def _sin_cola(cuadro):
    return cuadro[:-1] + [COLA.sub("", cuadro[-1])] if cuadro else cuadro


def _palabras(cuadros, con_hablante):
    desde = 1 if con_hablante else 0
    return " ".join(" ".join(c[desde:]) for c in cuadros).split()


def _ventana():
    """Las columnas y los renglones de la ventana para la que el conversor
    rearma las cajas."""
    ventana = conversor.cajas()["window"]
    return ventana["columns"], ventana["lines"]


def _cuadros_del_juego(patron="Map*.json"):
    rutas = sorted(glob.glob(os.path.join(project.data(), "maps", patron)))
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as handle:
            datos = json.load(handle)
        for evento in datos["events"]:
            for pagina in evento["pages"]:
                comandos = pagina["event_commands"]
                i = 0
                while i < len(comandos):
                    j = i + 1
                    if comandos[i]["code"] == events.SHOW_MESSAGE:
                        while (j < len(comandos) and comandos[j]["code"]
                               == events.SHOW_MESSAGE_2):
                            j += 1
                        yield [c["string"] for c in comandos[i:j]]
                    i = j


def test_todo_el_juego_entra_sin_perder_palabras():
    """Sobre todos los cuadros de `data/`: lo que sale entra, tiene las mismas
    palabras en el mismo orden, y rearmarlo otra vez no lo cambia."""
    vistos = 0
    columnas, renglones = _ventana()
    cuadros = list(_cuadros_del_juego())
    rearmados = screen_stage.refit(cuadros, columnas, renglones)
    salidas = []
    for cuadro, rearmado in zip(cuadros, rearmados):
        salida = rearmado["to"]
        if salida == [cuadro]:
            continue
        vistos += 1
        hablante = rearmado["speaker"]
        sin_cola = [_sin_cola(c) for c in salida]
        original = _sin_cola(cuadro)
        assert _palabras(sin_cola, hablante) == _palabras([original], hablante)
        for c in sin_cola:
            assert len(c) <= renglones, c
            assert all(len(t) <= columnas for t in c), c
        salidas.extend(salida)
    assert vistos, "ningún cuadro se rearmó: la prueba no está mirando nada"
    # Y rearmar lo que salió no lo cambia.
    for c, otra_vez in zip(salidas,
                           screen_stage.refit(salidas, columnas, renglones)):
        assert otra_vez["to"] == [c], c


def test_el_conversor_le_da_al_compilador_las_cajas_rearmadas():
    """El reajuste es un paso del pipeline: el conversor le pasa al
    compilador cada caja que no entra con las que van en su lugar, y el
    compilador las compila así. Sin esto la función podría estar perfecta y
    no correr nunca, que es el camino que ninguna prueba ejecuta.

    Se mira sobre el mapa 2: cada caja suya con un renglón más largo que la
    ventana tiene que estar en la tabla que el conversor entrega, y lo que
    va en su lugar, entrar."""
    columnas, renglones = _ventana()
    tabla = {tuple(caja["from"]): caja["to"]
             for caja in conversor.cajas()["boxes"]}
    largas = [c for c in _cuadros_del_juego("Map0002.json")
              if any(len(t) > columnas for t in _sin_cola(c))]
    assert largas, "el mapa 2 no tiene cajas largas: la prueba no mira nada"
    for caja in largas:
        assert tuple(caja) in tabla, caja
        for nueva in tabla[tuple(caja)]:
            assert len(nueva) <= renglones, nueva
            assert all(len(t) <= columnas for t in _sin_cola(nueva)), nueva
