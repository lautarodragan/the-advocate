"""La caja de la animación de batalla tiene en la VRAM el cuadro que tiene que
tener, byte por byte, para **cada cuadro de cada animación** del cartucho.

Desde el 2026-09-26 el cartucho no guarda los cuadros enteros sino sólo sus
tiles con algo —ver `frame_without_gaps` en `rm2k-snes-mapdata`—, y la ROM los
rearma en la RAM lejana antes de subirlos. La propiedad que hace verificable
ese cambio es que **lo que llega a la VRAM no cambió**, y eso es lo que se mira
acá: contra `animation_frame`, que es la cuenta de los 2 KB sin comprimir y
ninguna de las rutinas de la ROM.

Las goldens de `animacion-dibujo` miran cinco cuadros de una animación; esto
mira todos. Para llegar a las que ningún caso muestra, se le cambia a la ROM la
fila de la animación que está dibujando —`ANIMB_ROW`, `ANIMB_N`— y se la deja
correr: el tick arma cada cuadro con el mismo camino que usa el juego. Es
escribir el estado y preguntarle a la ROM qué hace con él, no saltearse el
camino que se prueba.
"""

import pytest

from port import animation, events
from port.battle_animations import animation_frame
from render.render_map import Renderer
from rpgmaker.resources import GAME_DIR

from consola import en_la_rom, en_la_wram
from tanda import partida

# La 78 sobre el héroe, en el mapa 6: el caso de las goldens del dibujo.
CASO = "animacion-dibujo"
ANIM_B_STRIDE = 8
ANIM_B_BYTES = 2048
SIN_DIBUJO = 0xFF
# Y en bsnes también, que enciende con la WRAM llena de basura: el buffer donde
# se rearma el cuadro es RAM lejana, y lo único que lo pone en cero es la carga
# del mapa. Ver `test_cores.py`.
BSNES = "/usr/lib/libretro/bsnes_libretro.so"


def _palabra(p, nombre, valor=None):
    donde = en_la_wram(p.simbolos[nombre])
    if valor is None:
        b = p.consola.ram(donde, 2)
        return b[0] | (b[1] << 8)
    p.consola.write_ram(donde, [valor & 0xFF, valor >> 8])


def _byte(p, nombre, valor=None):
    donde = en_la_wram(p.simbolos[nombre])
    if valor is None:
        return p.consola.ram(donde, 1)[0]
    p.consola.write_ram(donde, [valor])


def _animaciones_del_cartucho(p):
    """{número de RM2k: fila en `anim_battle_table`}, leído de la ROM."""
    with open(p.sfc, "rb") as archivo:
        rom = archivo.read()
    de = en_la_rom(p.simbolos["anim_battle"])
    return {n: rom[de + n] for n in range(p.simbolos["ANIM_B_MAX"])
            if rom[de + n] != SIN_DIBUJO}


