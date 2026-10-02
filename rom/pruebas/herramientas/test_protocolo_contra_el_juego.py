"""El bytecode de los eventos, contra lo que sólo tiene el juego: los
cartuchos armados y las páginas de los 328 mapas; y el módulo de Python con
el que las pruebas leen el bytecode, que es de ellas.

Lo que no necesita ni una cosa ni la otra —que los generados de las
herramientas estén al día, que las dos puntas digan los mismos números, los
largos del layout— son pruebas de las herramientas, y viven con ellas.
"""

import os
import subprocess

import pytest

import event_opcodes
import conversor
import events
import lcf
import rm2k
from resources import GAME_DIR
import cartuchos
import datos
import tanda


def declarados(modulo):
    return {n: v for n, v in vars(modulo).items()
            if n.startswith("OP_") and isinstance(v, int)}


def test_el_modulo_de_los_opcodes_esta_al_dia():
    """`arnes/event_opcodes.py` sale de la declaración de las herramientas,
    `snes/protocol/events.toml`, con `protocol`; está commiteado, como los
    demás generados, y esto es lo que lo cuida. Se regenera con

        protocol <la declaración, snes/protocol/events.toml> --python arnes/event_opcodes.py

    Hasta el 2026-10-02 lo generaba la receta `protocol` de las
    herramientas, cuando lo leía el conversor; desde que el conversor es de
    Rust lo leen sólo estas pruebas."""
    declaracion = os.path.join(os.path.dirname(cartuchos.runtime()), "snes",
                               "protocol", "events.toml")
    hecho = subprocess.run(
        ["protocol", declaracion, "--check", "--python", event_opcodes.__file__],
        capture_output=True, text=True)
    assert hecho.returncode == 0, (
        "arnes/event_opcodes.py no es lo que da la declaración:\n%s%s"
        % (hecho.stdout, hecho.stderr))


def desde_la_rom(datos, direccion):
    """Dónde cae `direccion` en el archivo, sea del banco que sea o de su
    espejo rápido (`$80xxxx`): el código va en los dos —ver `en_la_rom` en
    `arnes/consola.py`—, y esto es sólo para código."""
    return ((direccion >> 16) & 0x7F) << 16 | 0x400000 | (direccion & 0xFFFF)


@pytest.mark.parametrize("nombre", sorted(cartuchos.nombres()))
def test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k(nombre):
    """El despacho de `run_code` es `jmp (opcode_handlers, x)`.

    Que cada `op_x` exista lo cobra el ensamblador: la tabla es una macro que
    los nombra. Esto mira la ROM armada: que la entrada k, leída como la lee
    el `jmp`, sea la dirección del manejador del opcode k, y que ése esté en
    el banco de `run_code`, porque la entrada es de dieciséis bits y el
    `jmp` salta adentro del banco del programa. Un manejador que alguien
    mande a otro banco ensamblaría igual si el `.addr` lo trunca.
    """
    uno = tanda.cartucho(nombre)
    with open(uno.sfc, "rb") as archivo:
        datos = archivo.read()
    tabla = uno.simbolos["opcode_handlers"]
    banco = uno.simbolos["run_code"] >> 16
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
            "%s está en el banco $%02X y run_code en el $%02X: el `jmp` "
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
    """Todas las páginas disparables de los 328 mapas, ya compiladas: cada
    una sola, en un cartucho con todos. Es la primera llamada del compilador
    —ver `conversor.escaneo`—, que arma los índices del juego entero antes de
    compilar la primera."""
    todo = datos.todo_el_juego()
    for entrada in todo["maps"]:
        mapa = entrada["id"]
        game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % mapa))
        compiladas = conversor.paginas_compiladas(todo, mapa)
        for e, ev in enumerate(game_map.events):
            for numero, page in enumerate(ev.pages):
                # Las que la ROM sabe disparar: las cuatro, y la de tocar
                # sólo en otra capa que la del héroe.
                if page.trigger not in events.TRIGGERS or (
                        page.trigger == events.TRIGGER_TOUCH_HERO
                        and page.layer == rm2k.LAYER_SAME):
                    continue
                codigo = compiladas.get((e, numero))
                if codigo:
                    yield "Map%04d" % mapa, ev.id, numero, codigo


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
