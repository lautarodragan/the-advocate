"""El chip de sonido de la Super Nintendo: banco de muestras y registros.

El S-DSP no sintetiza nada por su cuenta: reproduce muestras. Ocho voces, cada
una leyendo una muestra de la memoria del SPC700 a la velocidad que se le pida,
con envolvente ADSR y volumen por canal. La altura de la nota sale de la
velocidad de lectura, así que una sola muestra sirve para todas las notas.

Eso cambia por completo el problema respecto del YM2612. Allá el timbre había
que construirlo con cuatro operadores y nueve parámetros cada uno, a ciegas.
Acá el timbre es la muestra, y las muestras salen de un SoundFont de General
MIDI: las arma snes_samples.py.

Lo que queda acá de aquel banco sintético son las envolventes. `for_program`
sigue devolviendo una familia por programa de General MIDI, y de ella se usan
sólo el ataque, el decaimiento y el sostenido, que el DSP aplica encima de la
muestra. Las ondas de `waveform` ya no van a la ROM; se dejan porque siguen
sirviendo para generar un tono de prueba de frecuencia conocida.
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

# El release del ADSR del DSP no se puede configurar: al escribir KOF la
# envolvente cae a cero en unos 8 ms, que se oye como un corte seco. Por eso
# soltar una nota no se hace con KOF sino apagando el bit de ADSR —con lo que
# manda GAIN— y pidiéndole una caída exponencial, cuya velocidad sí se elige.
# La envolvente sigue desde donde estaba, así que la nota se apaga en vez de
# cortarse.
GAIN_EXP_DECREASE = 0xA0        # bit 7: modo propio; bits 5-6: exponencial

# Los globales viven en las columnas $x C y $x D.
MVOL_L, MVOL_R = 0x0C, 0x1C
EVOL_L, EVOL_R = 0x2C, 0x3C
KON, KOF = 0x4C, 0x5C
FLG = 0x6C
PMON, NON, EON = 0x2D, 0x3D, 0x4D
DIR = 0x5D

FLG_BASE = 0x20         # eco apagado; los cinco bits bajos son el ruido


def voice_register(voice, register):
    return voice * 0x10 + register


# --- el banco ---------------------------------------------------------------

def instrument(name, harmonics, attack, decay, sustain, release, fade):
    """Un timbre: los pesos de sus armónicos más la envolvente.

    `harmonics[0]` es el fundamental. La envolvente va en las unidades del DSP:
    ataque y decaimiento son 0-15 y 0-7 (más alto = más rápido), el sostenido
    0-7 es a qué nivel se queda, y `release` 0-31 cuánto sigue cayendo mientras
    la nota se mantiene apretada (0 = se queda para siempre).

    `fade` es otra cosa y es la que importa acá: la velocidad de GAIN con la que
    la nota se apaga al soltarla. Decide si el instrumento resuena o corta. En
    la tabla del DSP los números chicos son lentos — unos 320 ms en 12, unos
    130 ms en 16— y se eligen de oído, como el resto del banco.
    """
    return {"name": name, "harmonics": harmonics, "attack": attack,
            "decay": decay, "sustain": sustain, "release": release,
            "fade": fade}


# Con 32 muestras por ciclo, del armónico 16 para arriba ya no queda nada que
# muestrear: se replegaría sobre los graves. Por eso ninguno pasa de 12.
PIANO = instrument("piano", [1.0, .60, .35, .20, .12, .08, .05], 15, 5, 3, 16, 11)
BASS = instrument("bajo", [1.0, .35, .12, .05], 15, 4, 4, 14, 14)
# Órgano de barras: armónicos impares y nada en los pares.
ORGAN = instrument("órgano", [1.0, 0, .50, 0, .30, 0, .20], 14, 0, 7, 0, 17)
# Diente de sierra: todos los armónicos cayendo como 1/n. Es el punto de
# partida de casi cualquier instrumento de cuerda frotada.
STRINGS = instrument("cuerdas", [1.0 / n for n in range(1, 11)], 10, 2, 6, 4, 12)
BRASS = instrument("metales", [.70, 1.0, .90, .70, .50, .35, .25, .15], 12, 3, 6, 6, 15)
# Onda cuadrada: impares cayendo como 1/n.
REED = instrument("caña", [1.0, 0, .33, 0, .20, 0, .14, 0, .11], 13, 3, 6, 5, 15)
LEAD = instrument("solista", [1.0, 0, .33, 0, .20, 0, .14, 0, .11, 0, .09], 15, 4, 6, 8, 14)
# Campana: los parciales no son múltiplos enteros del fundamental, y con una
# onda periódica eso no se puede hacer del todo. Se aproxima salteando.
BELL = instrument("campana", [1.0, 0, 0, .70, 0, 0, .45, 0, 0, .30], 15, 7, 2, 20, 9)

# Las 16 familias de General MIDI, de a 8 programas cada una. Mismo reparto que
# el banco del YM2612, para poder comparar las dos consolas con lo mismo.
BANK = [
    PIANO,      # 0-7     piano
    BELL,       # 8-15    percusión cromática
    ORGAN,      # 16-23   órgano
    LEAD,       # 24-31   guitarra
    BASS,       # 32-39   bajo
    STRINGS,    # 40-47   cuerdas
    STRINGS,    # 48-55   conjunto
    BRASS,      # 56-63   metales
    REED,       # 64-71   caña
    REED,       # 72-79   viento
    LEAD,       # 80-87   sintetizador solista
    STRINGS,    # 88-95   sintetizador de fondo
    BELL,       # 96-103  efectos
    BELL,       # 104-111 étnico
    BELL,       # 112-119 percusión
    LEAD,       # 120-127 efectos de sonido
]


def for_program(program):
    """El timbre que le toca a un instrumento de General MIDI."""
    return BANK[min(15, max(0, program) // 8)]


def waveform(harmonics, length=CYCLE, peak=0x6000):
    """Un ciclo de onda a partir de los pesos de sus armónicos.

    Se normaliza al pico pedido en vez de a la suma de los pesos: así todas las
    ondas del banco salen con la misma amplitud y el volumen queda decidido por
    la velocidad de la nota, no por cuántos armónicos tenga el timbre.
    """
    raw = []
    for i in range(length):
        value = sum(weight * math.sin(2 * math.pi * (n + 1) * i / length)
                    for n, weight in enumerate(harmonics) if weight)
        raw.append(value)

    top = max(abs(v) for v in raw) or 1.0
    return [int(round(v / top * peak)) for v in raw]


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


def adsr(sound):
    """Los dos registros de envolvente de un timbre."""
    return (0x80 | ((sound["decay"] & 0x07) << 4) | (sound["attack"] & 0x0F),
            ((sound["sustain"] & 0x07) << 5) | (sound["release"] & 0x1F))


def fade(sound):
    """Con qué valor de GAIN se apaga la nota al soltarla."""
    return GAIN_EXP_DECREASE | (sound["fade"] & 0x1F)


# El DSP suma las ocho voces y recién después aplica el volumen general, sin
# limitar en el medio: si la suma se pasa, recorta y suena sucio. Con ondas que
# llegan a 0x6000 y hasta media docena de voces a la vez, el techo por voz tiene
# que quedar bastante abajo. Los dos números salen de medir el pico del WAV
# grabado, no de la teoría: la teoría supone que todas las voces pican juntas y
# en fase, que no pasa nunca.
MASTER = 0x60
CEILING = 96
CEILING_DRUM = 84       # la percusión pega fuerte y dura poco: aguanta más


def volume(velocity, ceiling=CEILING):
    """El volumen de una voz, de 0 a 127 (el registro tiene signo).

    Se le deja un piso: una nota con velocidad muy baja tiene que oírse, y el
    banco de Windows con el que se compone esto era bastante compresor.
    """
    return max(4, min(ceiling, int(round(velocity / 127.0 * ceiling))))
