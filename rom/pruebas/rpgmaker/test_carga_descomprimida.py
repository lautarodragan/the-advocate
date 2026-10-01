"""Lo que queda en la VRAM y en la WRAM después de cargar cada mapa es, byte
por byte, lo que el conversor dice que tiene que haber.

Desde el 2026-09-26 los tiles del mapa, de los sprites, de la capa de encima y
de la animación del ChipSet viajan en el cartucho comprimidos en LZ2, y la ROM
los descomprime al cargar el mapa —ver `lz2_decompress` en
runtime/decompress.s—. La propiedad que hace verificable ese cambio es que
**lo que llega a la VRAM no cambió**, y eso es lo que se mira acá, en todos los
mapas de `release`: contra `crudos/`, que el conversor deja al lado del
cartucho sin comprimir —ver `write_raw`— y no contra nada que salga de la
ROM.

Se mira justo después de la carga, en el primer cuadro en que `fade_kind`
volvió a cero: el fundido congela el juego, así que hasta que termine nadie
pisa lo que se subió. Dos cosas sí cambian y se miran por su lado: la corrida
animada del ChipSet, que `anim_load` pisa con el dibujo que le toca al reloj
—tiene que ser **uno** de los dibujos del bloque—, y la pose del héroe, que
`place_hero` puede cambiar ya en ese cuadro si no mira hacia abajo.

Corre también en bsnes, que enciende con la WRAM llena de basura: un
descompresor que leyera algo sin inicializar daría otra cosa ahí. Ese core no
expone la VRAM por libretro, así que ahí se mira lo que quedó en la WRAM.
"""

import os

import pytest

from consola import en_la_rom, en_la_wram
import cartuchos
from tanda import partida

BSNES = "/usr/lib/libretro/bsnes_libretro.so"
BYTES_POR_TILE_8BPP = 64
BYTES_POR_TILE_4BPP = 32


def _crudo(p, indice, clase):
    with open(os.path.join(os.path.dirname(p.sfc), "crudos",
                           "%d.%s.bin" % (indice, clase)), "rb") as f:
        return f.read()


class Registro:
    """El registro de un mapa en `map_table`, leído del cartucho."""

    def __init__(self, p, rom, indice):
        self.s = p.simbolos
        self.base = (en_la_rom(self.s["map_table"])
                     + indice * self.s["MAP_STRIDE"])
        self.rom = rom

    def palabra(self, campo):
        k = self.base + self.s[campo]
        return self.rom[k] | (self.rom[k + 1] << 8)

    def byte(self, campo):
        return self.rom[self.base + self.s[campo]]

    def puntero(self, campo):
        k = self.base + self.s[campo]
        return self.rom[k] | (self.rom[k + 1] << 8) | (self.rom[k + 2] << 16)


