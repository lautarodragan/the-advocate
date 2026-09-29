"""El efecto de sonido adentro de una ruta forzada: la orden 35.

En RM2k suena cuando la ruta llega a ese paso (`Game_Character::
UpdateMoveRoute`, `play_sound_effect`), sin costar un cuadro: la orden que
sigue corre en el mismo. Hasta el 2026-09-27 el conversor lo tiraba. Ahora va
con el índice del efecto detrás —el mismo de `OP_SOUND`— y la ROM lo toca con
`sound_play`, sobre el héroe (`sonido_heroe`) y sobre un evento
(`sonido_ev`): son dos caminos y cada uno tiene su caso.

Los casos son del mapa 10 con `Close1`, que ya está en su paquete de audio
por las páginas del mapa: así el caso no le agrega un efecto al paquete ni le
mueve el reparto de la música a nadie.

* `sonido-en-ruta`: el héroe, dos pasos a la derecha, el efecto y otro paso.
* `sonido-en-ruta-evento`: el evento 14, una espera y el efecto.
* `sonido-en-ruta-salto`: el héroe salta en el lugar con el efecto adentro
  del salto, y da un paso. Ahí RM2k no lo toca —`BeginMoveRouteJump` sólo
  suma los pasos hasta el `end_jump`— y el conversor lo tira.

Lo que se mira es el estado de las dos voces de efectos en la RAM lejana
(`SE_FRAMES` y `SE_NEW`, ver runtime/efectos_de_sonido.s): un efecto
arranca cuando los cuadros que le quedan a una voz suben.
"""

import json
import os

from consola import en_la_rom, en_la_wram

EFECTO = ("Close1", 100, 100, 50)


def fila(una, sonido=EFECTO):
    """La fila de `sonido_tabla` del efecto: la muestra, la altura, el volumen
    de cada lado y los cuadros que dura. El índice sale de `efectos.json`, que
    el conversor escribe al lado del cartucho en el orden de `Songs.sounds`."""
    with open(os.path.join(os.path.dirname(una.sfc), "efectos.json")) as a:
        sonidos = [tuple(s) for s in json.load(a)["sonidos"]]
    k = sonidos.index(sonido)
    with open(una.sfc, "rb") as a:
        rom = a.read()
    base = en_la_rom(una.simbolos["sonido_tabla"]) + 7 * k
    return rom[base:base + 7]


def _voces(una):
    """(cuadros que le quedan, muestra) de cada una de las dos voces."""
    voces = []
    for cuadros, nuevo in (("SE_FRAMES", "SE_NEW"),
                           ("SE2_FRAMES", "SE2_NEW")):
        c = una.consola.ram(en_la_wram(una.simbolos[cuadros]), 2)
        n = una.consola.ram(en_la_wram(una.simbolos[nuevo]), 1)
        voces.append((c[0] | (c[1] << 8), n[0]))
    return voces


def arranques(una, ticks, mirar=None):
    """[(tick, muestra, cuadros, lo que devuelva `mirar`)] por cada efecto que
    arranca en los próximos `ticks`."""
    salida = []
    antes = _voces(una)
    for tick in range(ticks):
        una.correr(1)
        ahora = _voces(una)
        for (c0, _m0), (c1, m1) in zip(antes, ahora):
            if c1 > c0:
                salida.append((tick, m1, c1, mirar(una) if mirar else None))
        antes = ahora
    return salida


def test_sobre_el_heroe_suena_en_su_paso(partida):
    """Suena una vez, con la muestra de `Close1` y entero, en el tick en que
    el héroe termina el segundo paso y arranca el tercero: la celda ya es la
    de destino del tercero, porque el paso la cambia al empezar."""
    una = partida(caso="sonido-en-ruta")
    x0 = una.palabra("tile_x")
    esperada = fila(una)
    vistos = arranques(una, 120, mirar=lambda p: p.palabra("tile_x") - x0)
    assert len(vistos) == 1, (
        "la ruta pide un efecto y sonaron %d: %s" % (len(vistos), vistos))
    _tick, muestra, cuadros, celdas = vistos[0]
    assert muestra == esperada[0], (
        "sonó la muestra %d y la de Close1 es %d" % (muestra, esperada[0]))
    dura = esperada[5] | (esperada[6] << 8)
    assert dura - 2 <= cuadros <= dura, (
        "Close1 dura %d cuadros y arrancó con %d" % (dura, cuadros))
    assert celdas == 3, (
        "el efecto va después del segundo paso y antes del tercero, así que "
        "suena con el tercero arrancando: el héroe iba %d celdas" % celdas)
    assert una.palabra("tile_x") == x0 + 3, "la ruta no terminó sus pasos"


def test_sobre_un_evento_suena(partida):
    """Suena una vez, con la muestra de `Close1`: es `sonido_ev`, el camino
    de los eventos, que lee el operando del bytecode con la ranura en X."""
    una = partida(caso="sonido-en-ruta-evento")
    esperada = fila(una)
    vistos = arranques(una, 120)
    assert [m for _t, m, _c, _ in vistos] == [esperada[0]], (
        "la ruta del evento pide Close1 (muestra %d) y arrancaron %s"
        % (esperada[0], vistos))


def test_adentro_de_un_salto_no_suena(partida):
    """Adentro de un salto no suena, y la ruta sigue: después del salto en el
    lugar da su paso a la derecha."""
    una = partida(caso="sonido-en-ruta-salto")
    x0 = una.palabra("tile_x")
    vistos = arranques(una, 120)
    assert vistos == [], (
        "el efecto va adentro del salto y RM2k no lo toca, y sonaron %s"
        % (vistos,))
    assert una.palabra("tile_x") == x0 + 1, (
        "después del salto la ruta da un paso: el héroe está en %d y salió "
        "de %d" % (una.palabra("tile_x"), x0))
