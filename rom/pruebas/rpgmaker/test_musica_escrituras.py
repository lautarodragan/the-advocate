"""Que el decodificador del 65816 escriba al DSP lo mismo que el stream dice,
cuadro por cuadro.

El stream de música es por nota desde el 2026-09-26 —ver "el formato por
nota" en `tools/audio/snes_music.py`— y lo expande `music_frame`
(runtime/musica.s) a escrituras al DSP. La propiedad que sostiene el formato
es que esas escrituras sean **exactamente** las de `snes_music.escrituras`:
mismo registro, mismo valor, mismo orden y mismo cuadro. Hay dos redes:

* el conversor decodifica cada tema con `snes_music.decodificar`, el modelo
  del decodificador, y se corta si no da `escrituras` (`verificar_formato`);
* y ésta, que cobra lo que el modelo no ve: el 65816. Toca cada tema entero
  en la ROM, anota lo que llega a `dsp_musica` —la bitácora, `MUS_BITACORA`,
  que la prueba prende— y lo compara contra el modelo corriendo sobre los
  bytes **del cartucho**.

Lo que se mira es la entrada de `dsp_musica` y no el DSP: el emulador no
expone la memoria del SPC700, y lo que pasa después de `dsp_musica` —la
sombra de las voces de los efectos, el acuse del SPC700— no cambió con el
formato y lo cubre `test_bateria_suena.py`.

Los temas se prenden por los dos caminos que hay: el del título lo prende el
código principal, como un `PlayBGM`, y los demás la IRQ, como al terminar
cada vuelta. Cada uno se mira entero y un poco de la segunda vuelta.
"""

import pytest

from consola import (EMPEZAR, TITULO_AIRE, WRAM, DelCartucho, en_la_rom,
                     en_la_wram, indice_del_tema)

from audio import music_opcodes

# Los que más formas del stream ejercitan, además del título —el pedal—: el
# de `escape_newyork`, el de batalla —el más pesado, y el peor cuadro—, el de
# 3D-Galax (CC11 y el bend con la nota sonando: `OP_SET_VOL` y
# `OP_SET_PITCH`) y el de TF3_1_awe (paneo en todas las notas y CC7 de
# compuerta: `OP_NOTE_PAN` y `OP_SET_PAN`).
TEMAS = ["escape_newyork", "T_VGFighterMAX_Masako", "3D-Galax", "TF3_1_awe"]

# Cuántos cuadros después del final se sigue mirando: la vuelta al principio
# tiene que escribir lo mismo que la primera vez.
DESPUES_DEL_FINAL = 120


def _por_cuadro(vuelta, largo):
    """Por cuadro, lo que el modelo escribe: dos vueltas del tema, para ver
    también la segunda. Lo que no escribe nada no está."""
    por_cuadro = {}
    for desfase in (0, largo):
        for cuadro, registro, valor in vuelta:
            por_cuadro.setdefault(cuadro + desfase, []).append(
                (registro, valor))
    return por_cuadro


