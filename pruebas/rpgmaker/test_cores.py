"""La misma ROM en dos emuladores, y las dos pantallas comparadas **entre sí**.

Acá no hay golden: lo que se compara es snes9x contra bsnes, cuadro contra
cuadro, y eso contesta exactamente la pregunta para la que esto existe —"anda en
snes9x y no en la consola"— sin depender de un tercer programa que también se
puede equivocar.

Por qué vale la pena: **bsnes llena la WRAM
de basura al encender** —`bsnes_entropy`, que `retro.py` pone en "High"—, que es
lo que hace la consola de verdad; snes9x la deja siempre en el mismo estado, y
por eso la tanda entera daba verde con `ruta_n`/`ruta_i` sin inicializar, que sin
inicializar quedan iguales entre sí. Si las dos capturas difieren, **la ROM
depende de memoria que nadie escribió**: no es ruido del emulador y no se
arregla con tolerancia. No lo agarra siempre —la basura tiene que caer en un
valor que rompa—, pero no cuesta nada: medido en su momento sobre 20 corridas
del mapa 7 con esas dos líneas comentadas, con `bsnes_entropy` en "None"
difieren 0 corridas, con "Low" 3 y con "High" 11.

## Por qué se compara a 15 bits y por qué eso **no** es una tolerancia

La comparación es exacta —cero pixeles— pero sobre el cuadro de 15 bits, que es
lo que la consola muestra, y no sobre los 8 bits por canal que devuelve el
frontend. La diferencia importa: a 8 bits los tres casos dan entre el 10% y el
96% de pixeles distintos, y **ninguno de esos pixeles es un pixel distinto de la
consola**. Es que cada core expande sus 5 bits a 8 a su manera, y `retro.py`
encima los recibe en formatos distintos —snes9x en RGB565, bsnes en XRGB8888—:
para un mismo nivel 8 del canal azul, snes9x escribe 65 y bsnes 66.

Volver a recortar los tres bits bajos deshace exactamente esa expansión, que es
lo mismo que hace `tanda.quince_bits` para las demás pruebas y por la misma
razón. Y
que lo deshaga *exactamente* no se supone: lo mide
`test_los_dos_cores_expanden_a_8_bits_sin_pisarse`, que comprueba que los dos
cores emiten a lo sumo 32 niveles por canal y que cada nivel cae en su propio
tramo de ocho. Con eso, un nivel de diferencia de verdad —que a 8 bits son ocho
unidades— sigue saltando, y lo único que el recorte tapa son las dos unidades
del frontend.

## Los casos, y por qué cada uno

    evento        tiñe la pantalla desde un evento: CGRAM y el intérprete.
    caminando     camina: la RAM del control, que es la que tenía el error.
    cerrar        el mensaje. Es el código que más CGRAM y VRAM toca con la
                  pantalla apagada —`load_ventana` sube tiles y una paleta
                  entera, `estampar_ventana` escribe su tilemap—, que es justo
                  la clase de escritura que snes9x perdona y ahí ya nos mordió
                  dos veces. De paso trae `msg_abierto`, una variable de RAM que
                  si nadie pone en cero deja la página bloqueada para siempre.
    escena        la pelea compuesta: lo que más memoria nueva estrena. Ver su
                  docstring.
    autofire      X sostenido cierra cinco mensajes seguidos: el camino de
                  `read_pad` con su contador, que ninguno de los otros aprieta.

## El tercer core, mesen-s, queda afuera, y no por lo que parecía

Está instalado y `retro.py` lo maneja, así que se probó. **No se suma porque su
resultado depende de qué ROM se cargó antes en el mismo proceso**, que es la
clase de inestabilidad que no se puede tener en una prueba: los cuatro casos
corridos solos dan cero contra snes9x, y los mismos cuatro corridos uno detrás
del otro dan cero en `evento` y `cerrar-60` y 38.775 y 52.892 pixeles en
`caminando` y `cerrar-400`. Un core de libretro no se descarga entre una
`retro.Consola` y la siguiente —ctypes reusa el mismo `.so`, sin `retro_deinit`—
y mesen-s se arrastra estado ahí donde snes9x y bsnes no. O sea que el rojo no
diría nada de la ROM.

Lo que se esperaba encontrar y **no** es lo que pasa: mesen-s trunca el brillo
maestro donde los otros dos redondean, así que el pronóstico era que fallara
adentro de un fundido y anduviera afuera. Medido, es al revés —el caso teñido da
cero y el que no tiene fundido falla—, lo que confirma que lo que se está viendo
es el arrastre de estado y no el brillo.
"""

