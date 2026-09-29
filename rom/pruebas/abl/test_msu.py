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

import json
import os
import shutil
from array import array

import pytest

from audio import snes_music
from emulador import retro
from rpgmaker.recursos import GAME_DIR

import tanda
from consola import (EMPEZAR, NUCLEO, SEGUIR, TITULO_AIRE, Partida,
                     en_la_rom, en_la_wram, indice_del_tema)
from ensamblado import cartuchos
from msu import pistas_de

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
    assert os.path.exists(base + ".msu") and pistas_de(base), (
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


# --- todo tema tiene su pista -----------------------------------------------
#
# Lo pidió taro el 2026-09-26: con MSU-1, **todos** los temas suenan desde su
# pista. El número lo da `snes_music.pista_msu` y las pistas las arma
# `tools/audio/msu.py` al lado de `release`; esto mira las tres cosas juntas
# —el `musica.json` del conversor, la `tema_msu` de la ROM y los `.pcm`—,
# porque cada una por separado puede estar bien y no coincidir con las otras.


def test_todo_tema_tiene_su_pista():
    uno = tanda.cartucho(cartuchos.RELEASE)
    base = os.path.splitext(uno.sfc)[0]
    with open(os.path.join(os.path.dirname(uno.sfc), "musica.json"),
              encoding="utf-8") as archivo:
        temas = json.load(archivo)["temas"]
    with open(uno.sfc, "rb") as archivo:
        rom = archivo.read()
    tabla = en_la_rom(uno.simbolos["tema_msu"])
    hay = pistas_de(base)
    sin, mal, faltan = [], [], []
    for i, tema in enumerate(temas):
        # "(OFF)", o un nombre que no está ni en Music/ ni en el del RTP: no
        # hay de dónde sacar la pista, y el tema no suena ni por el SPC700.
        if not snes_music.ruta_del_tema(tema["nombre"], GAME_DIR):
            continue
        numero = tema.get("pista")
        if not numero:
            sin.append(tema["nombre"])
        elif rom[tabla + i] != numero:
            mal.append("%s (%d en la ROM, %d en musica.json)"
                       % (tema["nombre"], rom[tabla + i], numero))
        elif numero not in hay:
            faltan.append("%s-%d.pcm (%s)" % (base, numero, tema["nombre"]))
    assert not sin, "estos temas entraron en el cartucho sin pista: %s" % sin
    assert not mal, "la `tema_msu` de la ROM no es la del conversor: %s" % mal
    assert not faltan, (
        "faltan las pistas %s: las arma `just build release`, ver "
        "tools/audio/msu.py" % ", ".join(faltan))
    for numero, ruta in sorted(hay.items()):
        with open(ruta, "rb") as archivo:
            assert archivo.read(4) == b"MSU1", "%s no es una pista" % ruta
    # Y al revés: una que no es de ningún tema la copiaría `just entregar`.
    sobran = sorted(set(hay) - {t.get("pista") for t in temas})
    assert not sobran, (
        "las pistas %s no son de ningún tema del cartucho: `msu.armar` tenía "
        "que borrarlas" % sobran)


# --- con MSU-1, el paquete no sube las muestras de los temas con pista -------
#
# Ver `tema_por_msu` en runtime/paquete_de_audio.s. Estas corren **con** el
# MSU-1, al revés que la tanda: sobre una copia de `release` en un directorio
# propio, con enlaces a sus pistas —a todas o a todas menos una— y, para el
# tema sin pista, con su entrada de `tema_msu` borrada en la copia.
#
# Los dos mapas son los de los temas que se prenden solos al llegar: el 26
# prende `KSSMKEND`, que es el único tema de su paquete, y el 19 prende
# `Gaden`, que comparte paquete con `3D-Galax`.
ARRANQUE = "en-5"


def _con_pistas(tmp_path, sin_pista=(), sin_tema_msu=(), caso=ARRANQUE,
                titulo=True):
    """Una copia de `release` con su `.msu` y sus pistas al lado, salvo las de
    los temas `sin_pista` —la tarjeta no las tiene— y con los temas
    `sin_tema_msu` marcados sin pista en el cartucho. Devuelve la partida.

    `caso=None` es la partida de verdad, la página 0; `titulo=False` la deja
    en la pantalla de título, sin elegir nada."""
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
    for numero in set(pistas_de(base)) - faltan:
        os.symlink("%s-%d.pcm" % (base, numero), "%s-%d.pcm" % (otra, numero))
    k = 0 if caso is None else uno.casos.index(caso)
    return Partida(sfc, uno.simbolos, uno.mapas, caso=k,
                   salta=bool(k) and uno.saltan[k], msu=True,
                   titulo=uno.titulo if titulo else None)


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


# --- con MSU-1, la pista del título se calla al empezar -----------------------
#
# Al elegir "Begin the Story", `pantalla_titulo` llama a `music_boot`, que con
# el mapa inicial callado —el de la apertura no trae tema: lo prende un
# `PlayBGM`— marcaba `music_apagada` y nada más. El SPC700 quedaba callado,
# pero la pista del título seguía sonando por el MSU-1 hasta el primer
# `PlayBGM`, y una pelea en el medio la anotaba como el tema a reponer.

# Cuadros de hardware desde que se elige hasta mirar: los que tarda en cargar
# el mapa y llamar a `music_boot`, con aire.
AL_EMPEZAR = 120


def test_con_msu_la_pista_del_titulo_no_sigue_en_la_partida(tmp_path):
    una = _con_pistas(tmp_path, caso=None, titulo=False)
    una.consola.correr(TITULO_AIRE)
    titulo = una.simbolos["TEMA_TITULO"]
    assert una.palabra("tema_actual") == titulo and _lejano(
        una, "MSU_SUENA")[0], (
        "la pantalla de título no está tocando su pista por el MSU-1: esta "
        "prueba no mide nada")

    una.titulo = EMPEZAR
    una.pasar_el_titulo(EMPEZAR)
    una.consola.correr(AL_EMPEZAR)
    assert una.byte("music_apagada"), (
        "la partida no arrancó con el SPC700 callado: o el mapa inicial "
        "trae tema, o un `PlayBGM` ya sonó, y el caso no pasa por el camino "
        "callado de `music_boot`")
    sigue = _lejano(una, "MSU_SUENA")[0] and una.palabra(
        "tema_actual") == titulo
    assert not sigue, (
        "%d cuadros después de empezar la partida la pista del título sigue "
        "sonando por el MSU-1: `music_boot` calló el SPC700 y no la pista"
        % AL_EMPEZAR)


# --- con MSU-1, el `FadeOutBGM` baja la pista y no los efectos ---------------
#
# El caso de `pruebas/rpgmaker/test_fundido_del_tema.py`, con las pistas al
# lado: `evilrhys` tiene pista, así que el fundido baja MSU_VOLUMEN y al
# llegar a cero la para, y el volumen general del DSP no se toca. Lo que se
# pide es eso, y que el efecto de después del fundido suene: con la pista
# parada, lo único que se oye es él.

# Por debajo de esto un pico es ruido de redondeo, no un efecto que suena.
AUDIBLE = 1000


def test_con_msu_el_fundido_para_la_pista_y_los_efectos_siguen(tmp_path):
    una = _con_pistas(tmp_path, caso="efecto-tras-el-fundido")
    sonaba = False
    efectos, actual = [], None
    for _ in range(900):
        antes = len(una.consola.audio)
        suena = _lejano(una, "MSU_SUENA")[0]
        sonaba |= bool(suena)
        una.correr(1)
        ocupada = any(_lejano(una, v, 3) != b"\0\0\0"
                      for v in ("SE_CUADROS", "SE2_CUADROS"))
        if ocupada:
            if actual is None:
                actual = [antes, suena, una.byte("bgm_fundido")]
                efectos.append(actual)
            actual[3:] = [len(una.consola.audio)]
        else:
            actual = None
            if len(efectos) == 3:
                break
    assert sonaba, "evilrhys no sonó por la pista: esta prueba no mide nada"
    assert len(efectos) == 3, (
        "el caso tenía que tocar tres efectos y se vieron %d" % len(efectos))
    inicio, suena, fundiendo, fin = efectos[2]
    assert not suena and not fundiendo, (
        "el tercer efecto arrancó con la pista sonando o el fundido andando: "
        "el `FadeOutBGM` no paró la pista del MSU-1")
    muestras = array("h", bytes(una.consola.audio[inicio:fin]))
    pico = max(abs(m) for m in muestras)
    assert pico >= AUDIBLE, (
        "con MSU-1, el efecto de después del fundido picó %d: el fundido de "
        "la pista calló también los efectos" % pico)


# --- con MSU-1, la partida guardada con pista no arranca muda ----------------
#
# Con una pista sonando, `music_apagada` vale 1: el SPC700 está callado a
# propósito. La partida guarda ese byte como "no suena nada", y al cargarla
# `music_boot_ya` tomaba el camino callado. Lo que viaja tiene que ser la
# respuesta a "¿está sonando?", que no depende de por dónde: ver
# `guardar_partida`.
#
# Se guarda en el mapa 26, que prende `KSSMKEND` —con pista— al llegar, y se
# carga en las cuatro combinaciones de con y sin MSU-1. La partida viaja de una
# consola a la otra por la SRAM, como un `.srm` que se lleva del FX Pak a un
# emulador sin las pistas: el core es uno solo por proceso, así que la segunda
# consola reemplaza a la primera.

# Cuadros de hardware después de elegir la ranura: los que tarda en cargar el
# mapa y llamar a `music_boot`, con aire.
AL_CARGAR = 120


def _la_misma_rom(una, msu):
    """Otra consola con la ROM de `una`, con o sin sus pistas."""
    uno = tanda.cartucho(cartuchos.RELEASE)
    k = uno.casos.index(ARRANQUE)
    return Partida(una.sfc, una.simbolos, una.mapas, caso=k,
                   salta=uno.saltan[k], msu=msu, titulo=uno.titulo)


@pytest.mark.parametrize("guarda,carga", [(True, True), (True, False),
                                          (False, True)],
                         ids=["msu-a-msu", "msu-a-spc700", "spc700-a-msu"])
def test_la_partida_guardada_vuelve_con_su_tema(tmp_path, guarda, carga):
    una = _con_pistas(tmp_path)
    if not guarda:
        una = _la_misma_rom(una, msu=False)
    _llegar(una, 26)
    tema = indice_del_tema(una, "KSSMKEND")
    assert una.palabra("tema_actual") == tema, "en el 26 no prendió KSSMKEND"
    assert bool(_lejano(una, "MSU_SUENA")[0]) == guarda, (
        "KSSMKEND tenía que sonar %s al guardar: el caso no es el que dice"
        % ("por la pista" if guarda else "por el SPC700"))
    una.guardar_por_el_menu()
    assert una.hay_partida(), "la partida no llegó a guardarse"
    srm = una.sram()

    if carga != guarda:
        una = _la_misma_rom(una, msu=carga)
        una.poner_sram(0, srm)
    una.reiniciar(SEGUIR)
    una.consola.correr(AL_CARGAR)
    assert una.mapa() == 26, "la partida no cargó en el mapa 26"
    assert una.palabra("tema_actual") == tema, (
        "la partida cargó con el tema %d y no con KSSMKEND"
        % una.palabra("tema_actual"))
    pista = bool(_lejano(una, "MSU_SUENA")[0])
    spc700 = not una.byte("music_apagada")
    if carga:
        assert pista, (
            "la partida guardada %s cargó con MSU-1 y KSSMKEND no suena por "
            "la pista (music_apagada en %d)"
            % ("con la pista sonando" if guarda else "sin MSU-1",
               una.byte("music_apagada")))
    else:
        assert spc700 and not pista, (
            "la partida guardada con la pista sonando cargó sin MSU-1 y "
            "KSSMKEND no suena por el SPC700: arrancó muda")
        faltan = sorted(set(una.muestras_del_tema(tema))
                        - una.muestras_en_la_aram())
        assert not faltan, (
            "KSSMKEND suena por el SPC700 sin las muestras %s" % faltan)
