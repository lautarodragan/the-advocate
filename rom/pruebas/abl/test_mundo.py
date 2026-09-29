"""El mundo, el mapa 66: el que estrena el quinto reparto de VRAM
(`LAYOUT_VENTANA_FONDO_TECHO`, 544 tiles de fondo) y el único de `release`
con el fondo en dos flujos de LZ2 —527 tiles de 8bpp son más que el buffer de
carga: ver `lz2_fondo` en runtime/descomprimir.s—.

Se llega como llega el juego, a la celda del `Teleport [66, 71, 29]` de la
despedida del 64, pero con `ir_al_mapa`: la despedida la juega
`test_recorrido_carrera_golden.py`, que sigue hasta Sorbe y el fin de la demo.

**La pelea sale sin fondo**, y es deuda declarada, no un error de esta prueba:
el cartucho lleva tres fondos de batalla y el mundo usa otros cinco terrenos.
Ver `workflow/tasks/*/mundo-1-el-66-entra.md`.
"""

from consola import en_la_wram
from tanda import golden, partida

EL_MUNDO = 66
LA_LLEGADA = (71, 29)
TALAN = 14
# Kersh gana solo contra lo que sale en la llegada; Talan, con lo que tiene al
# empezar la partida, pierde.
KERSH = 11
# Lo que corre la automática del evento 1 al llegar —la ruta del héroe y dos
# switches—, con margen.
LLEGAR_TICKS = 30


def llegar(*grupo):
    p = partida("en-5")
    p.poner_grupo(*grupo)
    p.ir_al_mapa(EL_MUNDO, *LA_LLEGADA)
    p.correr(LLEGAR_TICKS)
    assert p.mapa() == EL_MUNDO and p.heroe() == LA_LLEGADA, (
        "pedí el 66 en %s y la partida está en el %d, en %s"
        % (LA_LLEGADA, p.mapa(), p.heroe()))
    assert not p.corriendo_una_pagina(), (
        "a los %d ticks de llegar sigue corriendo una página" % LLEGAR_TICKS)
    return p


def test_el_mundo_recien_llegado():
    """`mundo-66-llegada`: Talan en el 66, y la ventana entera bien armada."""
    p = llegar(TALAN)
    golden("mundo-66-llegada", p.imagen())
    malas, _ = p.celdas_mal_dibujadas()
    assert not malas, "%d celdas mal dibujadas en el 66: %s" % (
        len(malas), malas[:12])


def test_una_pelea_en_el_mundo_vuelve_al_mapa_bien_dibujado():
    """`mundo-66-despues-de-pelear`: un encuentro pedido con `ENC_PIDE`, que
    Kersh gana a fuerza de A, y la vuelta al mapa.

    Es el camino de `volver_de_batalla`: la escena de la pelea pisa el banco de
    tiles de BG1 y la mitad alta del $7F, y `load_map` vuelve a subir el fondo
    —de a dos flujos— y `lz2_grilla` la grilla."""
    p = llegar(KERSH)
    s = p.simbolos
    p.consola.write_ram(en_la_wram(s["ENC_PIDE"]), [1])
    abierta = False
    # En cuadros de hardware: la pelea no cuenta ticks. A cada nueve cuadros,
    # que es lo que pasa los mensajes y elige atacar.
    for cuadros in range(1, 4000):
        p.consola.hold(*(("a",) if cuadros % 9 < 2 else ()))
        p.consola.run(1)
        if p.byte("menu_abierto"):
            abierta = True
        elif abierta:
            break
    else:
        raise AssertionError("la pelea no terminó en %d cuadros" % cuadros)
    p.consola.hold()
    assert abierta, "el encuentro pedido no abrió ninguna pelea"
    p.correr(LLEGAR_TICKS)
    assert p.mapa() == EL_MUNDO and p.heroe() == LA_LLEGADA, (
        "la pelea no volvió al 66 en %s: la partida está en el %d, en %s"
        % (LA_LLEGADA, p.mapa(), p.heroe()))
    golden("mundo-66-despues-de-pelear", p.imagen())
    malas, _ = p.celdas_mal_dibujadas()
    assert not malas, "%d celdas mal dibujadas después de pelear: %s" % (
        len(malas), malas[:12])
