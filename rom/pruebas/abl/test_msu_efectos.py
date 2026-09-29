"""Los efectos de sonido con MSU-1: las voces 0 a 5 y los efectos del `.msu`.

Con MSU-1 y el SPC700 sin música, un efecto que no entra en la 7 ni en la 6
toma una de las voces 0 a 5; y si el `.msu` es el de este cartucho, los
efectos de cada paquete se suben de ahí, enteros y a la tasa que les entra.
Ver runtime/efectos_con_msu.s y tools/audio/efectos_msu.py. La tanda corre
sin MSU-1 —el arnés le esconde el `.msu` al core—, así que eso lo cubren las
pruebas de siempre; esto cubre el otro camino.

Los dos casos son de acá:

* `efecto-de-calidad`: `Success2` en el mapa 10, que en el cartucho va
  recortado a tres cuartos de segundo, a 6 kHz y con bucle, y en el `.msu`
  entero a 22 kHz: el paquete del 10 son dos efectos y entran enteros.
* `tres-efectos`: `Glass`, `Flash3` y `Earth4` en el mismo cuadro en el mapa
  3, con `evilrhys` sonando. Es el momento de la escena de `evilrhys` que
  tiene tres efectos a la vez.

Y uno de `pruebas/rpgmaker/test_sonido_en_ruta.py`, `sonido-en-ruta`: `Close1`
pedido adentro de una ruta forzada del héroe, en el mapa 10.

Corren en snes9x, como `test_msu.py`.
"""

import json
import os
import shutil
from array import array

import numpy

from audio import brr_samples, snes_music
from port import msu_datos

import tanda
from consola import Partida, en_la_rom, en_la_wram
from ensamblado import cartuchos
from msu import pistas_de

# Por debajo de esto un pico es ruido de redondeo, no un efecto que suena.
AUDIBLE = 1000


def _partida(tmp_path, nombre, caso, msu):
    """Una copia de `release` en su directorio, con `msu` —los bytes de un
    `.msu`— y todas las pistas al lado, y el caso elegido."""
    uno = tanda.cartucho(cartuchos.RELEASE)
    base = os.path.splitext(uno.sfc)[0]
    directorio = os.path.join(tmp_path, nombre)
    os.makedirs(directorio)
    sfc = os.path.join(directorio, os.path.basename(uno.sfc))
    shutil.copyfile(uno.sfc, sfc)
    otra = os.path.splitext(sfc)[0]
    with open(otra + ".msu", "wb") as archivo:
        archivo.write(msu)
    for numero in pistas_de(base):
        os.symlink("%s-%d.pcm" % (base, numero), "%s-%d.pcm" % (otra, numero))
    k = uno.casos.index(caso)
    return Partida(sfc, uno.simbolos, uno.mapas, caso=k, salta=uno.saltan[k],
                   msu=True, titulo=uno.titulo)


def _msu_del_cartucho():
    tanda.cartucho(cartuchos.RELEASE)       # se niega si está viejo
    with open(cartuchos.msu_de(cartuchos.RELEASE), "rb") as archivo:
        return archivo.read()


def _lejano(una, nombre, largo=1):
    return una.consola.ram(en_la_wram(una.simbolos[nombre]), largo)


def _efectos_cambiados(msu, firma):
    """Una copia del `.msu` con las muestras de todos los efectos negadas —las
    cabeceras de cada bloque de BRR quedan como estaban— y la firma de la
    cabecera tal cual, o recalculada si `firma`: con ella es el `.msu` de otro
    build, que la ROM no tiene que leer."""
    fondos = 2 * tanda.cartucho(cartuchos.RELEASE).simbolos["MSU_FONDOS_N"]
    entradas = [bytearray(e) for e in msu_datos.leer(msu)]
    for entrada in entradas[fondos:]:
        for i in range(len(entrada)):
            if i % brr_samples.BLOCK_BYTES:
                entrada[i] ^= 0xFF
    if firma:
        return msu_datos.armar([bytes(e) for e in entradas])[0]
    donde = msu_datos.indice(msu)
    otro = bytearray(msu)
    for (inicio, largo), entrada in zip(donde[fondos:], entradas[fondos:]):
        otro[inicio:inicio + largo] = entrada
    return bytes(otro)


