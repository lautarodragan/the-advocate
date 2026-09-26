"""Que las pistas de MSU-1 al lado de `release/abl.sfc` no lleguen a la tanda.

`release` lleva siempre sus pistas —`just build release` las deja al lado de
la ROM— y el emulador busca el `.msu` al lado del `.sfc`: si el core lo
encontrara, cada prueba que escucha correría con el SPC700 callado. Lo evita
el arnés, que le da al core una copia de la ROM en un directorio vacío —ver
`retro.Consola`—, y esto es lo que lo cobra si deja de hacerlo.

Se escucha la pantalla de título, que es lo primero que suena y tiene pista.
La referencia es la misma ROM copiada a un directorio sin pistas, y el control
es pedirle el MSU-1 a la de `release/`: si con él el audio no cambiara, que
sin él sea igual a la referencia no probaría nada.
"""

import os
import shutil

from audio import snes_music
from emulador import retro

import tanda
from consola import (NUCLEO, Partida, en_la_rom, en_la_wram,
                     indice_del_tema)
from ensamblado import cartuchos

# Del encendido: a esta altura el tema del título ya suena, y con el MSU-1 lo
# toca la pista. Medido en snes9x y en bsnes.
CUADROS = 600


def _con_msu(sfc):
    consola = retro.Consola(sfc, NUCLEO, msu=True)
    consola.correr(CUADROS)
    return bytes(consola.audio)


def test_las_pistas_de_release_no_llegan_al_core(tmp_path):
    sfc = tanda.cartucho(cartuchos.RELEASE).sfc
    base = os.path.splitext(sfc)[0]
    assert os.path.exists(base + ".msu") and os.path.exists(base + "-1.pcm"), (
        "a %s le faltan sus pistas de MSU-1, así que esta prueba no compara "
        "nada: las deja `just build release`" % os.path.dirname(sfc))

    sola = os.path.join(tmp_path, os.path.basename(sfc))
    shutil.copyfile(sfc, sola)
    spc700 = _con_msu(sola)

    assert _con_msu(sfc) != spc700, (
        "con el MSU-1 pedido y las pistas al lado, el título suena igual que "
        "sin ellas: o el core dejó de buscarlas, o el tema dejó de tener "
        "pista, y la comparación de abajo no prueba nada")
    # Por donde entran las pruebas, sin pedir nada: es lo que se protege.
    assert bytes(tanda.encender(cartuchos.RELEASE, CUADROS).audio) == spc700, (
        "la consola de las pruebas encontró las pistas de MSU-1 de %s: la "
        "tanda está escuchando las pistas y no el SPC700. `retro.Consola` "
        "tiene que darle al core un directorio sin ellas"
        % os.path.dirname(sfc))


# --- con MSU-1, el paquete no sube las muestras de los temas con pista -------
#
# Ver `tema_por_msu` en rom/src/paquete_de_audio.s. Estas corren **con** el
# MSU-1, al revés que la tanda: sobre una copia de `release` en un directorio
# propio, con enlaces a sus pistas —a todas o a todas menos una— y, para el
# tema sin pista, con su entrada de `tema_msu` borrada en la copia.
#
# Los dos mapas son los de los temas que se prenden solos al llegar: el 26
# prende `KSSMKEND`, que es el único tema de su paquete, y el 19 prende
# `Gaden`, que comparte paquete con `3D-Galax`.
ARRANQUE = "en-5"


def _con_pistas(tmp_path, sin_pista=(), sin_tema_msu=()):
    """Una copia de `release` con su `.msu` y sus pistas al lado, salvo las de
    los temas `sin_pista` —la tarjeta no las tiene— y con los temas
    `sin_tema_msu` marcados sin pista en el cartucho. Devuelve la partida."""
    uno = tanda.cartucho(cartuchos.RELEASE)
    base = os.path.splitext(uno.sfc)[0]
    with open(uno.sfc, "rb") as archivo:
        rom = bytearray(archivo.read())
    nombres = _temas(uno.sfc)
    pistas = en_la_rom(uno.simbolos["tema_msu"])
    faltan = {rom[pistas + nombres.index(t)] for t in sin_pista}
    for tema in sin_tema_msu:
        rom[pistas + nombres.index(tema)] = 0xFF
    directorio = os.path.join(tmp_path, "tarjeta")
    os.makedirs(directorio)
    sfc = os.path.join(directorio, os.path.basename(uno.sfc))
    with open(sfc, "wb") as archivo:
        archivo.write(rom)
    otra = os.path.splitext(sfc)[0]
    os.symlink(base + ".msu", otra + ".msu")
    # `indice_del_tema` lee los nombres de al lado del `.sfc`.
    os.symlink(os.path.join(os.path.dirname(uno.sfc), "musicdata.inc"),
               os.path.join(directorio, "musicdata.inc"))
    for numero in set(snes_music.PISTAS_MSU.values()) - faltan:
        os.symlink("%s-%d.pcm" % (base, numero), "%s-%d.pcm" % (otra, numero))
    k = uno.casos.index(ARRANQUE)
    return Partida(sfc, uno.simbolos, uno.mapas, caso=k, salta=uno.saltan[k],
                   msu=True, titulo=uno.titulo)