import os

import pytest

from consola import RAIZ
from tanda import partida, quince_bits, ticks_de_avance

# Los dos cores, por ruta. bsnes es el preciso y el que enciende con basura;
# snes9x es el de todas las demás pruebas, así que una diferencia acá es
# exactamente la distancia entre lo que mira la tanda entera y lo que haría la
# consola.
SNES9X = "/usr/lib/libretro/snes9x_libretro.so"
BSNES = "/usr/lib/libretro/bsnes_libretro.so"

# Cuántos niveles tiene un canal de la consola, que es propiedad del hardware:
# 5 bits por canal, 15 en total.
NIVELES = 32


def iguales(nombre, una, otra):
    """Las dos capturas, y tienen que ser idénticas a 15 bits.

    Cuando difieren, las dos quedan en `pruebas/snapshots/cores/`, al lado de
    las de los otros rojos, para poder mirarlas una al lado de la otra. Acá no
    hay golden que reemplazar: lo único que se puede hacer con un rojo es ir a
    buscar qué lee la ROM sin haberlo escrito.
    """
    assert una.size == otra.size, (
        "%s: snes9x da %s y bsnes %s" % (nombre, una.size, otra.size))
    aqui, alla = quince_bits(una), quince_bits(otra)
    if aqui == alla:
        return
    distintos = sum(1 for a, b in zip(aqui, alla) if a != b)
    donde = os.path.join(RAIZ, "pruebas", "snapshots", "cores")
    os.makedirs(donde, exist_ok=True)
    una.save(os.path.join(donde, "%s-snes9x.png" % nombre))
    otra.save(os.path.join(donde, "%s-bsnes.png" % nombre))
    raise AssertionError(
        "%s: snes9x y bsnes dibujan distinto en %d de %d pixeles (%.2f%%), a 15 "
        "bits. Las dos capturas quedaron en %s. bsnes enciende con la WRAM "
        "llena de basura y snes9x en cero, así que esto dice que la ROM lee "
        "memoria que nadie inicializó: no se arregla con tolerancia."
        % (nombre, distintos, len(aqui), 100.0 * distintos / len(aqui), donde))


def dos_cores(caso, ticks, **como):
    """La misma partida corrida en los dos cores; devuelve las dos pantallas."""
    return tuple(partida(caso, nucleo=nucleo)
                 .correr(ticks, **como).imagen()
                 for nucleo in (SNES9X, BSNES))


# El mapa 4: prende dos switches, tiñe la pantalla y teletransporta. Es la
# página que abre A Blurred Line, y lo que se ve es el mapa destino ya teñido
# sin haber tocado una tecla.
EVENTO = "grupo-11-en-4"


def test_evento():
    """El tinte desde un evento: CGRAM y el intérprete, en los dos cores."""
    iguales("evento", *dos_cores(EVENTO, 240))


def test_caminando():
    """El héroe del mapa 73 con 60 pixeles andados hacia la derecha.

    El avance no es un número de ticks sino la cuenta de `ticks_de_avance`, y
    errarle por uno mueve media pantalla. Es el caso que mira el movimiento en
    sí, o sea la RAM del control: es ahí donde vivía `ruta_n`/`ruta_i` sin
    inicializar, que es el error que estrenó esta comparación.
    """
    iguales("caminando-73-right-60",
            *dos_cores("grupo-11-en-73", ticks_de_avance(60),
                       sosteniendo=("right",)))