def _el_efecto(una, cuadros=400):
    """Corre hasta que el efecto de la voz 7 arranca y termina. Devuelve (el
    audio, en mono y en flotante, la tasa, y lo que quedó en SE_NUEVO)."""
    inicio = nuevo = None
    for _ in range(cuadros):
        antes = len(una.consola.audio)
        una.correr(1)
        estado = _lejano(una, "SE_CUADROS", 12)
        suena = estado[0] or estado[1]
        if inicio is None and suena:
            inicio, nuevo = antes, bytes(estado[5:12])
        elif inicio is not None and not suena:
            break
    assert inicio is not None, "el efecto del caso no arrancó"
    muestras = numpy.frombuffer(bytes(una.consola.audio[inicio:]),
                                dtype="<i2").astype(float)
    return muestras[0::2] + muestras[1::2], una.consola.sample_rate(), nuevo


def _envolvente(muestras, tasa, paso=0.02):
    n = int(tasa * paso)
    k = len(muestras) // n
    return numpy.sqrt((muestras[:k * n].reshape(k, n) ** 2).mean(1))


def test_con_msu_el_efecto_suena_entero_y_a_su_tasa(tmp_path):
    """`Success2` en el mapa 10: con el `.msu` del cartucho, la altura es la de
    22.050 Hz, suena como el WAV de punta a punta —la envolvente lo sigue y
    termina callada, sin la meseta que repite el recortado— y los bytes
    salieron del `.msu`: el control, con las muestras cambiadas y la firma
    intacta, suena distinto."""
    msu = _msu_del_cartucho()
    una = _partida(tmp_path, "con", "efecto-de-calidad", msu)
    muestras, tasa, nuevo = _el_efecto(una)
    assert _lejano(una, "MSU_SE")[0] == 1, (
        "con MSU-1 y el .msu del cartucho, la ROM no lo aceptó para los "
        "efectos: o no encontró la firma, o no lo miró")
    assert not _lejano(una, "MSU_SUENA")[0], (
        "en el mapa 10 no tenía que sonar ninguna pista: el audio del efecto "
        "no se puede mirar solo")
    altura = int.from_bytes(nuevo[1:3], "little")
    esperada = snes_music.effect_pitch(
        snes_music.SoundEffect("Success2", b"", 22050, None, 0), 100)
    assert altura == esperada, (
        "Success2 arrancó con la altura %d y la de 22.050 Hz es %d: la ROM no "
        "tomó la del .msu, o el paquete del 10 dejó de entrar a la tasa del "
        "WAV" % (altura, esperada))

    crudo, fuente = snes_music.read_wav("Success2")
    del_wav = _envolvente(numpy.array(crudo, float), fuente)
    grabada = _envolvente(muestras, tasa)
    n = min(len(grabada), len(del_wav)) - 5
    parecido = max(numpy.corrcoef(grabada[k:k + n], del_wav[:n])[0, 1]
                   for k in range(5))
    assert parecido > 0.92, (
        "la envolvente de Success2 con MSU-1 no sigue la del WAV (%.3f): no "
        "suena entero, o no suena a su velocidad" % parecido)
    cola = grabada[-5:].mean() / grabada.max()
    cola_del_wav = del_wav[-5:].mean() / del_wav.max()
    assert cola < max(0.05, 2 * cola_del_wav), (
        "Success2 con MSU-1 termina al %.0f%% de su pico y el WAV al %.0f%%: "
        "suena el recortado, que repite su último tramo hasta el final"
        % (100 * cola, 100 * cola_del_wav))

    control = _partida(tmp_path, "control", "efecto-de-calidad",
                       _efectos_cambiados(msu, firma=False))
    cambiadas, _tasa, _nuevo = _el_efecto(control)
    assert _lejano(control, "MSU_SE")[0] == 1
    n = min(len(cambiadas), len(muestras))
    assert not numpy.array_equal(cambiadas[:n], muestras[:n]), (
        "con las muestras del .msu cambiadas Success2 suena igual: la ROM no "
        "lo está subiendo de ahí, y lo de arriba no prueba nada")