def _caja(p, nucleo):
    """Lo que hay en la caja. bsnes no expone la VRAM por libretro, así que ahí
    se mira `ANIMB_BUF`, que es de donde el vblank la copia entera."""
    if nucleo == BSNES:
        return p.consola.ram(en_la_wram(p.simbolos["ANIMB_BUF"]), ANIM_B_BYTES)
    palabras = p.consola.vram(_palabra(p, "ANIMB_VRAM"), ANIM_B_BYTES // 2)
    return b"".join(w.to_bytes(2, "little") for w in palabras)


def _correr_la_animacion(p, nucleo, fila, cuadros):
    """Pone a dibujar la animación de la fila `fila` desde su primer cuadro y
    devuelve {cuadro: lo que quedó en la caja después de subirlo}."""
    _palabra(p, "ANIMB_ROW", fila * ANIM_B_STRIDE)
    _palabra(p, "ANIMB_N", cuadros)
    _palabra(p, "ANIMB_T", 0)
    _palabra(p, "ANIMB_FRAME", 0xFFFF)
    _byte(p, "ANIMB_ACTIVE", 1)
    vistos = {}
    for _ in range(2 * cuadros + 4):
        p.correr(1)
        if not _byte(p, "ANIMB_ACTIVE"):
            break
        # Recién elegido y todavía no subido: la caja tiene el anterior.
        if _byte(p, "ANIMB_UPLOAD"):
            continue
        vistos.setdefault(_palabra(p, "ANIMB_FRAME"), _caja(p, nucleo))
    return vistos


@pytest.fixture(scope="module")
def esperados():
    events.index_animations(GAME_DIR)
    renderer = Renderer()
    return lambda numero: [animation_frame(c) for c in
                           animation.by_number(renderer, numero)["cuadros"]]


@pytest.mark.parametrize("nucleo", (None, BSNES), ids=("snes9x", "bsnes"))
def test_la_caja_tiene_cada_cuadro_de_cada_animacion(esperados, nucleo):
    p = partida(CASO, nucleo=nucleo)
    p.correr(20)
    assert _byte(p, "ANIMB_ACTIVE"), (
        "la 78 no se está dibujando: el caso %s dejó de mostrarla" % CASO)
    filas = _animaciones_del_cartucho(p)
    assert len(filas) > 1, "el cartucho lleva una sola animación: esto no mira nada"
    mal, cuadros_vistos = [], 0
    for numero, fila in sorted(filas.items()):
        quiero = esperados(numero)
        vistos = _correr_la_animacion(p, nucleo, fila, len(quiero))
        assert set(vistos) == set(range(len(quiero))), (
            "la animación %d tiene %d cuadros y la caja mostró %s"
            % (numero, len(quiero), sorted(vistos)))
        for k, esperado in enumerate(quiero):
            cuadros_vistos += 1
            if vistos[k] != esperado:
                distintos = [t for t in range(ANIM_B_BYTES // 32)
                             if vistos[k][t * 32:(t + 1) * 32]
                             != esperado[t * 32:(t + 1) * 32]]
                mal.append("animación %d, cuadro %d: tiles distintos %s"
                           % (numero, k, distintos))
    assert not mal, "%d de %d cuadros no son los que tienen que ser:\n%s" % (
        len(mal), cuadros_vistos, "\n".join(mal[:20]))


def test_la_caja_vuelve_entera_del_menu(esperados):
    """Con una animación a medio dibujar, abrir y cerrar el menú de pausa no
    deja tiles de más en la caja.

    Desde el 2026-10-01 cada cuadro se descomprime a `LZ2_BUFFER` y el
    anterior se borra leyendo sus tiles de ahí; volver del menú —o de la
    tienda, de las ranuras o de una pelea— pasa por `back_to_map`, que sube
    otra vez los tiles del mapa por ese mismo buffer. Sin `anim_buf_clear` al
    final de `back_to_map`, el cuadro anterior se borraba leyendo tiles de
    fondo como si fueran números de la caja: quedaban tiles viejos y se
    escribía más allá de `ANIMB_BUF`.
    """
    p = partida(CASO)
    p.correr(20)
    filas = _animaciones_del_cartucho(p)
    numero, fila = max(filas.items(), key=lambda f: len(esperados(f[0])))
    quiero = esperados(numero)
    # Que termine la página del caso, que espera a su animación: el menú
    # sólo se abre con el héroe libre.
    for _ in range(600):
        if not p.byte("ev_active"):
            break
        p.correr(1)
    else:
        raise AssertionError("la página del caso %s no terminó" % CASO)
    _palabra(p, "ANIMB_ROW", fila * ANIM_B_STRIDE)
    _palabra(p, "ANIMB_N", len(quiero))
    _palabra(p, "ANIMB_T", 0)
    _palabra(p, "ANIMB_FRAME", 0xFFFF)
    _byte(p, "ANIMB_ACTIVE", 1)
    p.correr(6)
    assert _palabra(p, "ANIMB_FRAME") > 0, "la animación no avanzó"
    p.consola.hold("b")
    p.consola.run(2)
    p.consola.hold()
    for _ in range(120):
        if p.byte("menu_open"):
            break
        p.consola.run(1)
    else:
        raise AssertionError("B no abrió el menú de pausa")
    p.consola.run(30)
    p.consola.hold("b")
    p.consola.run(2)
    p.consola.hold()
    for _ in range(120):
        if not p.byte("menu_open"):
            break
        p.consola.run(1)
    else:
        raise AssertionError("B no cerró el menú de pausa")
    mal = []
    for _ in range(2 * len(quiero)):
        p.correr(1)
        if not _byte(p, "ANIMB_ACTIVE"):
            break
        if _byte(p, "ANIMB_UPLOAD"):
            continue
        k = _palabra(p, "ANIMB_FRAME")
        if _caja(p, None) != quiero[k]:
            mal.append(k)
    assert not mal, (
        "después del menú, la animación %d mostró mal los cuadros %s"
        % (numero, sorted(set(mal))))
