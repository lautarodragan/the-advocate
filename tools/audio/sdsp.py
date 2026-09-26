"""El chip de sonido de la Super Nintendo: registros, envolventes y volumen.

El S-DSP no sintetiza nada por su cuenta: reproduce muestras. Ocho voces, cada
una leyendo una muestra de la memoria del SPC700 a la velocidad que se le pida,
con envolvente ADSR y volumen por canal. La altura de la nota sale de la
velocidad de lectura, así que una sola muestra sirve para todas las notas.

Eso cambia por completo el problema respecto del YM2612. Allá el timbre había
que construirlo con cuatro operadores y nueve parámetros cada uno, a ciegas.
Acá el timbre es la muestra, y las muestras salen de un SoundFont de General
MIDI: las arma snes_samples.py.

Las envolventes también salen del SoundFont: `envelope` traduce las de cada
zona a lo que el ADSR y el GAIN del DSP saben hacer.
"""

import math

VOICES = 8
SAMPLE_RATE = 32000     # a lo que lee el DSP con paso 1:1
CYCLE = 32              # muestras por ciclo de las ondas del banco
MAX_PITCH = 0x3FFF

# --- registros --------------------------------------------------------------
# Los de cada voz están de a 16: la voz v usa v*$10 + el número de abajo.
V_VOL_L, V_VOL_R = 0x00, 0x01
V_PITCH_L, V_PITCH_H = 0x02, 0x03
V_SRCN = 0x04
V_ADSR1, V_ADSR2 = 0x05, 0x06
V_GAIN = 0x07

# Los globales viven en las columnas $x C y $x D.
MVOL_L, MVOL_R = 0x0C, 0x1C
EVOL_L, EVOL_R = 0x2C, 0x3C
KON, KOF = 0x4C, 0x5C
FLG = 0x6C
PMON, NON, EON = 0x2D, 0x3D, 0x4D
DIR = 0x5D

FLG_BASE = 0x20         # eco apagado; los cinco bits bajos son el ruido


# --- las envolventes --------------------------------------------------------
#
# Salen del SoundFont, generadores 33 a 40, que `gunter sf2 --json` devuelve
# por zona —ver `muestras_brr.envolvente`—. Hasta el 2026-09-25 salían de
# ocho familias elegidas a ojo cuando el banco era sintético, y lo que más
# difería era el release: el bajo sintético y la sierra se sueltan en 30 ms en
# el SF2 y acá arrastraban 2,4 s de cola.
#
# Lo que el DSP sabe hacer, y por eso la traducción no es directa: cada fase
# avanza un paso cada tantas muestras de las 32.000 por segundo, y cuántas lo
# dice `PERIODO` por el número de tasa de 5 bits (0 es "nunca"). El ataque es
# lineal y llega arriba en 64 pasos; el decaimiento, el sostenido y el GAIN
# exponencial restan 1/256 del nivel por paso; el GAIN lineal resta 1/64.
PERIODO = [None, 2048, 1536, 1280, 1024, 768, 640, 512, 384, 320, 256, 192,
           160, 128, 96, 80, 64, 48, 40, 32, 24, 20, 16, 12, 10, 8, 6, 5, 4, 3,
           2, 1]

# El release del ADSR del DSP no se puede configurar: al escribir KOF la
# envolvente cae a cero en unos 8 ms, que se oye como un corte seco. Por eso
# soltar una nota no se hace con KOF sino apagando el bit de ADSR —con lo que
# manda GAIN— y pidiéndole una caída, cuya velocidad sí se elige. La
# envolvente sigue desde donde estaba, así que la nota se apaga en vez de
# cortarse.
GAIN_LINEAR_DECREASE = 0x80     # bit 7: modo propio; bits 5-6: lineal
GAIN_EXP_DECREASE = 0xA0        # bits 5-6: exponencial