def test_con_msu_el_efecto_de_una_ruta_suena_entero(tmp_path):
    """El efecto de una ruta forzada va por el mismo camino que el de un
    `PlaySound` —`sonido_tocar`—, así que con el `.msu` del cartucho suena
    igual: `Close1` en el mapa 10, a la altura de 22.050 Hz, con la
    envolvente del WAV."""
    una = _partida(tmp_path, "ruta", "sonido-en-ruta", _msu_del_cartucho())
    muestras, tasa, nuevo = _el_efecto(una)
    assert _lejano(una, "MSU_SE")[0] == 1, (
        "con MSU-1 y el .msu del cartucho, la ROM no lo aceptó para los "
        "efectos")
    altura = int.from_bytes(nuevo[1:3], "little")
    esperada = snes_music.effect_pitch(
        snes_music.SoundEffect("Close1", b"", 22050, None, 0), 100)
    assert altura == esperada, (
        "Close1 arrancó con la altura %d y la de 22.050 Hz es %d" % (
            altura, esperada))
    crudo, fuente = snes_music.read_wav("Close1")
    del_wav = _envolvente(numpy.array(crudo, float), fuente)
    grabada = _envolvente(muestras, tasa)
    n = min(len(grabada), len(del_wav)) - 5
    parecido = max(numpy.corrcoef(grabada[k:k + n], del_wav[:n])[0, 1]
                   for k in range(5))
    assert parecido > 0.92, (
        "la envolvente de Close1 con MSU-1 no sigue la del WAV (%.3f)"
        % parecido)


def test_con_un_msu_de_otro_build_los_efectos_salen_de_la_rom(tmp_path):
    """Un `.msu` que no es el de este cartucho —bien formado, con su firma, y
    otros efectos— no se lee: Success2 suena como con un `.msu` vacío, que es
    el de la ROM, con su altura."""
    msu = _msu_del_cartucho()
    otro = _efectos_cambiados(msu, firma=True)
    assert otro[:msu_datos.FIRMA] != msu[:msu_datos.FIRMA]
    grabados = {}
    for nombre, archivo in (("vacio", b""), ("otro", otro)):
        una = _partida(tmp_path, nombre, "efecto-de-calidad", archivo)
        muestras, _tasa, nuevo = _el_efecto(una)
        assert _lejano(una, "MSU_HAY")[0], "el MSU-1 no se encendió"
        assert _lejano(una, "MSU_SE")[0] == 2, (
            "con el .msu %s la ROM lo aceptó para los efectos: no está "
            "mirando la firma" % nombre)
        grabados[nombre] = (muestras, nuevo)
    (vacio, nuevo_vacio), (de_otro, nuevo_otro) = (grabados["vacio"],
                                                  grabados["otro"])
    assert nuevo_otro == nuevo_vacio
    assert numpy.array_equal(de_otro, vacio), (
        "con el .msu de otro build Success2 no suena como con uno vacío: la "
        "ROM subió algo de ahí")
    rom = tanda.cartucho(cartuchos.RELEASE)
    with open(rom.sfc, "rb") as archivo:
        cartucho = archivo.read()
    fila = en_la_rom(rom.simbolos["sonido_tabla"]) + 7 * _indice_de(
        rom, nuevo_vacio)
    assert nuevo_vacio == cartucho[fila:fila + 7], (
        "sin el .msu, Success2 no arrancó con la fila de `sonido_tabla`")


def _indice_de(rom, nuevo):
    """El índice de la fila de `sonido_tabla` que empieza con la muestra de
    `nuevo`, con volumen 100 al centro: la de Success2."""
    with open(rom.sfc, "rb") as archivo:
        cartucho = archivo.read()
    base = en_la_rom(rom.simbolos["sonido_tabla"])
    for k in range(rom.simbolos["SONIDOS_N"]):
        if cartucho[base + 7 * k:base + 7 * k + 7] == nuevo:
            return k
    raise AssertionError("ninguna fila de sonido_tabla es %s" % nuevo.hex())