@pytest.mark.parametrize("cuadro", (60, 400))
def test_cerrar(cuadro):
    """La ventana de mensaje abierta (60) y cerrada con A (400).

    El toque de A cae un tick antes del número, que es `RETRASO_DE_PANTALLA`, y
    los ticks se miran con margen y no en el borde: a los 60 el mensaje está
    abierto hace rato y a los 400 hace rato que se cerró.
    """
    iguales("cerrar-%d" % cuadro,
            *dos_cores("cerrar", cuadro, apretar_a=(200,)))


def test_autofire():
    """Los cinco mensajes de `autofire` cerrados con X sostenido.

    **No cobra que `arranque` ponga el contador en cero**: el arnés aprieta X
    recién pasado el arranque, y para entonces cada `read_pad` con X suelto
    ya lo puso en cero. Ese `stz` es para un X apretado desde el encendido,
    que ninguna prueba hace. Lo que mira esto es el camino con X en el core
    que arranca con basura."""
    iguales("autofire-120",
            *dos_cores("autofire", 120, sosteniendo=("x",)))


def test_los_dos_cores_expanden_a_8_bits_sin_pisarse():
    """Que recortar a 15 bits **no** sea una tolerancia disfrazada.

    Los dos cores expanden los 5 bits de la consola a 8 de maneras distintas, y
    esa diferencia es la única que `quince_bits` tiene permitido tapar. Lo que
    se comprueba acá es que taparla no tape nada más: sobre un cuadro de verdad,
    cada core emite a lo sumo 32 valores por canal —los niveles de la consola— y
    **cada valor cae en un tramo de ocho distinto**, así que `>> 3` devuelve el
    nivel y no mezcla dos.

    Con eso, un nivel de diferencia de verdad —ocho unidades a 8 bits— sigue
    dando rojo, y lo único que se pierde son las una o dos unidades del
    frontend. Si un core cambiara su expansión y dos niveles suyos cayeran en el
    mismo tramo, esto se pone en rojo antes de que los otros casos
    empiecen a dar cero por la razón equivocada.
    """
    for nombre, imagen in zip(("snes9x", "bsnes"),
                              dos_cores(EVENTO, 240)):
        canales = list(zip(*imagen.convert("RGB").get_flattened_data()))
        for cual, valores in zip("rgb", canales):
            vistos = set(valores)
            assert len(vistos) <= NIVELES, (
                "%s: el canal %s tiene %d valores distintos y la consola sólo "
                "puede mostrar %d" % (nombre, cual, len(vistos), NIVELES))
            assert len({v >> 3 for v in vistos}) == len(vistos), (
                "%s: dos valores del canal %s caen en el mismo tramo de ocho, "
                "así que recortar a 15 bits los confunde: %s"
                % (nombre, cual, sorted(vistos)))


def test_escena_de_la_pelea():
    """La escena de la pelea compuesta en la consola, y un enemigo borrado.

    Es lo que más memoria nueva estrena: los dos búferes de 32 KB del banco $7F
    —que bsnes enciende con basura— y el estado de `ESC_*`. Si la ROM leyera
    un byte de ahí sin haberlo escrito, el fondo, un battler o las celdas del
    borrado saldrían distintos. Es el encuentro de la tropa 100 de
    `test_batalla_escena_dibujo.py`, con el del medio muerto a mano.
    """
    from consola import en_la_wram
    imagenes = []
    for nucleo in (SNES9X, BSNES):
        una = partida("en-5", nucleo=nucleo)
        una.ir_al_mapa(28, 20, 30)
        s = una.simbolos
        una.consola.escribir_ram(en_la_wram(s["ENC_SEM"]), [22, 0])
        una.consola.escribir_ram(en_la_wram(s["ENC_PIDE"]), [1])
        una.consola.correr(120)
        assert una.byte("menu_abierto"), "la pelea no se abrió"
        donde = s["BA_UNO"] + (s["BA_GRUPO_MAX"] + 1) * s["BA_BYTES"]
        una.consola.escribir_ram(en_la_wram(donde), [0, 0])
        una.consola.correr(60)
        assert una.consola.ram(en_la_wram(s["ESC_VIS"]), 1)[0] == 0b101, \
            "el enemigo del medio no se borró: la prueba no mide lo que dice"
        imagenes.append(una.imagen())
    iguales("escena", *imagenes)