# **La caída exponencial del DSP no es exponencial hasta el final**: por
# debajo de 1/8 del nivel resta de a uno, y desde arriba llega a cero en unos
# 790 pasos. Hacerla coincidir en pendiente con la del SoundFont la apaga
# antes de tiempo —el piano se callaba a los 1,4 s en vez de seguir a
# -26 dB—, así que se la hace llegar a cero donde el SoundFont anda por
# -40 dB, que es "ya no se oye". Lo midió el prototipo de
# `workflow/tasks/todo/la-calidad-de-la-musica.md`.
PASOS_HASTA_CERO = 790
HASTA_DB = 40.0
# Un release más corto que esto va con GAIN lineal: la exponencial más rápida
# tarda 25 ms en llegar a cero y no alcanza para los 30 ms del bajo.
RELEASE_LINEAL = 0.1
# Un ataque más corto que esto es instantáneo (A = 15): el más rápido de los
# otros, A = 14, ya tarda 4 ms.
ATAQUE_INSTANTANEO = 0.004
# Y por debajo de cuánto se considera que la nota se apaga sola mientras se
# la mantiene: entonces no hay nivel de sostenido que imitar, sino una caída
# que seguir.
SOSTENIDO_MUDO_DB = 30.0

# dB que baja un paso exponencial: 20·log10(256/255).
_DB_POR_PASO = 20 * math.log10(256 / 255.0)


def _segundos(timecents):
    """Los timecents del SoundFont: 1200 por octava, 0 es un segundo y
    -12000 es "nada"."""
    return 2.0 ** (timecents / 1200.0) if timecents > -12000 else 0.0


def _tasa_cerca(segundos, duracion, tasas):
    """De `tasas`, la que hace durar a la fase lo más parecido a `segundos`
    en escala logarítmica. `duracion(tasa)` dice cuánto dura con esa."""
    return min(tasas, key=lambda r: abs(math.log(max(duracion(r), 1e-9)
                                                 / max(segundos, 1e-9))))


def _hasta_cero(r):
    """Cuánto tarda una caída exponencial de tasa `r` en llegar a cero."""
    return PASOS_HASTA_CERO * PERIODO[r] / float(SAMPLE_RATE)


def envelope(sf2, key):
    """(ADSR1, ADSR2, GAIN del release) para una nota, desde la envolvente de
    volumen de su zona en el SoundFont: el dict con los `env_*` de `gunter
    sf2 --json`."""
    ataque = _segundos(sf2["env_attack_timecents"]) + _segundos(
        sf2["env_hold_timecents"])
    # El decaimiento se acorta con la tecla, alrededor del do central.
    decae = _segundos(sf2["env_decay_timecents"]
                      + sf2["env_key_to_decay"] * (60 - key))
    sostenido_db = sf2["env_sustain_centibels"] / 10.0
    suelta = _segundos(sf2["env_release_timecents"])

    # Ataque: A de 0 a 14 usa la tasa 2A+1 y sube en 64 pasos.
    if ataque < ATAQUE_INSTANTANEO:
        ar = 15
    else:
        ar = _tasa_cerca(ataque, lambda a: 64 * PERIODO[2 * a + 1]
                         / float(SAMPLE_RATE), range(15))

    # El SoundFont baja 100 dB en `decae` segundos, en línea recta en dB.
    if sostenido_db >= SOSTENIDO_MUDO_DB:
        # Se apaga sola: el nivel de sostenido arriba de todo —la fase de
        # decaimiento termina en el acto— y el sostenido baja con la caída
        # del SoundFont, hasta cero donde ella llega a -40 dB.
        sl, dr = 7, 0
        sr = _tasa_cerca(decae * HASTA_DB / 100.0, _hasta_cero, range(1, 32))
    else:
        # Baja hasta un nivel y se queda: SL en octavos, y el decaimiento
        # (tasa 2D+16) con la pendiente del SoundFont. Arriba de 1/8 la caída
        # del DSP sí es exponencial, así que acá la pendiente es lo que vale.
        nivel = 10 ** (-sostenido_db / 20.0)
        sl = max(0, min(7, int(round(8 * nivel)) - 1))
        periodo = _DB_POR_PASO * SAMPLE_RATE / (100.0 / max(decae, 1e-3))
        dr = _tasa_cerca(periodo, lambda d: PERIODO[2 * d + 16], range(8))
        sr = 0

    if suelta < RELEASE_LINEAL:
        r = _tasa_cerca(suelta, lambda r: 64 * PERIODO[r] / float(SAMPLE_RATE),
                        range(1, 32))
        gain = GAIN_LINEAR_DECREASE | r
    else:
        r = _tasa_cerca(suelta * HASTA_DB / 100.0, _hasta_cero, range(1, 32))
        gain = GAIN_EXP_DECREASE | r
    return (0x80 | (dr << 4) | ar, (sl << 5) | sr, gain)