def test_con_msu_tres_efectos_suenan_a_la_vez(tmp_path):
    """El mapa 3 con `evilrhys` por la pista y tres efectos en el mismo
    cuadro: la 7, la 6 y una de las voces 0 a 5, con las tres muestras
    distintas. Y el tercero se oye: la misma corrida con las voces 0 a 5
    apagadas justo antes —`MSU_HAY` en cero, que es lo que mira
    `ex_permitidas`— suena distinto, y la diferencia es audible."""
    msu = _msu_del_cartucho()
    grabados = []
    for apagar in (False, True):
        una = _partida(tmp_path, "tres-%d" % apagar, "tres-efectos", msu)
        estado = None
        for _ in range(600):
            antes = len(una.consola.audio)
            if apagar and una.palabra("tema_actual") == _tema(una, "evilrhys"):
                una.consola.write_ram(
                    en_la_wram(una.simbolos["MSU_HAY"]), [0])
            una.correr(1)
            siete = _lejano(una, "SE_CUADROS", 12)
            if siete[0] or siete[1]:
                estado = (siete, _lejano(una, "SE2_CUADROS", 12),
                          _lejano(una, "EX_CUADROS", 26))
                break
        assert estado is not None, "los efectos del caso no arrancaron"
        una.correr(60)
        grabados.append(array("h", bytes(una.consola.audio[antes:])))
        if apagar:
            continue
        assert _lejano(una, "MSU_SUENA")[0] and una.byte("music_apagada"), (
            "evilrhys no sonó por la pista: el SPC700 tenía la música y las "
            "voces 0 a 5 no son de los efectos")
        siete, seis, extras = estado
        ocupadas = extras[25]           # EX_OCUP, detrás de EX_CUADROS y EX_IDX
        assert seis[0] or seis[1], "el segundo efecto no tomó la voz 6"
        assert ocupadas, (
            "con MSU-1 y la pista sonando, el tercer efecto no tomó ninguna de "
            "las voces 0 a 5")
        voz = (ocupadas & -ocupadas).bit_length() - 1
        idx = int.from_bytes(extras[12 + 2 * voz:14 + 2 * voz], "little")
        rom = tanda.cartucho(cartuchos.RELEASE)
        with open(rom.sfc, "rb") as archivo:
            cartucho = archivo.read()
        tercera = cartucho[en_la_rom(rom.simbolos["sonido_tabla"]) + 7 * idx]
        muestras = {siete[5], seis[5], tercera}
        assert len(muestras) == 3, (
            "las tres voces tocan las muestras %s: no son los tres efectos"
            % sorted(muestras))
    con, sin = grabados
    n = min(len(con), len(sin))
    diferencia = max(abs(a - b) for a, b in zip(con[:n], sin[:n]))
    assert diferencia >= AUDIBLE, (
        "con el tercer efecto en una de las voces 0 a 5 el audio difiere en "
        "%d de la corrida sin ellas: el tercero no se oye" % diferencia)


def _tema(una, nombre):
    with open(os.path.join(os.path.dirname(tanda.cartucho(
            cartuchos.RELEASE).sfc), "musicdata.inc")) as archivo:
        for linea in archivo:
            if linea.startswith("; Temas: "):
                return linea[len("; Temas: "):].strip().split(", ").index(
                    nombre)
    raise AssertionError("el musicdata.inc no dice sus temas")


def test_con_msu_un_sonido_que_no_es_del_paquete_va_con_su_altura_de_la_rom(
        tmp_path):
    """La otra salida de `altura_msu`: el sonido no está en la lista del
    paquete, y la altura queda la de `sonido_tabla`. Es `efecto-de-calidad`
    con `PAQ_MAPA` cambiado, al llegar al 10, por un paquete cuya lista no
    tiene a Success2 y sí algún sonido de índice mayor —para que la búsqueda
    corte por pasar de largo y no sólo en el $FFFF—: la ROM no guarda qué
    versión subió, así que la lista es lo único que mira."""
    rom = tanda.cartucho(cartuchos.RELEASE)
    with open(rom.sfc, "rb") as archivo:
        cartucho = archivo.read()
    with open(os.path.join(os.path.dirname(rom.sfc), "efectos.json")) as a:
        sonidos = json.load(a)["sonidos"]
    k = sonidos.index(["Success2", 100, 100, 50])

    def palabra(donde):
        return int.from_bytes(cartucho[donde:donde + 2], "little")
    paq = en_la_rom(rom.simbolos["se_msu_altura_paq"])
    alturas = en_la_rom(rom.simbolos["se_msu_altura"])
    elegido = None
    for p in range(rom.simbolos["PAQUETES_N"]):
        donde, indices = alturas + palabra(paq + 2 * p), []
        while palabra(donde) != 0xFFFF:
            indices.append(palabra(donde))
            donde += 4
        if k not in indices and any(i > k for i in indices):
            elegido = p
            if any(i < k for i in indices):
                break
    assert elegido is not None, "ningún paquete sirve para la prueba"

    una = _partida(tmp_path, "ajeno", "efecto-de-calidad", _msu_del_cartucho())
    una.consola.write_ram(en_la_wram(rom.simbolos["PAQ_MAPA"]),
                          elegido.to_bytes(2, "little"))
    _muestras, _tasa, nuevo = _el_efecto(una)
    assert _lejano(una, "MSU_SE")[0] == 1
    fila = en_la_rom(rom.simbolos["sonido_tabla"]) + 7 * k
    assert nuevo[1:3] == cartucho[fila + 1:fila + 3], (
        "Success2 con el paquete %d, que no lo lleva, arrancó con la altura "
        "%d y la de sonido_tabla es %d" % (
            elegido, int.from_bytes(nuevo[1:3], "little"),
            palabra(fila + 1)))