def _temas(sfc):
    with open(os.path.join(os.path.dirname(sfc), "musicdata.inc")) as archivo:
        for linea in archivo:
            if linea.startswith("; Temas: "):
                return linea[len("; Temas: "):].strip().split(", ")
    raise AssertionError("el musicdata.inc de %s no dice sus temas" % sfc)


def _lejano(una, nombre, largo=1):
    return una.consola.ram(en_la_wram(una.simbolos[nombre]), largo)


def _llegar(una, mapa):
    una.ir_al_mapa(mapa, 5, 5, cuadros=200)
    return una.mapas.index(mapa)


def test_con_msu_el_paquete_no_sube_las_muestras_del_tema_con_pista(tmp_path):
    """El mapa 26 con todas las pistas: `KSSMKEND` suena por el MSU-1 y sus
    muestras no están en la ARAM; los efectos del paquete, todos."""
    una = _con_pistas(tmp_path)
    assert _lejano(una, "MSU_HAY")[0], (
        "el MSU-1 no se encendió: esta prueba no mide nada")
    indice = _llegar(una, 26)
    tema = indice_del_tema(una, "KSSMKEND")
    assert una.palabra("tema_actual") == tema and _lejano(una, "MSU_SUENA")[0], (
        "llegando al mapa 26 tenía que sonar KSSMKEND por el MSU-1")

    temas, efectos = una.muestras_del_paquete(indice)
    assert temas == [tema], "el paquete del 26 cambió: el caso no es el mismo"
    aram = una.muestras_en_la_aram()
    faltan = sorted(set(efectos) - aram)
    assert not faltan, "faltan los efectos %s del mapa 26" % faltan
    subidas = sorted((set(una.muestras_del_tema(tema)) - set(efectos)) & aram)
    assert not subidas, (
        "con MSU-1 y la pista en la tarjeta, el paquete del 26 subió las "
        "muestras %s de KSSMKEND, que suena por la pista: `tema_por_msu` no "
        "las salteó" % subidas)


def test_con_msu_el_tema_sin_pista_del_paquete_sube_sus_muestras(tmp_path):
    """El mapa 19 con `Gaden` sin pista en el cartucho: suena por el SPC700
    con todas sus muestras, y las de `3D-Galax`, que tiene pista y comparte el
    paquete, no se suben."""
    una = _con_pistas(tmp_path, sin_tema_msu=["Gaden"])
    indice = _llegar(una, 19)
    gaden = indice_del_tema(una, "Gaden")
    galax = indice_del_tema(una, "3D-Galax")
    assert sorted(una.muestras_del_paquete(indice)[0]) == sorted([gaden, galax])
    assert una.palabra("tema_actual") == gaden, "en el 19 no prendió Gaden"
    assert not _lejano(una, "MSU_SUENA")[0] and not una.byte("music_apagada"), (
        "Gaden no tiene pista y no está sonando por el SPC700")

    aram = una.muestras_en_la_aram()
    efectos = set(una.muestras_del_paquete(indice)[1])
    faltan = sorted(set(una.muestras_del_tema(gaden)) - aram)
    assert not faltan, (
        "Gaden suena por el SPC700 y le faltan las muestras %s" % faltan)
    solo_galax = (set(una.muestras_del_tema(galax))
                  - set(una.muestras_del_tema(gaden)) - efectos)
    assert solo_galax, "3D-Galax no tiene muestras propias: no compara nada"
    subidas = sorted(solo_galax & aram)
    assert not subidas, (
        "3D-Galax tiene pista y el paquete subió sus muestras %s" % subidas)


def test_con_msu_la_pista_que_falta_cae_al_spc700_con_sus_muestras(tmp_path):
    """El mapa 26 sin la pista de `KSSMKEND` en la tarjeta: el MSU-1 dice que
    no está, el tema suena por el SPC700, y como el paquete no la había subido
    —contaba con la pista—, `tema_asegurar` la sube al prenderlo. Y queda
    anotado en MSU_FALTA, para que los paquetes que siguen la suban de
    entrada."""
    una = _con_pistas(tmp_path, sin_pista=["KSSMKEND"])
    _llegar(una, 26)
    tema = indice_del_tema(una, "KSSMKEND")
    assert una.palabra("tema_actual") == tema
    assert not _lejano(una, "MSU_SUENA")[0] and not una.byte("music_apagada"), (
        "sin su pista en la tarjeta KSSMKEND tenía que caer al SPC700")
    faltan = sorted(set(una.muestras_del_tema(tema))
                    - una.muestras_en_la_aram())
    assert not faltan, (
        "KSSMKEND cayó al SPC700 sin las muestras %s: nadie las subió al ver "
        "que la pista faltaba" % faltan)
    falta = _lejano(una, "MSU_FALTA", (tema >> 3) + 1)[tema >> 3]
    assert falta & (1 << (tema & 7)), (
        "la pista de KSSMKEND faltó y MSU_FALTA no lo anotó")
