"""Con un líder sin gráfico, las paletas de sprite son las del cartucho.

`DummyHero`, el actor 10, no tiene un pixel opaco: el juego lo pone de líder
en las cinemáticas donde Talan es un evento más —la escena del barril del mapa
14, la guarida de Boss Wick después de los vidcasts—. Su entrada en la tabla
de actores lleva quince colores en cero, porque no hay nada que colorear, y
la ROM **los subía igual** a la paleta de sprite que dice su entrada, la 0:
todo lo que se dibujara con ella quedaba negro. Era Talan, en las dos
escenas, porque su `Future1:0` es el primer gráfico que reparte el conversor.
Lo vio taro jugando en la SNES el 2026-09-27; cambiar de mapa lo arreglaba
porque en los dos casos el mapa siguiente se carga con Talan de líder.

Se mira contra `cgram_sombra`, que es lo que `subir_tinte` copia a la CGRAM en
el vblank, y con el tinte neutro que pone `ir_al_mapa`: así lo que tiene que
haber es, color por color, el bloque de sprites que el conversor dejó en el
cartucho para ese mapa.
"""

import pytest

from consola import EMPEZAR, en_la_rom, en_la_wram
from ensamblado import cartuchos

DUMMY_HERO = 10
TALAN = 14
EL_MAPA_14 = 14
LA_GUARIDA_DE_WICK = 40
PRIMER_COLOR_DE_SPRITE = 128
COLORES_POR_PALETA = 16


def _cartucho(p):
    with open(p.sfc, "rb") as f:
        return f.read()


def _registro(p, rom, map_id):
    s = p.simbolos
    return en_la_rom(s["mapa_tabla"]) + p.mapas.index(map_id) * s["MAPA_STRIDE"]


def _palabra(rom, k):
    return rom[k] | rom[k + 1] << 8


def _sprites_del_cartucho(p):
    """Los colores de sprite del mapa cargado, como los dejó el conversor."""
    s, rom = p.simbolos, _cartucho(p)
    base = _registro(p, rom, p.mapa())
    k = base + s["M_PTR_SPRITE_CGRAM"]
    puntero = _palabra(rom, k) | rom[k + 2] << 16
    cuantos = _palabra(rom, base + s["M_SPRITE_CGRAM"])
    desde = en_la_rom(puntero)
    return [rom[desde + 2 * i] | rom[desde + 2 * i + 1] << 8
            for i in range(cuantos)]


def _sprites_en_la_sombra(p, cuantos):
    b = p.consola.ram(en_la_wram(p.simbolos["cgram_sombra"])
                      + 2 * PRIMER_COLOR_DE_SPRITE, 2 * cuantos)
    return [b[2 * i] | b[2 * i + 1] << 8 for i in range(cuantos)]


def _cargar(p, map_id, x, y):
    """Pide el mapa y corre hasta el primer cuadro con la carga terminada.

    Se mira ahí y no después porque el fundido congela el juego: hasta que
    termina no corre ninguna página, y las automáticas de varios mapas cambian
    el grupo —el 14 pone a Talan— o tiñen la pantalla —el 4, el 42, el 54—
    apenas arrancan. Es lo mismo que hace `test_carga_descomprimida.py`."""
    p.ir_al_mapa(map_id, x, y, cuadros=0)
    for _ in range(400):
        p.consola.run(1)
        if not p.byte("fundido_que"):
            assert p.mapa() == map_id, (
                "pedí el mapa %d y la ROM cargó el %d" % (map_id, p.mapa()))
            return
    raise AssertionError("el mapa %d no terminó de cargar" % map_id)


def _paletas_distintas(p):
    esperado = _sprites_del_cartucho(p)
    visto = _sprites_en_la_sombra(p, len(esperado))
    return sorted({i // COLORES_POR_PALETA for i in range(len(esperado))
                   if visto[i] != esperado[i]})


# Todos los del juego y no sólo los dos de taro: el color lo pisaba la carga
# del mapa, así que cualquiera al que se llegue con DummyHero liderando tenía
# la paleta 0 en negro, y cuáles son depende de por dónde se juegue. Los de la
# escena, primero, para que el rojo diga de entrada dónde lo vio taro.
MAPAS = [EL_MAPA_14, LA_GUARIDA_DE_WICK] + [
    m for m in cartuchos.MAPAS_DEL_JUEGO
    if m not in (EL_MAPA_14, LA_GUARIDA_DE_WICK)]


@pytest.mark.parametrize("map_id", MAPAS)
def test_el_lider_sin_grafico_no_pisa_ninguna_paleta(partida, map_id):
    """El mapa cargado con `DummyHero` de líder: las ocho paletas de sprite
    tienen que salir tal cual del cartucho. Antes la 0 quedaba en negro."""
    p = partida(titulo=EMPEZAR)
    rom = _cartucho(p)
    base = _registro(p, rom, map_id)
    x = _palabra(rom, base + p.simbolos["M_HERO_START_X"]) // 16
    y = _palabra(rom, base + p.simbolos["M_HERO_START_Y"]) // 16
    p.poner_grupo(DUMMY_HERO)
    _cargar(p, map_id, x, y)
    assert p.byte("grupo") == DUMMY_HERO
    distintas = _paletas_distintas(p)
    assert not distintas, (
        "con DummyHero de líder en el mapa %d, las paletas de sprite %s no son "
        "las del cartucho: la ROM les subió los quince colores en cero de un "
        "actor sin gráfico" % (map_id, distintas))


def test_con_talan_de_lider_su_ranura_lleva_sus_colores(partida):
    """La otra mitad, para que la de arriba no pase por no subir nunca nada:
    con un líder que sí tiene gráfico, sus quince colores van a su ranura."""
    p = partida(titulo=EMPEZAR)
    p.poner_grupo(TALAN)
    _cargar(p, EL_MAPA_14, 1, 1)
    assert p.byte("grupo") == TALAN
    fila = p.byte("hero_pal") // 2
    desde = en_la_wram(p.simbolos["hero_cgram"])
    puntero = p.consola.ram(desde, 3)
    colores = en_la_rom(puntero[0] | puntero[1] << 8 | puntero[2] << 16)
    rom = _cartucho(p)
    esperado = [rom[colores + 2 * i] | rom[colores + 2 * i + 1] << 8
                for i in range(COLORES_POR_PALETA - 1)]
    visto = _sprites_en_la_sombra(p, PRIMER_COLOR_DE_SPRITE)[
        fila * COLORES_POR_PALETA + 1:(fila + 1) * COLORES_POR_PALETA]
    assert any(esperado), "Talan tiene colores: la tabla de actores los trae"
    assert visto == esperado, (
        "Talan lidera y su ranura, la %d, no tiene sus colores" % fila)
