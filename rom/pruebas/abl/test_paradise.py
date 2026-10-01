"""El camino a Paradise recién llegado: Mountain Path (105), la amnistía
(106), el túnel (107) y Distant Paradise (108).

El 106, el 107 y el 108 arrancan con una escena al llegar —la amnistía,
Isabella, el camino al Consejo—, así que se llega con la escena ya vista: el
switch que la apaga prendido (331, 332 y 333). El 105 se camina tal cual.
Las escenas las juega `test_recorrido_paradise_golden.py`. Ver
`workflow/tasks/*/mundo-7-camino-a-paradise.md`.

Se llega a donde deja el juego: al 105 desde el túnel del mundo (66 ev18), al
106 desde el 105, al 107 desde el 106 y al 108 desde el final del túnel.

Y el 108 es el mapa que entra porque sus quietos **se turnan las ranuras de
VRAM**: los que ninguna cámara muestra juntos comparten una, y la ROM sube la
pose del que entra en pantalla. Eso lo cobra `test_los_quietos_del_108_se_turnan`,
caminando por el pueblo lleno. Ver
`workflow/tasks/*/el-108-con-poses-compartidas.md`.
"""

import pytest

from consola import SEGUIR, en_la_rom
from tanda import golden, partida

TALAN = 14
LLEGAR_TICKS = 40

LLEGADAS = (
    ("paradise-105-llegada", 105, (68, 19), ()),
    ("paradise-106-llegada", 106, (10, 13), (331,)),
    ("paradise-107-llegada", 107, (1, 8), (332,)),
    ("paradise-108-llegada", 108, (19, 19), (333,)),
)


@pytest.mark.parametrize("nombre,mapa,celda,vistas", LLEGADAS,
                         ids=[n for n, _m, _c, _v in LLEGADAS])
def test_recien_llegado(nombre, mapa, celda, vistas):
    p = partida("en-5", switches=vistas)
    p.poner_grupo(TALAN)
    p.ir_al_mapa(mapa, *celda)
    p.correr(LLEGAR_TICKS)
    assert p.mapa() == mapa and p.heroe() == celda, (
        "pedí el %d en %s y la partida está en el %d, en %s"
        % (mapa, celda, p.mapa(), p.heroe()))
    assert not p.corriendo_una_pagina(), (
        "a los %d ticks de llegar al %d sigue corriendo una página"
        % (LLEGAR_TICKS, mapa))
    golden(nombre, p.imagen())
    malas, _ = p.celdas_mal_dibujadas()
    assert not malas, "%d celdas mal dibujadas en el %d: %s" % (
        len(malas), mapa, malas[:12])


DISTANT_PARADISE = 108
# El pueblo lleno: con estos switches están los de la segunda tanda de
# vecinos —los eventos 65 a 85, menos los de 81—, que es la que más quietos
# pone a la vez. Ninguno arranca una página al llegar.
EL_PUEBLO_LLENO = (333, 396, 386, 388)
# Por el camino de tierra que baja desde la plaza: arriba, 76 y 79 en
# pantalla; abajo del todo, 75 —que se turna la ranura con 79— y 67; y de
# vuelta arriba. Cada paso, `(golden, hacia dónde, ticks, celda a la que
# llega)`.
LA_CAMINATA = (
    ("paradise-108-turnos-arriba", None, 0, (20, 19)),
    ("paradise-108-turnos-al-medio", "down", 100, (20, 32)),
    ("paradise-108-turnos-abajo", "down", 100, (20, 45)),
    ("paradise-108-turnos-de-vuelta", "up", 200, (20, 20)),
)


def _palabra_de_la_rom(rom, direccion):
    k = en_la_rom(direccion)
    return rom[k] | (rom[k + 1] << 8)


