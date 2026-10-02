"""El bytecode de los eventos, contra lo que sólo tiene el juego: los
cartuchos armados y las páginas de los 328 mapas.

Lo que no necesita ni una cosa ni la otra —que los generados de las
herramientas estén al día, que las dos puntas digan los mismos números, los
largos del layout— son pruebas de las herramientas, y viven con ellas.

**Ninguna sabe los números del bytecode.** Hasta el 2026-10-02 las pruebas
tenían su módulo de Python con los opcodes, generado de la declaración; se
fue cuando la última que lo leía dejó de hacerlo, para que el bytecode sea
del motor y no de las pruebas del juego. Lo que una prueba necesita del
bytecode se lo pregunta a la ROM armada —sus símbolos— o es una prueba del
compilador, en Rust.
"""

import os

import pytest

import conversor
import events
import lcf
import rm2k
from resources import GAME_DIR
import cartuchos
import datos
import tanda


def desde_la_rom(datos, direccion):
    """Dónde cae `direccion` en el archivo, sea del banco que sea o de su
    espejo rápido (`$80xxxx`): el código va en los dos —ver `en_la_rom` en
    `arnes/consola.py`—, y esto es sólo para código."""
    return ((direccion >> 16) & 0x7F) << 16 | 0x400000 | (direccion & 0xFFFF)


def de_eventos(simbolos):
    """{número: manejador} de los opcodes de eventos, leídos de los símbolos
    del cartucho: el `.inc` de la declaración define cada número con el
    nombre del opcode, y su manejador es un `.proc` con el mismo nombre en
    minúsculas. Los del stream de música caen en el mismo espacio de
    símbolos pero no tienen manejador, así que no entran."""
    tabla = simbolos.tabla
    return {int(v): n.lower() for n, v in tabla.items()
            if n.isupper() and n.lower() in tabla
            and n.lower().startswith("op_")}


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
    codigos = de_eventos(uno.simbolos)
    assert codigos, (
        "los símbolos del cartucho no traen ningún opcode con manejador: la "
        "prueba ya no mira lo que dice")
    assert sorted(codigos) == list(range(len(codigos))), (
        "los números del bytecode de eventos tienen huecos: la tabla no puede ser")
    for k in sorted(codigos):
        manejador = codigos[k]
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
# las páginas del juego**.
#
# Desde el 2026-10-02 el recorrido lo hace el compilador, sobre cada página
# que emite —`whole_instructions`, en `compile.rs` de `rm2k-snes-events`—, y
# una que no cae justo en su final para la conversión. Hasta ese día lo
# hacía esta prueba, en Python, con los largos del módulo generado. Lo que
# queda acá es que el juego entero pase por ahí.


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
def test_todas_las_paginas_del_juego_pasan_por_el_recorrido():
    cuantas = sum(1 for _ in paginas_del_juego())
    # Que no pase por vacío: si `paginas_del_juego` dejara de devolver nada,
    # este test sería verde sin que el compilador hubiera recorrido nada.
    assert cuantas > 3000
