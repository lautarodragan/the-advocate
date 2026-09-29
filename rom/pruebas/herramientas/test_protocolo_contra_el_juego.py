"""El bytecode de los eventos, contra lo que sólo tiene el juego: los
cartuchos armados y las páginas de los 328 mapas.

Lo que no necesita ni una cosa ni la otra —que los generados estén al día,
que las dos puntas digan los mismos números, los largos del layout— son
pruebas de las herramientas, y viven con ellas.
"""

import os

import pytest

from port import event_opcodes
from port import events
from rpgmaker import lcf
from rpgmaker.resources import GAME_DIR
from assembly import cartridges
import tanda


def declarados(modulo):
    return {n: v for n, v in vars(modulo).items()
            if n.startswith("OP_") and isinstance(v, int)}


def desde_la_rom(datos, direccion):
    """El byte de LoROM que cae en `direccion`, sea del banco que sea o de su
    espejo rápido (`$80xxxx`)."""
    return ((direccion >> 16) & 0x7F) * 0x8000 + (direccion & 0x7FFF)


@pytest.mark.parametrize("nombre", sorted(cartridges.CARTRIDGES))
def test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k(nombre):
    """El despacho de `correr_codigo` es `jmp (manejadores_de_opcode, x)`.

    Que cada `op_x` exista lo cobra el ensamblador: la tabla es una macro que
    los nombra. Esto mira la ROM armada: que la entrada k, leída como la lee
    el `jmp`, sea la dirección del manejador del opcode k, y que ése esté en
    el banco de `correr_codigo`, porque la entrada es de dieciséis bits y el
    `jmp` salta adentro del banco del programa. Un manejador que alguien
    mande a otro banco ensamblaría igual si el `.addr` lo trunca.
    """
    uno = tanda.cartucho(nombre)
    with open(uno.sfc, "rb") as archivo:
        datos = archivo.read()
    tabla = uno.simbolos["manejadores_de_opcode"]
    banco = uno.simbolos["correr_codigo"] >> 16
    codigos = {v: n for n, v in declarados(event_opcodes).items()}
    assert sorted(codigos) == list(range(len(codigos))), (
        "los números de events.toml tienen huecos: la tabla no puede ser")
    for k in sorted(codigos):
        manejador = codigos[k].lower()
        direccion = uno.simbolos[manejador]
        en = desde_la_rom(datos, tabla + 2 * k)
        entrada = datos[en] | datos[en + 1] << 8
        assert entrada == direccion & 0xFFFF, (
            "la entrada $%02X de la tabla apunta a $%04X y %s está en $%06X"
            % (k, entrada, manejador, direccion))
        assert direccion >> 16 == banco, (
            "%s está en el banco $%02X y correr_codigo en el $%02X: el `jmp` "
            "de la tabla no llega" % (manejador, direccion >> 16, banco))


# --- los largos, contra el juego -------------------------------------------
#
# Lo que hace falta probar no es "el teletransporte anda", que eso ya lo miran la
# tanda de pixeles y `test_puerta_misma`: es que **el emisor y el intérprete
# cuenten los mismos bytes**. Si no coinciden, el intérprete lee el bytecode
# corrido y eso no da ningún error: da una página que hace cualquier cosa. Por eso
# no se mira sólo el teletransporte sino **todos los opcodes de todas
# las páginas del juego**: recorre el bytecode con los largos de
# `OPCODE_SIZE` y exige caer justo en el final. Un opcode al que el emisor le
# ponga un byte de más o de menos se cae ahí, sea cual sea.


def paginas_del_juego():
    """Todas las páginas disparables de los 328 mapas, ya compiladas."""
    # **Todos** los índices que llena el conversor antes de compilar, y no sólo
    # el de variables: son globales de `events`, así que con uno solo las
    # páginas que compilan dependían de qué otra prueba había corrido antes en
    # el mismo proceso, y con xdist eso es el reparto.
    for indexar in (events.index_variables, events.index_animations,
                    events.index_common_events, events.index_battle_audio,
                    events.index_terms, events.index_actors,
                    events.index_skills):
        indexar(GAME_DIR)
    for nombre in sorted(os.listdir(GAME_DIR)):
        if not (nombre.startswith("Map") and nombre.endswith(".lmu")):
            continue
        game_map = lcf.Map(os.path.join(GAME_DIR, nombre))
        del_mapa = events.MapEvents(game_map)
        for ev in game_map.events:
            for numero, page in enumerate(ev.pages):
                if page.trigger not in events.TRIGGERS \
                        or not events.can_trigger(page):
                    continue
                codigo = events.compile_page(
                    page, lambda m: 0, events.Messages(),
                    del_mapa.for_event(ev.id), events.Songs(), events.Graphics(),
                    events.Pictures(GAME_DIR))
                if codigo:
                    yield nombre, ev.id, numero, codigo


@pytest.mark.skipif(not os.path.isdir(GAME_DIR),
                    reason="hace falta el juego original en GAME_DIR")
def test_los_largos_de_opcode_cuadran_en_todo_el_juego():
    cuantas = 0
    for nombre, evento, numero, codigo in paginas_del_juego():
        cuantas += 1
        i = 0
        while i < len(codigo):
            i += events.opcode_size(codigo, i)
        assert i == len(codigo), (
            "%s evento %d página %d: el recorrido por OPCODE_SIZE termina "
            "en %d y la página mide %d" % (nombre, evento, numero, i,
                                           len(codigo)))
    # Que no pase por vacío: si `paginas_del_juego` dejara de devolver nada,
    # este test sería verde sin haber mirado ni un byte.
    assert cuantas > 3000