def turnos_en_pantalla(p):
    """Los quietos del mapa que se turnan una ranura y están en pantalla:
    `(evento, ranura, pose, bien)`, con `bien` diciendo si la ranura tiene
    en la VRAM los bytes de su pose en el cartucho.

    "En pantalla" es lo que `build_oam` no descarta —la caja de 32x32 del
    objeto toca la pantalla— y la tabla es la del cartucho, `share_maps` y
    `share_data`, leída como la lee `share_want`. El que mira al héroe está
    en la ranura del giro y no se cuenta.
    """
    s = p.simbolos
    ram = p.consola.ram
    with open(p.sfc, "rb") as archivo:
        rom = archivo.read()
    mapa = p.palabra("map_current")
    registro = _palabra_de_la_rom(rom, s["share_maps"] + 2 * mapa)
    assert registro, "el mapa %d no se turna ninguna ranura" % p.mapa()
    datos = s["share_data"] + registro
    eventos = s["share_data"] + _palabra_de_la_rom(rom, datos)
    poses = s["share_data"] + _palabra_de_la_rom(rom, datos + 2)
    sprites = _palabra_de_la_rom(
        rom, s["map_table"] + mapa * s["MAP_STRIDE"] + s["M_VRAM_SPRITE"])
    puntero = ram(s["poses_ptr"], 3)
    tabla = puntero[0] | (puntero[1] << 8) | (puntero[2] << 16)
    girando = ram(s["TURN_EV"] & 0x1FFFF, 1)[0]
    pantalla_x, camara_y = p.palabra("screen_x"), p.palabra("camera_y")
    filas = ram(s["npc_buf"], p.palabra("npc_total"))
    vistos = []
    for i in range(0, len(filas), s["NPC_STRIDE"]):
        fila = filas[i:i + s["NPC_STRIDE"]]
        evento = fila[8]
        x = (fila[0] | (fila[1] << 8)) - pantalla_x - s["SPRITE_OFF_X"]
        y = (fila[2] | (fila[3] << 8)) - camara_y - s["SPRITE_OFF_Y"]
        x, y = (x + 0x8000) % 0x10000 - 0x8000, (y + 0x8000) % 0x10000 - 0x8000
        if not fila[14] or evento == girando:
            continue
        if not (-32 <= x < 256 and -32 <= y < 224):
            continue
        k = en_la_rom(eventos + 2 * evento)
        ranura, pose = rom[k], rom[k + 1]
        if ranura == 0xFF:
            continue
        donde = sprites + _palabra_de_la_rom(rom, datos + 5 + 2 * ranura)
        k = en_la_rom(tabla + _palabra_de_la_rom(rom, poses + 2 * pose))
        origen = rom[k] | (rom[k + 1] << 8) | (rom[k + 2] << 16)
        esperada = rom[en_la_rom(origen):en_la_rom(origen) + 512]
        # Las cuatro filas del bloque de 4x4, a 256 palabras una de otra.
        subida = b"".join(
            bytes(b for w in p.consola.vram(donde + 256 * r, 64)
                  for b in (w & 0xFF, w >> 8))
            for r in range(4))
        vistos.append((evento, ranura, pose, subida == esperada))
    return vistos


def _sin_errores(p, donde):
    vistos = turnos_en_pantalla(p)
    malos = [v[:3] for v in vistos if not v[3]]
    assert not malos, (
        "%s: estos quietos se ven con la ranura de otro, (evento, ranura, "
        "pose): %s" % (donde, malos))
    return vistos


def test_los_quietos_del_108_se_turnan():
    """Caminando por el pueblo lleno, cada quieto que se turna una ranura
    se ve con la suya: la de la VRAM es la de su pose en el cartucho, en
    cada parada. Y de verdad se turnan: alguna ranura mostró dos poses
    distintas en el camino. Con golden en cada parada, la de arriba antes y
    después de que los de abajo entren en pantalla."""
    p = partida("en-5", switches=EL_PUEBLO_LLENO)
    p.poner_grupo(TALAN)
    p.ir_al_mapa(DISTANT_PARADISE, 20, 19)
    p.correr(LLEGAR_TICKS)
    poses_por_ranura = {}
    for nombre, hacia, ticks, celda in LA_CAMINATA:
        if hacia is not None:
            p.sostener(ticks, hacia)
            p.soltar()
            p.correr(10)
        assert p.mapa() == DISTANT_PARADISE and p.heroe() == celda, (
            "%s: la partida está en el %d, en %s, y tenía que llegar a %s"
            % (nombre, p.mapa(), p.heroe(), celda))
        for _evento, ranura, pose, _bien in _sin_errores(p, nombre):
            poses_por_ranura.setdefault(ranura, set()).add(pose)
        golden(nombre, p.imagen())
    turnadas = {r: v for r, v in poses_por_ranura.items() if len(v) > 1}
    assert turnadas, (
        "nadie se turnó una ranura en toda la caminata: la prueba no mira lo "
        "que dice. Ranuras y poses vistas: %s" % poses_por_ranura)


def test_el_108_se_turna_al_saltar_dentro_del_mapa_y_al_cargar():
    """Los dos caminos que no son caminar: un `Teleport` al mismo mapa
    —`FADE_SAME`, que no recarga el banco y salta la cámara de una— y cargar
    una partida guardada ahí, que sube el banco del cartucho y no sabe qué
    tiene cada ranura. En los dos, el primer cuadro ya tiene que estar bien:
    lo arma `build_oam_settled` con la pantalla apagada."""
    p = partida("en-5", switches=EL_PUEBLO_LLENO)
    p.poner_grupo(TALAN)
    p.ir_al_mapa(DISTANT_PARADISE, 20, 19)
    p.correr(LLEGAR_TICKS)
    _sin_errores(p, "al llegar")
    s = p.simbolos
    for nombre, valor in (("entry_x", 20), ("entry_y", 45)):
        p.consola.write_ram(s[nombre], [valor, 0])
    p.consola.write_ram(s["fade_kind"], [s["FADE_SAME"]])
    p.consola.write_ram(s["fade"], [1])
    p.consola.write_ram(s["fade_base"], [p.palabra("ticks") & 0xFF])
    p.correr(90)
    assert p.mapa() == DISTANT_PARADISE and p.heroe() == (20, 45), p.heroe()
    abajo = _sin_errores(p, "después del salto")
    assert abajo, "después del salto no hay ningún quieto que se turne en pantalla"
    p.guardar_por_el_menu(ranura=1)
    p.reiniciar(SEGUIR, ranura=1)
    p.correr(LLEGAR_TICKS)
    assert p.mapa() == DISTANT_PARADISE and p.heroe() == (20, 45), (
        "la partida cargó en el %d, en %s" % (p.mapa(), p.heroe()))
    assert sorted(_sin_errores(p, "después de cargar")) == sorted(abajo)
