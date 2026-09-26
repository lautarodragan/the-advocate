"""Lo que queda en la VRAM y en la WRAM después de cargar cada mapa es, byte
por byte, lo que el conversor dice que tiene que haber.

Desde el 2026-09-26 los tiles del mapa, de los sprites, de la capa de encima y
de la animación del ChipSet viajan en el cartucho comprimidos en LZ2, y la ROM
los descomprime al cargar el mapa —ver `lz2_descomprimir` en
rom/src/descomprimir.s—. La propiedad que hace verificable ese cambio es que
**lo que llega a la VRAM no cambió**, y eso es lo que se mira acá, en todos los
mapas de `release`: contra `crudos/`, que el conversor deja al lado del
cartucho sin comprimir —ver `escribir_crudos`— y no contra nada que salga de la
ROM.

Se mira justo después de la carga, en el primer cuadro en que `fundido_que`
volvió a cero: el fundido congela el juego, así que hasta que termine nadie
pisa lo que se subió. Dos cosas sí cambian y se miran por su lado: la corrida
animada del ChipSet, que `anim_cargar` pisa con el dibujo que le toca al reloj
—tiene que ser **uno** de los dibujos del bloque—, y la pose del héroe, que
`place_hero` puede cambiar ya en ese cuadro si no mira hacia abajo.

Corre también en bsnes, que enciende con la WRAM llena de basura: un
descompresor que leyera algo sin inicializar daría otra cosa ahí. Ese core no
expone la VRAM por libretro, así que ahí se mira lo que quedó en la WRAM.
"""

import os

import pytest

from consola import en_la_rom, en_la_wram
from ensamblado import cartuchos
from tanda import partida

BSNES = "/usr/lib/libretro/bsnes_libretro.so"
BYTES_POR_TILE_8BPP = 64
BYTES_POR_TILE_4BPP = 32


def _crudo(p, indice, clase):
    with open(os.path.join(os.path.dirname(p.sfc), "crudos",
                           "%d.%s.bin" % (indice, clase)), "rb") as f:
        return f.read()


class Registro:
    """El registro de un mapa en `mapa_tabla`, leído del cartucho."""

    def __init__(self, p, rom, indice):
        self.s = p.simbolos
        self.base = (en_la_rom(self.s["mapa_tabla"])
                     + indice * self.s["MAPA_STRIDE"])
        self.rom = rom

    def palabra(self, campo):
        k = self.base + self.s[campo]
        return self.rom[k] | (self.rom[k + 1] << 8)

    def byte(self, campo):
        return self.rom[self.base + self.s[campo]]


def _corridas_animadas(p, rom, indice):
    """[(palabra de VRAM, bytes por dibujo, desplazamiento del dibujo 0)] de
    las familias que animan en este mapa, leídas de `anim_tabla`."""
    s = p.simbolos
    corridas = []
    for familia in range(s["ANIM_FAMILIAS"]):
        k = (en_la_rom(s["anim_tabla"]) + indice * s["ANIM_STRIDE"]
             + familia * s["ANIM_FAM_STRIDE"])
        vram, cero, largo = (rom[k] | rom[k + 1] << 8, rom[k + 2] | rom[k + 3] << 8,
                             rom[k + 4] | rom[k + 5] << 8)
        if rom[k + 6]:
            corridas.append((vram, largo, cero))
    return corridas