def _fin_del_stream(rom, direccion):
    """La dirección del `OP_END` del stream, recorriéndolo por los largos que
    declara music.toml."""
    i, datos = 0, DelCartucho(rom, direccion)
    while datos[i] != music_opcodes.OP_END:
        i += music_opcodes.OPCODE_SIZE[datos[i]]
    # El desplazamiento en el archivo vuelve a ser una dirección de LoROM.
    archivo = en_la_rom(direccion) + i
    return (archivo // 0x8000) << 16 | 0x8000 | (archivo & 0x7FFF)


def _escribir(una, direccion, datos):
    una.consola.escribir_ram(en_la_wram(direccion), bytes(datos))


def _leer_bitacora(una, desde):
    s = una.simbolos
    largo = s["MUS_BITACORA_LARGO"]
    i = una.consola.ram(en_la_wram(s["MUS_BITACORA_I"]), 2)
    hasta = i[0] | i[1] << 8
    crudo = una.consola.ram(en_la_wram(s["MUS_BITACORA"]), largo)
    pares, j = [], desde
    while j != hasta:
        pares.append((crudo[j], crudo[j + 1]))
        j = (j + 2) % largo
    return pares, hasta


def _cuadros_de_la_rom(una, hasta, j=0, cuadros=None):
    """Lo que `dsp_musica` recibió, por cuadro de música, hasta tener
    `hasta` cuadros.

    Se parte por las marcas de cuadro y no por los cuadros del emulador: un
    cuadro pesado —la vuelta al principio del de batalla, con el arranque y
    cuatro notas— termina después de que el emulador entregó el suyo.
    """
    marca = una.simbolos["MUS_BITACORA_MARCA"]
    cuadros = [] if cuadros is None else cuadros
    for _ in range(2 * hasta):
        if len(cuadros) > hasta:
            break
        una.consola.correr(1)
        pares, j = _leer_bitacora(una, j)
        for par in pares:
            if par[0] == marca:
                cuadros.append([])
            else:
                assert cuadros, "una escritura antes de la primera marca"
                cuadros[-1].append(par)
    assert len(cuadros) > hasta, (
        "en %d cuadros del emulador la música corrió %d: `music_frame` no "
        "corre en cada cuadro" % (2 * hasta, len(cuadros)))
    return cuadros


def _comparar(nombre, cuadros, vuelta):
    """Cuadro por cuadro, la vuelta entera y el principio de la segunda."""
    # Vuelve a empezar en el cuadro de sus últimas escrituras, las que apagan
    # todo: ahí mismo lee el `OP_END`.
    largo = vuelta[-1][0]
    esperado = _por_cuadro(vuelta, largo)
    for cuadro in range(largo + DESPUES_DEL_FINAL):
        quiere = esperado.get(cuadro, [])
        assert cuadros[cuadro] == quiere, (
            "%s, cuadro %d del stream: la ROM le pidió al DSP %s y el stream "
            "dice %s (registro, valor)"
            % (nombre, cuadro,
               [("$%02X" % r, "$%02X" % v) for r, v in cuadros[cuadro]],
               [("$%02X" % r, "$%02X" % v) for r, v in quiere]))


@pytest.mark.parametrize("nombre", TEMAS)
def test_la_rom_escribe_lo_que_el_stream_dice(partida, nombre):
    """Cada tema arranca por el camino del loop: se apunta el stream a su
    `OP_END` con el tema en `tema_actual`, así que en el cuadro siguiente
    `music_frame` vuelve al principio con `music_start_ya`, que es lo mismo
    que hace al terminar cada vuelta. Las muestras no se suben
    —`tema_asegurar` no corre—, así que no suena lo que se toca; las
    escrituras son las mismas."""
    una = partida(titulo=EMPEZAR).quedarse_en_el_titulo()
    s = una.simbolos
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    tema = indice_del_tema(una, nombre)
    vuelta = una.escrituras_del_tema(tema)
    fin = _fin_del_stream(rom, una.stream_del_tema(tema)[0])

    # Todo entre dos cuadros, que es cuando la consola no está corriendo.
    _escribir(una, s["music"], [fin & 0xFF, fin >> 8 & 0xFF, fin >> 16])
    _escribir(una, s["tema_actual"], [tema, 0])
    _escribir(una, s["MUS_ESPERA"], [0, 0])
    _escribir(una, s["MUS_SONANDO"], [0])
    _escribir(una, s["MUS_KON"], [0])
    _escribir(una, s["music_apagada"], [0])
    _escribir(una, s["MUS_BITACORA_I"], [0, 0])
    _escribir(una, s["MUS_BITACORA_SI"], [1])
    cuadros = _cuadros_de_la_rom(una, vuelta[-1][0] + DESPUES_DEL_FINAL)
    _comparar(nombre, cuadros, vuelta)


def test_el_tema_del_titulo_desde_el_encendido(partida):
    """El otro camino: el tema lo prende el código principal —`music_start`
    desde la pantalla de título, como un `PlayBGM`—, y no la IRQ. Ahí los
    registros traen lo que dejó el juego, y así apareció el primer error del
    decodificador: `music_start_ya` ponía la espera en cero con un `lda #0`
    de ocho bits y un `sta` de dieciséis, y B traía basura. El tema esperaba
    miles de cuadros antes de la primera nota, y el camino de la IRQ, donde B
    llega en cero, no lo veía.

    La bitácora se prende en cada cuadro desde el reset —el arranque la
    apaga— hasta que aparece la primera marca: ése es el cuadro 0 del tema.
    """
    una = partida(titulo=EMPEZAR)
    s = una.simbolos
    tema = s["TEMA_TITULO"]
    vuelta = una.escrituras_del_tema(tema)
    una.consola.escribir_ram(0, bytes([0x55]) * WRAM)
    una.consola.reset()
    for _ in range(s["BOOT_CUADROS"] + TITULO_AIRE):
        _escribir(una, s["MUS_BITACORA_I"], [0, 0])
        _escribir(una, s["MUS_BITACORA_SI"], [1])
        una.consola.correr(1)
        if _leer_bitacora(una, 0)[1]:
            break
    else:
        raise AssertionError("la pantalla de título no prendió su tema")
    assert una.palabra("tema_actual") == tema
    cuadros = _cuadros_de_la_rom(una, vuelta[-1][0] + DESPUES_DEL_FINAL)
    _comparar("el tema del título", cuadros, vuelta)
