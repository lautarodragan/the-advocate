"""El destino de un teletransporte entra en dos bytes, y los largos cuadran.

`OP_TELEPORT` guardaba el índice del mapa destino en **un byte**, así que el
formato no podía nombrar más de 256 mapas y el juego tiene 328. Hoy no molesta
—la demo más grande lleva 29— pero era un techo escrito en el bytecode, y esto
lo saca.

Lo que hace falta probar no es "el teletransporte anda", que eso ya lo miran la
tanda de pixeles y `test_puerta_misma`: es que **el emisor y el intérprete
cuenten los mismos bytes**. Si no coinciden, el intérprete lee el bytecode
corrido y eso no da ningún error: da una página que hace cualquier cosa. Por eso
el segundo test no mira sólo el teletransporte sino **todos los opcodes de todas
las páginas del juego**: recorre el bytecode con los largos de
`LARGO_DE_OPCODE` y exige caer justo en el final. Un opcode al que el emisor le
ponga un byte de más o de menos se cae ahí, sea cual sea.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))

import eventos                                               # noqa: E402
import lcf                                                   # noqa: E402
from render_map import GAME_DIR                              # noqa: E402

# Un índice que **no entra en un byte**, que es de lo que se trata. El juego
# tiene 328 mapas: el 300 es uno de los que el formato viejo no podía nombrar.
LEJOS = 300


def compilar_un_teleport(destino):
    cmd = lcf.EventCommand(eventos.TELEPORT, 0, "", [7, 12, 34])
    return eventos._compilar(cmd, lambda m: destino)


def test_el_destino_viaja_en_dos_bytes():
    codigo = compilar_un_teleport(LEJOS)
    assert len(codigo) == eventos.LARGO_DE_OPCODE[eventos.OP_TELEPORT]
    estado = eventos.Estado()
    eventos.ejecutar(codigo + bytes([eventos.OP_FIN]), estado)
    # El mapa, y de paso la celda, que es lo que se correría si el largo
    # estuviera mal.
    assert estado.salto == (LEJOS, 12, 34)


def test_un_destino_que_no_entra_en_un_byte_no_se_trunca():
    """El caso que el formato viejo no podía: 300 & 0xFF es 44."""
    assert compilar_un_teleport(LEJOS) != compilar_un_teleport(LEJOS & 0xFF)


def paginas_del_juego():
    """Todas las páginas disparables de los 328 mapas, ya compiladas."""
    eventos.indexar_variables(GAME_DIR)
    for nombre in sorted(os.listdir(GAME_DIR)):
        if not (nombre.startswith("Map") and nombre.endswith(".lmu")):
            continue
        game_map = lcf.Map(os.path.join(GAME_DIR, nombre))
        del_mapa = eventos.Eventos(game_map)
        for ev in game_map.events:
            for numero, page in enumerate(ev.pages):
                if page.trigger not in eventos.TRIGGERS \
                        or not eventos.puede_dispararse(page):
                    continue
                codigo = eventos.compilar_pagina(
                    page, lambda m: 0, eventos.Mensajes(),
                    del_mapa.para(ev.id), eventos.Temas(), eventos.Graficos(),
                    eventos.Imagenes(GAME_DIR))
                if codigo:
                    yield nombre, ev.id, numero, codigo


@pytest.mark.skipif(not os.path.isdir(GAME_DIR),
                    reason="hace falta el juego original en GAME_DIR")
def test_ningun_opcode_comparte_numero_con_otro():
    """Dos `OP_*` con el mismo valor son dos programas distintos.

    No es una precaución abstracta: el 2026-09-13 tres ramas de sub-agente
    eligieron el siguiente número libre a la vez, sin verse, y salieron dos
    colisiones —`OP_PARAR_RUTAS` con `OP_ACTOR_GRAF` en $23, `OP_SI_ACTOR` con
    `OP_TECLA` en $24—. Git las mergeó **sin un solo conflicto**, porque cada
    una está en su línea, y lo que se rompía era el recorrido del bytecode: el
    intérprete leía un opcode de tres bytes creyendo que medía siete.

    Lo cazó `test_los_largos_de_opcode_cuadran_en_todo_el_juego`, pero de
    rebote y sólo porque alguna página del juego usaba los dos. Esto lo dice
    directamente y sin depender de que el juego los ejercite.
    """
    numeros = {}
    for nombre, valor in sorted(vars(eventos).items()):
        if not nombre.startswith("OP_") or not isinstance(valor, int):
            continue
        assert valor not in numeros, (
            "%s y %s son los dos $%02X: el bytecode no se puede recorrer"
            % (numeros[valor], nombre, valor))
        numeros[valor] = nombre
    assert len(numeros) > 30, "no se miró ni un opcode"


def test_los_largos_de_opcode_cuadran_en_todo_el_juego():
    cuantas = 0
    for nombre, evento, numero, codigo in paginas_del_juego():
        cuantas += 1
        i = 0
        while i < len(codigo):
            i += eventos.largo_de_opcode(codigo, i)
        assert i == len(codigo), (
            "%s evento %d página %d: el recorrido por LARGO_DE_OPCODE termina "
            "en %d y la página mide %d" % (nombre, evento, numero, i,
                                           len(codigo)))
    # Que no pase por vacío: si `paginas_del_juego` dejara de devolver nada,
    # este test sería verde sin haber mirado ni un byte.
    assert cuantas > 3000