def _vram(p, palabra, largo):
    return b"".join(w.to_bytes(2, "little")
                    for w in p.consola.vram(palabra, largo // 2))


def _cargar(p, map_id):
    """Pide el mapa con el fundido de una puerta y corre hasta el cuadro en
    que la carga terminó. Devuelve cuántos cuadros de hardware duró la vuelta
    del lazo que cargó, que es lo que la carga le cuesta a la pantalla."""
    indice = p.mapas.index(map_id)
    registro = Registro(p, p.rom, indice)
    x = registro.palabra("M_HERO_START_X") // 16
    y = registro.palabra("M_HERO_START_Y") // 16
    p.ir_al_mapa(map_id, x, y, cuadros=0)
    antes = p.palabra("vueltas")
    for cuadros in range(1, 400):
        p.consola.correr(1)
        if not p.byte("fundido_que"):
            assert p.mapa() == map_id, (
                "pedí el mapa %d y la ROM cargó el %d" % (map_id, p.mapa()))
            return cuadros - (p.palabra("vueltas") - antes) + 1
    raise AssertionError("el mapa %d no terminó de cargar en 400 cuadros" % map_id)


def _distintos(visto, esperado, paso):
    """Los números de los tiles —de `paso` bytes— que no coinciden."""
    if len(visto) != len(esperado):
        return ["largo %d contra %d" % (len(visto), len(esperado))]
    return [t for t in range(len(esperado) // paso)
            if visto[t * paso:(t + 1) * paso] != esperado[t * paso:(t + 1) * paso]]


def _mirar_la_vram(p, indice):
    """Lo que no coincide en la VRAM del mapa `indice` recién cargado."""
    s, rom = p.simbolos, p.rom
    registro = Registro(p, rom, indice)
    mal = []

    # Los tiles del fondo, menos las corridas animadas, que se miran aparte.
    base = registro.palabra("M_VRAM_TILES")
    crudo = _crudo(p, indice, "map_tiles")
    assert len(crudo) == registro.palabra("M_MAP_TILES") * BYTES_POR_TILE_8BPP
    visto = bytearray(_vram(p, base, len(crudo)))
    esperado = bytearray(crudo)
    anim = _crudo(p, indice, "anim_tiles")
    corridas = _corridas_animadas(p, rom, indice)
    for k, (vram, largo, cero) in enumerate(corridas):
        desde = (vram - base) * 2
        # Sus dibujos van seguidos desde el 0 hasta donde empieza la familia
        # que sigue: ver `anim_bytes` en snes_convert.py.
        hasta = corridas[k + 1][2] if k + 1 < len(corridas) else len(anim)
        dibujos = [anim[d:d + largo] for d in range(cero, hasta, largo)]
        puesto = bytes(visto[desde:desde + largo])
        if puesto not in dibujos:
            mal.append("la corrida animada de $%04X no es ninguno de sus %d "
                       "dibujos" % (vram, len(dibujos)))
        visto[desde:desde + largo] = bytes(largo)
        esperado[desde:desde + largo] = bytes(largo)
    t = _distintos(bytes(visto), bytes(esperado), BYTES_POR_TILE_8BPP)
    if t:
        mal.append("tiles del fondo distintos: %s" % t[:12])

    # La capa de encima: su base es el nibble alto de BG12NBA.
    crudo = _crudo(p, indice, "above_tiles")
    assert len(crudo) == registro.palabra("M_ABOVE_TILES") * BYTES_POR_TILE_4BPP
    base = (registro.byte("M_BG12NBA_VALUE") & 0xF0) << 8
    t = _distintos(_vram(p, base, len(crudo)), crudo, BYTES_POR_TILE_4BPP)
    if t:
        mal.append("tiles de la capa de encima distintos: %s" % t[:12])

    # Los sprites, menos la pose del héroe: el bloque 0, las cuatro filas de
    # cuatro tiles de 32x32 que en la grilla de nombres van de a dieciséis.
    crudo = _crudo(p, indice, "sprite_tiles")
    assert len(crudo) == registro.palabra("M_SPRITE_TILES") * BYTES_POR_TILE_4BPP
    visto = bytearray(_vram(p, registro.palabra("M_VRAM_SPRITE"), len(crudo)))
    esperado = bytearray(crudo)
    for fila in range(4):
        for col in range(4):
            tile = fila * 16 + col
            desde = tile * BYTES_POR_TILE_4BPP
            if desde < len(visto):
                visto[desde:desde + BYTES_POR_TILE_4BPP] = bytes(BYTES_POR_TILE_4BPP)
                esperado[desde:desde + BYTES_POR_TILE_4BPP] = bytes(BYTES_POR_TILE_4BPP)
    t = _distintos(bytes(visto), bytes(esperado), BYTES_POR_TILE_4BPP)
    if t:
        mal.append("tiles de sprites distintos: %s" % t[:12])
    return mal


def _mirar_la_wram(p, indice):
    """Lo que no coincide en la WRAM: los dibujos de la animación, que quedan
    todo lo que dure el mapa, y el buffer de carga, que tiene lo último que se
    descomprimió —los sprites: ver `cargar_mapa_sin_eventos`—."""
    s = p.simbolos
    mal = []
    for simbolo, clase in (("ANIM_DIBUJOS", "anim_tiles"),
                           ("LZ2_BUFFER", "sprite_tiles")):
        crudo = _crudo(p, indice, clase)
        visto = p.consola.ram(en_la_wram(s[simbolo]), len(crudo))
        t = _distintos(bytes(visto), crudo, BYTES_POR_TILE_4BPP)
        if t:
            mal.append("%s en %s distinto, tiles %s" % (clase, simbolo, t[:12]))
    return mal


def _recorrer(nucleo):
    """Una partida que pasa por todos los mapas de `release`, con lo que no
    coincidió en cada uno."""
    p = partida(None, en=cartuchos.RELEASE, nucleo=nucleo)
    with open(p.sfc, "rb") as f:
        p.rom = f.read()
    vistos = {}
    for indice, map_id in enumerate(p.mapas):
        _cargar(p, map_id)
        vistos[map_id] = _mirar_la_wram(p, indice)
        if nucleo != BSNES:
            vistos[map_id] += _mirar_la_vram(p, indice)
    return vistos


@pytest.mark.parametrize("nucleo", (None, BSNES), ids=("snes9x", "bsnes"))
def test_lo_cargado_es_lo_que_el_conversor_dice_en_cada_mapa(nucleo):
    vistos = _recorrer(nucleo)
    mal = ["mapa %d: %s" % (m, "; ".join(v)) for m, v in vistos.items() if v]
    assert not mal, "%d de %d mapas con otra cosa:\n%s" % (
        len(mal), len(vistos), "\n".join(mal))