# --- notas ------------------------------------------------------------------

def pitch(note, length=CYCLE):
    """El paso de lectura para que una onda de un ciclo dé esa nota.

    El DSP avanza `pitch/4096` muestras por cada muestra de salida a 32 kHz, así
    que una onda de `length` muestras suena a `32000 * pitch / 4096 / length`.
    Despejando sale la cuenta de abajo.

    El registro tiene 14 bits, o sea que el paso máximo es 4x: con 32 muestras
    por ciclo, unos 4 kHz. Arriba de eso se baja la nota de octava, igual que
    hacía el PSG cuando se le acababa el divisor por abajo.
    """
    while True:
        hertz = 440.0 * 2.0 ** ((note - 69) / 12.0)
        value = int(round(hertz * length * 4096 / SAMPLE_RATE))
        if value <= MAX_PITCH:
            return max(1, value)
        note -= 12


def pitch_for(note, root, rate, length=None):
    """El paso de lectura para tocar una nota con una muestra grabada.

    Con las ondas de un ciclo la cuenta salía del largo del ciclo. Con una
    grabación sale de otro lado: la muestra suena en su afinación original
    cuando el DSP la lee a la misma tasa a la que se grabó, y de ahí se
    transpone por la diferencia de semitonos contra su nota de referencia.

    El registro tiene 14 bits, o sea cuatro veces la tasa base como máximo.
    Guardando a 10 kHz eso da unas dos octavas y media por encima de la nota
    grabada, de sobra; cuando no alcanza se baja una octava, que desafina menos
    que quedarse en el tope.
    """
    while True:
        step = rate * 4096.0 / SAMPLE_RATE * 2.0 ** ((note - root) / 12.0)
        value = int(round(step))
        if value <= MAX_PITCH:
            return max(1, value)
        note -= 12


# El DSP suma las ocho voces y recién después aplica el volumen general, sin
# limitar en el medio: si la suma se pasa, recorta y suena sucio. Con ondas que
# llegan a 0x6000 y hasta media docena de voces a la vez, el techo por voz tiene
# que quedar bastante abajo. Los dos números salen de medir el pico del WAV
# grabado, no de la teoría: la teoría supone que todas las voces pican juntas y
# en fase, que no pasa nunca.
#
# **Y el recorte es antes del volumen general**: la suma de las voces se
# satura a 16 bits y recién después se multiplica por MASTER, así que lo que
# evita el recorte es el techo de cada voz, y MASTER sólo decide a qué nivel
# sale. Con la batería sonando otra vez y los sostenidos del SoundFont
# recortaban 16 de los 22 temas —el de batalla, 309.040 muestras—, así que el
# 2026-09-25 se les dio **aire**: el techo de cada voz AIRE veces el de antes
# (96 y 84) y MASTER otro tanto más alto, hasta donde llega: el registro tiene
# signo y no pasa de $7F.
#
# El prototipo proponía 0,8 con MASTER en $78, que deja el nivel igual, y no
# alcanzó: los 16 seguían recortando, hzbreach 107.218 muestras. Con 0,5
# recortan cinco, a lo sumo 858 muestras (hzbreach), y el nivel baja unos
# 3,6 dB donde antes no recortaba —`escape_newyork` sale a -17,3 LUFS—.
# Para bajar más sin perder nivel hace falta un techo por tema: la tabla y
# lo que costaría están en `workflow/tasks/todo/la-calidad-de-la-musica.md`.
AIRE = 0.5
MASTER = min(0x7F, int(round(0x60 / AIRE)))
CEILING = int(round(96 * AIRE))
CEILING_DRUM = int(round(84 * AIRE))    # la percusión pega fuerte y dura
                                        # poco: aguanta más


def volume(velocity, ceiling=CEILING):
    """El volumen de una voz, de 0 a 127 (el registro tiene signo).

    Se le deja un piso: una nota con velocidad muy baja tiene que oírse, y el
    banco de Windows con el que se compone esto era bastante compresor.
    """
    return max(4, min(ceiling, int(round(velocity / 127.0 * ceiling))))