def _corridas_animadas(p, rom, indice):
    """[(palabra de VRAM, bytes por dibujo, desplazamiento del dibujo 0)] de
    las familias que animan en este mapa, leídas de `anim_table`."""
    s = p.simbolos
    corridas = []
    for familia in range(s["ANIM_FAMILIES"]):
        k = (en_la_rom(s["anim_table"]) + indice * s["ANIM_STRIDE"]
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
    antes = p.palabra("ticks")
    for cuadros in range(1, 400):
        p.consola.run(1)
        if not p.byte("fade_kind"):
            assert p.mapa() == map_id, (
                "pedí el mapa %d y la ROM cargó el %d" % (map_id, p.mapa()))
            return cuadros - (p.palabra("ticks") - antes) + 1
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
        # que sigue: ver `anim_bytes` en `rm2k-snes-mapdata`.
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


def _grilla(p):
    """La grilla que hay en la WRAM, con el largo de la del mapa: la mitad
    alta del banco $7E y, si pasa de 32 KB, la del $7F. Ver `GRID`."""
    s = p.simbolos
    largo = p.palabra("map_width") * p.palabra("map_height") * 2
    mitad = s["GRID_END"] - s["GRID"]
    baja = p.consola.ram(en_la_wram(s["GRID"]), min(largo, mitad))
    alta = (p.consola.ram(en_la_wram(s["GRID_HIGH"]), largo - mitad)
            if largo > mitad else b"")
    return bytes(baja) + bytes(alta)


def _mirar_la_grilla(p, indice):
    crudo = _crudo(p, indice, "map_cells")
    visto = _grilla(p)
    if visto == crudo:
        return []
    if len(visto) != len(crudo):
        return ["la grilla mide %d y el conversor dice %d" % (len(visto), len(crudo))]
    celdas = [k for k in range(0, len(crudo), 2) if visto[k:k + 2] != crudo[k:k + 2]]
    return ["%d celdas de la grilla distintas, la primera en el byte %d"
            % (len(celdas), celdas[0])]


def _mirar_detras_de_la_grilla(p, indice):
    """La tabla de bloques, su pasabilidad y el bytecode, que viven en la
    WRAM justo donde termina la grilla —ver `lz2_grid`—: que el registro y
    `map_code` apunten ahí y que esté lo que el conversor dice. La dirección
    la pone el conversor y el lugar lo decide el descompresor, así que esto
    mira que coincidan."""
    s = p.simbolos
    bloques = _crudo(p, indice, "map_ram")
    codigo = _crudo(p, indice, "map_code")
    crudo = bloques + codigo
    registro = Registro(p, p.rom, indice)
    mitad = s["GRID_END"] - s["GRID"]
    lugar = s["GRID_HIGH"] + max(0, len(_crudo(p, indice, "map_cells")) - mitad)
    mal = []
    if registro.puntero("M_PTR_MAP_BLOCKS") != lugar:
        mal.append("la tabla de bloques está en $%06X y el registro apunta a $%06X"
                   % (lugar, registro.puntero("M_PTR_MAP_BLOCKS")))
    pasabilidad = registro.puntero("M_PTR_BLOCK_PASS")
    if not lugar <= pasabilidad <= lugar + len(crudo):
        mal.append("la pasabilidad apunta a $%06X, afuera de lo que hay detrás "
                   "de la grilla" % pasabilidad)
    fila = en_la_rom(s["map_code"]) + indice * s["MAP_CODE_STRIDE"]
    base = p.rom[fila + 4] | (p.rom[fila + 5] << 8)
    largo = p.rom[fila + 6] | (p.rom[fila + 7] << 8)
    if (base, largo) != ((lugar + len(bloques)) & 0xFFFF, len(codigo)):
        mal.append("map_code dice que el bytecode está en $%04X y mide %d; está "
                   "en $%04X y mide %d" % (base, largo,
                                           (lugar + len(bloques)) & 0xFFFF,
                                           len(codigo)))
    visto = bytes(p.consola.ram(en_la_wram(lugar), len(crudo)))
    if visto != crudo:
        k = next(k for k in range(len(crudo)) if visto[k] != crudo[k])
        mal.append("lo que hay detrás de la grilla es distinto desde el byte %d" % k)
    return mal


def _mirar_la_wram(p, indice):
    """Lo que no coincide en la WRAM: la grilla, los dibujos de la animación,
    que quedan todo lo que dure el mapa, y el buffer de carga, que tiene lo
    último que se descomprimió —los sprites: ver `enter_map_no_events`—."""
    s = p.simbolos
    mal = _mirar_la_grilla(p, indice) + _mirar_detras_de_la_grilla(p, indice)
    for simbolo, clase in (("ANIM_DRAWINGS", "anim_tiles"),
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


# --- la grilla y la pelea -----------------------------------------------------
#
# La mitad alta del banco $7F es a la vez el final de las grillas de más de 32
# KB y `SCN_SCENE`, la escena compuesta de la pelea: pelear la pisa, y
# `back_from_battle` vuelve a descomprimir la grilla, y con ella lo que vive
# detrás —la tabla de bloques y su pasabilidad—. El mapa 52 es el de la
# grilla más grande, 40.000 B, y el caso `pelea-en-52` pelea ahí contra el
# droide con Kersh, que lo gana.

PELEA_EN_52 = "pelea-en-52"


@pytest.mark.parametrize("nucleo", (None, BSNES), ids=("snes9x", "bsnes"))
def test_la_grilla_vuelve_entera_de_una_pelea(nucleo):
    p = partida(PELEA_EN_52, nucleo=nucleo)
    s = p.simbolos
    indice = p.mapas.index(52)
    crudo = _crudo(p, indice, "map_cells")
    mitad = s["GRID_END"] - s["GRID"]
    assert len(crudo) > mitad, (
        "la grilla del mapa 52 mide %d: no llega a la mitad del $7F y esto no "
        "prueba nada" % len(crudo))
    assert _grilla(p) == crudo, "la grilla ya estaba mal antes de pelear"
    alta = en_la_wram(s["GRID_HIGH"])
    pisada, cuadros = False, 0
    # Todo en cuadros de hardware: la pelea no cuenta ticks. A cada nueve
    # cuadros, que es lo que pasa los mensajes y elige atacar.
    for cuadros in range(1, 4000):
        p.consola.hold(*(("a",) if cuadros % 9 < 2 else ()))
        p.consola.run(1)
        if p.byte("menu_open"):
            pisada = pisada or (bytes(p.consola.ram(alta, len(crudo) - mitad))
                                != crudo[mitad:])
        elif pisada:
            break
    else:
        raise AssertionError("la pelea no terminó en %d cuadros" % cuadros)
    p.consola.hold()
    assert pisada, (
        "la pelea no pisó la mitad alta del $7F: si la escena se mudó, esta "
        "prueba ya no mira el camino de `back_from_battle`")
    antes = p.palabra("ticks")
    for _ in range(240):
        p.consola.run(1)
        if p.palabra("ticks") - antes >= 2:
            break
    assert p.mapa() == 52, "la pelea no volvió al mapa 52: volvió al %d" % p.mapa()
    with open(p.sfc, "rb") as f:
        p.rom = f.read()
    mal = _mirar_la_grilla(p, indice) + _mirar_detras_de_la_grilla(p, indice)
    assert not mal, "la grilla después de la pelea: %s" % mal


# --- el fondo de dos flujos ----------------------------------------------------
#
# Un fondo de más de `LZ2_CAP_BACKDROP` bytes va en dos flujos, y `lz2_backdrop`
# sube el primero antes de descomprimir el segundo en el mismo lugar. Antes de
# eso el fondo del 66 se descomprimía entero y lo que no entraba en el buffer
# de carga caía en `GRID_HIGH`: en el 66, que usa sólo la mitad baja, andaba
# de casualidad. La prueba de arriba mira que llegue entero a la VRAM; ésta,
# con un testigo escrito en `GRID_HIGH`, que no se salga del buffer.


def test_un_fondo_de_dos_flujos_no_se_sale_del_buffer():
    p = partida(None, en=cartuchos.RELEASE)
    with open(p.sfc, "rb") as f:
        p.rom = f.read()
    s = p.simbolos
    grandes = [m for k, m in enumerate(p.mapas)
               if len(_crudo(p, k, "map_tiles")) > s["LZ2_CAP_BACKDROP"]]
    assert grandes, (
        "ningún mapa de `release` tiene el fondo en dos flujos: esta prueba "
        "no mira el camino de dos de `lz2_backdrop`")
    map_id = grandes[0]
    indice = p.mapas.index(map_id)
    mitad = s["GRID_END"] - s["GRID"]
    assert len(_crudo(p, indice, "map_cells")) <= mitad, (
        "la grilla del mapa %d usa la mitad alta, y ahí el testigo lo pisaría "
        "ella: hace falta otro mapa" % map_id)
    # El testigo va después de lo que vive detrás de la grilla —la tabla de
    # bloques, su pasabilidad y el bytecode, que la carga escribe ahí a
    # propósito—, y eso se mira contra el conversor.
    alta = en_la_wram(s["GRID_HIGH"]) + len(_crudo(p, indice, "map_ram")) \
        + len(_crudo(p, indice, "map_code"))
    testigo = bytes(range(256)) * 16
    p.consola.write_ram(alta, list(testigo))
    _cargar(p, map_id)
    assert bytes(p.consola.ram(alta, len(testigo))) == testigo, (
        "cargar el mapa %d pisó `GRID_HIGH`: el fondo se salió del buffer "
        "de carga" % map_id)
    mal = _mirar_la_vram(p, indice) + _mirar_detras_de_la_grilla(p, indice)
    assert not mal, "el mapa %d: %s" % (map_id, "; ".join(mal))


# --- lo que sigue corriendo en otro mapa ---------------------------------------
#
# El bytecode vive detrás de la grilla desde el 2026-10-01, y el mapa que se
# carga pone el suyo en ese lugar. Una página que sigue después de un
# `Teleport` se lleva el suyo a `CODE_CARRY`, y eso lo corre cada caso de la
# tanda, que empieza saltando y sigue. La ruta forzada del héroe, que sigue
# caminando en el mapa nuevo como en RM2k, se copia entera a `ROUTE_CARRY`:
# eso no lo corre ningún caso, y por eso se mira acá, con el estado escrito
# desde afuera como en `test_animacion_cuadros.py`.

ESPERAR = 23  # la orden de ruta `wait`: veinte cuadros cada una


def test_la_ruta_del_heroe_sigue_entera_en_el_mapa_nuevo():
    p = partida(None, en=cartuchos.RELEASE)
    with open(p.sfc, "rb") as f:
        p.rom = f.read()
    s = p.simbolos
    # Una ruta de esperas en el banco del bytecode, al final de la mitad del
    # $7F, donde no llega lo de atrás de la grilla de ningún mapa de `release`.
    donde = s["GRID_HIGH"] + 0x7F00
    ruta = bytes([ESPERAR] * 40)
    p.consola.write_ram(en_la_wram(donde), list(ruta))
    p.consola.write_ram(s["hero_route"],
                        [donde & 0xFF, (donde >> 8) & 0xFF, donde >> 16])
    p.consola.write_ram(s["route_n"], [len(ruta)])
    p.consola.write_ram(s["route_i"], [0])
    otro = next(m for m in p.mapas if m != p.mapa())
    _cargar(p, otro)
    b = p.consola.ram(s["hero_route"], 3)
    assert b[0] | (b[1] << 8) | (b[2] << 16) == s["ROUTE_CARRY"], (
        "la ruta del héroe no se mudó a ROUTE_CARRY al cambiar de mapa")
    assert p.byte("route_i") < len(ruta), (
        "la ruta terminó antes de cambiar de mapa: esto no mira nada")
    copiada = bytes(p.consola.ram(en_la_wram(s["ROUTE_CARRY"]), len(ruta)))
    assert copiada == ruta, "la ruta copiada no es la que el héroe venía haciendo"
