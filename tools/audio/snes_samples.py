"""Arma el banco de muestras de la SNES a partir del SoundFont.

Reemplaza las ondas de un ciclo de sdsp.py por grabaciones reales. El problema
deja de ser inventar un timbre y pasa a ser uno de presupuesto: el SPC700 tiene
64 KB para todo.

La palanca es la tasa de muestreo. El DSP remuestrea igual para cambiar la
altura de la nota, así que guardar a 8 o 12 kHz no cuesta nada extra en tiempo
de ejecución: sólo cuesta agudos. Es exactamente lo que hacían los juegos de la
consola, y por eso suenan como suenan.

Con el banco de Windows, sin embargo, la palanca casi no se usa: sus muestras ya
vienen a 22 kHz y son cortas, así que el banco entero entra sin remuestrear
nada. Eso importa porque acá se remuestrea sin filtrar antes, y bajar la tasa
así mete replegado. La regla es no tocar la tasa mientras haya lugar.

Tres restricciones mandan en el resultado:

  * **El loop tiene que caer en un bloque de BRR.** El DSP vuelve al principio
    de un bloque de nueve bytes, o sea cada 16 muestras. Si el punto de loop
    queda a mitad de bloque, no se puede expresar; hay que ajustar el
    remuestreo para que caiga justo, no redondear y esperar.
  * **El loop no se acorta.** FluidR3 elige loops largos (casi un segundo en el
    piano) porque adentro hay batido entre cuerdas. Cortarlo más corto mete una
    periodicidad audible, así que cuando falta lugar se baja la tasa, no el
    largo.
  * **Los ataques no se tocan.** Es lo que distingue un piano de un órgano, y
    dura poco: recortarlo ahorra poco y cuesta mucho.
"""

import hashlib
import math
import os

from audio import muestras_brr
from comun import cache_disco

# El sintetizador por software de Windows, que es con el que se compuso y se
# escuchó este juego. Microsoft le licenció a Roland un subconjunto reducido del
# Sound Canvas, así que no es un SC-55: es exactamente esto y nada más.
#
# Que sea reducido nos viene bien por dos lados. Sus muestras son diez veces más
# cortas que las de FluidR3 y ya vienen a 22 kHz, así que el banco entero entra
# en ARAM sin remuestrear nada — y remuestrear era, por lejos, lo que más
# calidad costaba. Y de paso dejamos de aproximarnos a un banco parecido para
# muestrear del que produjo el sonido original.
SOUNDFONT = os.environ.get(
    "ABL_SOUNDFONT",
    "/extras/soundfonts/Microsoft GS Wavetable Synth.sf2")
BLOCK = muestras_brr.BLOQUE_MUESTRAS   # 16 muestras por bloque de BRR
REFERENCE_KEY = 60                 # do central: con qué nota se elige la zona
PEAK = 0x6800                      # a cuánto se normaliza cada muestra

# El SPC700 tiene 64 KB y no todo es nuestro: el driver, el directorio de
# muestras y el buffer de eco viven ahí también. El reparto entre melódicos y
# percusión deja 8 KB de aire.
ARAM_BUDGET = 40 * 1024
DRUM_BUDGET = 16 * 1024

# La percusión de General MIDI vive en el banco 128, y ahí cada tecla es un
# instrumento distinto en vez de una altura distinta. Eso es del formato, así
# que quien lo sabe es `gunter sf2`: acá se pide `drum:36` y nada más.
DRUM_SECONDS = 0.5

MIN_RATE = 4000
MAX_RATE = 24000


class Voice:
    """Un instrumento ya listo para el SPC700."""

    def __init__(self, program, name, data, rate, root, loop_block, frames):
        self.program = program
        self.name = name
        self.data = data                # BRR
        self.rate = rate                # a la que quedó guardada
        self.root = root                # qué nota suena a esa tasa
        self.loop_block = loop_block    # en qué bloque vuelve
        self.frames = frames

    def __repr__(self):
        return "<Voz %d %r %d B a %d Hz>" % (self.program, self.name,
                                             len(self.data), self.rate)


# --- el caché de la muestra preparada ---------------------------------------
#
# Lo que se guarda acá es **la voz entera**: el remuestreo, la normalización y
# el BRR que sale de ellos. `muestras_brr.codificar` ya cacheaba lo último, y
# ése nunca fue el problema — la preparación en Python que va antes sí. Medido
# con `cProfile` sobre una conversión de `abl` **con el caché
# caliente**: de 165 s de perfil, 114,6 eran audio, y de ésos 108,9 los ponía
# `build_drum_bank`, que en una conversión se llama 790 veces.
#
# **Se cachea el golpe y no el banco** —`build_drum(golpe, presupuesto)` y no
# `build_drum_bank(golpes, presupuesto)`— y ésa es la decisión. El banco tiene
# menos claves, pero su clave lleva *qué golpes* pide el cartucho, así que dos
# cartuchos con listas de temas distintas no comparten ni una entrada. El golpe
# suelto sí: la clave es una nota y un presupuesto, y ésos se repiten entre las
# 790 vueltas, entre los cinco cartuchos de prueba y la demo.

_version = None
_huellas = {}
_tambores = {}
_voces = {}


def _version_de_la_preparacion():
    """Qué versión del código produjo la voz que hay guardada.

    Va este archivo —el remuestreo, la normalización y el reparto de
    presupuesto viven acá— y, por `muestras_brr.version()`, el puente y **el
    binario instalado**. Lo que decide la clave es lo que produjo los bytes, y
    los bytes pasan por los tres.
    """
    global _version
    if _version is None:
        _version = cache_disco.clave(muestras_brr.version(),
                                     cache_disco.version_de(
                                         "audio/snes_samples.py"))
    return _version


def huella_del_soundfont(ruta):
    """El contenido del SoundFont, no su ruta.

    `ABL_SOUNDFONT` puede apuntar a otro banco, y un banco puede cambiar sin
    cambiar de nombre: la clave tiene que caducar con cualquiera de las dos.
    Se lee una vez por proceso porque el archivo pesa megas.

    Es pública porque `msu.py` renderiza con **el mismo soundfont** y su clave
    necesita la misma huella, por la misma razón.
    """
    if ruta not in _huellas:
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
        _huellas[ruta] = h.hexdigest()
    return _huellas[ruta]


def _cacheada(memoria, clave, partes, hacer):
    """Una voz, de la memoria del proceso, del disco o recién hecha.

    Lo guardado va adentro de una tupla de uno porque **`None` es un resultado
    legítimo** —no hay tal golpe en el banco, o lo que entra en el presupuesto
    no llega ni a un bloque— y `cache_disco.leer` devuelve `None` cuando no hay
    nada. Sin el envoltorio, un "no existe" ya calculado se volvería a calcular
    en cada corrida.
    """
    if clave in memoria:
        return memoria[clave]
    en_disco = cache_disco.clave(_version_de_la_preparacion(), *partes)
    guardado = cache_disco.leer("muestras", en_disco)
    if guardado is None:
        guardado = (hacer(),)
        cache_disco.guardar("muestras", en_disco, guardado)
    memoria[clave] = guardado[0]
    return guardado[0]


def resample(samples, count):
    """Cambia el largo de una señal por interpolación lineal.

    Para bajar la tasa lo correcto sería filtrar antes, si no los agudos se
    repliegan sobre los graves. Acá no se hace: en instrumentos de tono estos
    parciales son débiles, y el error del BRR es bastante mayor que el del
    replegado. Si alguna vez suena áspero en los agudos, éste es el lugar.
    """
    if count <= 0 or not samples:
        return []
    if count == len(samples):
        return list(samples)

    step = (len(samples) - 1) / float(count)
    out = []
    for i in range(count):
        position = i * step
        index = int(position)
        fraction = position - index
        first = samples[index]
        second = samples[min(index + 1, len(samples) - 1)]
        out.append(int(round(first + (second - first) * fraction)))
    return out


def normalize(samples, peak=PEAK):
    """Lleva la muestra a una amplitud conocida.

    Así el volumen lo decide la velocidad de la nota y no cuán fuerte grabaron
    ese instrumento, que entre presets de FluidR3 varía bastante.
    """
    top = max((abs(s) for s in samples), default=0)
    if not top:
        return list(samples)
    scale = peak / float(top)
    return [int(round(s * scale)) for s in samples]


def plan_rate(attack_frames, loop_frames, source_rate, budget):
    """A qué tasa hay que guardar para entrar en el presupuesto.

    Devuelve la tasa más alta que cumple, acotada por MIN_RATE y MAX_RATE. El
    presupuesto está en bytes de BRR, que son nueve por cada 16 muestras.
    """
    frames = attack_frames + loop_frames
    if not frames:
        return MIN_RATE
    # Cuantas muestras entran en el presupuesto.
    allowed = budget * BLOCK / float(muestras_brr.BLOQUE_BYTES)
    rate = source_rate * allowed / frames
    return int(max(MIN_RATE, min(MAX_RATE, min(rate, source_rate))))


def build_voice(soundfont, program, budget, key=REFERENCE_KEY):
    """Un instrumento del SoundFont en BRR, cacheado. Ver `_cacheada`."""
    return _cacheada(_voces, (soundfont, program, budget, key),
                     (huella_del_soundfont(soundfont), "program",
                      str(program), str(budget), str(key)),
                     lambda: _build_voice(soundfont, program, budget, key))


def _build_voice(soundfont, program, budget, key):
    """Extrae un instrumento del SoundFont y lo deja en BRR.

    El ajuste fino está en que el loop caiga justo en un bloque. Se elige
    primero cuántas muestras va a tener el loop —un múltiplo de 16— y de ahí
    sale la tasa real, que puede diferir un poco de la pedida. Después el
    ataque se lleva al múltiplo de 16 más cercano con esa misma tasa.
    """
    sample = muestras_brr.extraer("program:%d@%d" % (program, key), soundfont)
    if sample is None:
        return None

    # Qué zona cubre la nota, si el loop vale y de dónde sale la nota raíz son
    # decisiones del formato, y las toma `gunter sf2`: acá el loop ya viene en
    # cuadros y relativo al PCM extraído, y `loop` ya dice que no cuando la
    # zona no repite o cuando el loop está vacío.
    looped = sample.loop
    attack_frames = sample.loop_start if looped else sample.cuadros
    loop_frames = sample.loop_end - sample.loop_start if looped else 0

    rate = plan_rate(attack_frames, loop_frames, sample.tasa, budget)
    ratio = rate / float(sample.tasa)

    if looped:
        # El loop primero: su largo tiene que ser múltiplo de 16, y de ese
        # redondeo sale la tasa que realmente vamos a declarar.
        loop_out = max(BLOCK, int(round(loop_frames * ratio / BLOCK)) * BLOCK)
        ratio = loop_out / float(loop_frames)
        rate = int(round(sample.tasa * ratio))
    else:
        loop_out = 0

    attack_out = int(round(attack_frames * ratio / BLOCK)) * BLOCK

    audio = resample(sample.pcm[:attack_frames], attack_out)
    if looped:
        audio += resample(sample.pcm[sample.loop_start:sample.loop_end],
                          loop_out)
    audio = normalize(audio)

    data = muestras_brr.codificar(
        audio, loop_block=attack_out // BLOCK if looped else None)
    return Voice(program, sample.nombre, data,
                 rate * 2.0 ** (-sample.cents / 1200.0), sample.nota,
                 attack_out // BLOCK if looped else 0, len(audio))


def build_drum(soundfont, note, budget, seconds=DRUM_SECONDS):
    """Un golpe de percusión en BRR, cacheado. Ver `_cacheada`."""
    return _cacheada(_tambores, (soundfont, note, budget, seconds),
                     (huella_del_soundfont(soundfont), "drum", str(note),
                      str(budget), repr(seconds)),
                     lambda: _build_drum(soundfont, note, budget, seconds))


def _build_drum(soundfont, note, budget, seconds):
    """Un golpe de percusión del kit estándar.

    En General MIDI la percusión vive en el banco 128 y cada tecla es un
    instrumento distinto: el 36 es el bombo, el 42 el charles. No se transpone
    nada, así que la muestra se guarda para sonar a su tasa original.

    Se recorta, y bastante: el plato ride de FluidR3 dura 2,6 segundos y el
    charles cerrado 0,7, casi todo cola que se apaga. Guardarla entera costaría
    más que todos los instrumentos melódicos juntos. Se corta y el resto lo hace
    la envolvente del DSP, que es justamente para lo que sirve.
    """
    sample = muestras_brr.extraer("drum:%d" % note, soundfont)
    if sample is None:
        return None

    frames = min(sample.cuadros, int(seconds * sample.tasa))
    rate = plan_rate(frames, 0, sample.tasa, budget)
    out = int(round(frames * rate / float(sample.tasa)) / BLOCK) * BLOCK
    if out < BLOCK:
        return None

    audio = normalize(resample(sample.pcm[:frames], out))
    data = muestras_brr.codificar(audio, loop_block=None)
    return Voice(note, sample.nombre, data, rate, sample.nota, 0, out)


def brightness(samples, rate):
    """Dónde está el centro de gravedad del espectro, en Hz.

    Es la cuenta clásica del centroide espectral, hecha en el dominio del
    tiempo: la energía de las diferencias entre muestras consecutivas contra la
    energía de la señal da cuánto pesa lo agudo, sin necesidad de una FFT.

    Sirve para repartir el presupuesto entre golpes de percusión. Repartir por
    cuántas veces suena cada uno es exactamente el criterio equivocado: el
    bombo suena cien veces y no tiene un solo agudo, y el plato suena dieciséis
    y es todo agudo. Medir el brillo pone la resolución donde hace falta.
    """
    energy = sum(s * s for s in samples)
    if not energy:
        return rate / 4.0
    diff = sum((samples[i] - samples[i - 1]) ** 2
               for i in range(1, len(samples)))
    return rate / (2.0 * math.pi) * math.sqrt(diff / energy)


_pedidos = {}


def _pedido_del_golpe(soundfont, note):
    """Qué tasa justifica el brillo de un golpe, y cuánto dura. O None.

    **No depende del presupuesto**, y ahí está la gracia de tenerlo aparte:
    `build_drum_bank` se llama cientos de veces con el mismo juego de golpes y
    otro presupuesto, y el centroide de cada uno da lo mismo todas las veces.
    Recorrerlo de nuevo costaba 48 de los 165 s del perfil.

    Alcanza con la memoria del proceso y no va al disco: adentro de una
    conversión esto son unas decenas de golpes, y el que las paga una sola vez
    ya no las vuelve a ver.
    """
    clave = (soundfont, note)
    if clave not in _pedidos:
        sample = muestras_brr.extraer("drum:%d" % note, soundfont)
        if sample is None:
            _pedidos[clave] = None
        else:
            frames = min(sample.cuadros, int(DRUM_SECONDS * sample.tasa))
            audio = sample.pcm[:min(frames, 8192)]
            rate = 2.4 * brightness(audio, sample.tasa)
            _pedidos[clave] = (max(MIN_RATE, min(MAX_RATE, rate)), frames,
                               sample.tasa)
    return _pedidos[clave]


def build_drum_bank(notes, budget=DRUM_BUDGET, soundfont=SOUNDFONT):
    """Un golpe por cada nota de percusión que el MIDI use.

    A cada uno se le pide la tasa que su brillo justifica —un poco más del
    doble del centroide, que deja lugar para lo que hay por encima— y recién si
    la suma no entra se bajan todas en la misma proporción.
    """
    wanted = {}
    for note in notes:
        pedido = _pedido_del_golpe(soundfont, note)
        if pedido is not None:
            wanted[note] = pedido

    # Lo que costaría darle a cada uno lo que pide, en bytes de BRR.
    def cost(rate, frames, source_rate):
        return (frames * (rate / source_rate)
                * muestras_brr.BLOQUE_BYTES / BLOCK)

    # Primero la pregunta simple: ¿entran todos a su tasa original? Bajar la
    # tasa sin filtrar antes mete replegado, así que si hay lugar no se toca
    # nada. Con el banco de Windows, que ya viene a 22 kHz, la respuesta suele
    # ser que sí.
    native = sum(cost(r, f, r) for _, f, r in wanted.values())
    if native <= budget:
        scale = None
    else:
        # Y si no entran, el brillo decide quién cede: el bombo no tiene un
        # solo agudo y el plato es todo agudo.
        scale = budget / (sum(cost(*wanted[n]) for n in wanted) or 1)

    drums = []
    for note in sorted(wanted):
        rate, frames, source_rate = wanted[note]
        share = (cost(source_rate, frames, source_rate) if scale is None
                 else cost(rate * scale, frames, source_rate))
        drum = build_drum(soundfont, note, max(512, int(share)))
        if drum is not None:
            drums.append(drum)
    return drums


# Cuánto de su parte tiene que haber gastado un instrumento para que se lo
# considere "con hambre" y entre en el reparto de lo que sobró. No es 100%
# porque el largo real se redondea a bloques de 16 muestras y casi nunca cae
# justo.
PARTE_LLENA = 0.95
VUELTAS_DE_REPARTO = 3


def build_bank(programs, budget=ARAM_BUDGET, soundfont=SOUNDFONT,
               key=REFERENCE_KEY):
    """Un banco con todos los instrumentos pedidos, repartiendo el presupuesto.

    Se reparte en partes iguales. Podría ponderarse por cuánto suena cada uno,
    pero el que más suena no es el que más resolución necesita: un bajo aguanta
    4 kHz sin que se note y un arpa no.

    **Y lo que sobra se vuelve a repartir**, que es lo que hace que varios temas
    puedan compartir un banco sin sonar peor. Un instrumento corto, o uno que
    topa en MAX_RATE, no gasta su parte: con cinco programas sobraban 10 de los
    40 KB. Repartir ese sobrante entre los que sí la gastaron es la diferencia
    entre que el piano de `escape_newyork` baje a 12,6 kHz al meter cuatro temas
    y que se quede en 21. Dos o tres vueltas alcanzan para converger; después no
    queda nadie con hambre.
    """
    parte = budget // max(1, len(programs))
    reparto = {program: parte for program in programs}
    hechas = {}

    for _ in range(max(1, VUELTAS_DE_REPARTO)):
        for program in programs:
            if program not in hechas:
                hechas[program] = build_voice(soundfont, program,
                                              reparto[program], key)
        voices = [hechas[p] for p in programs if hechas[p] is not None]
        sobra = budget - sum(len(v.data) for v in voices)
        hambrientos = [v.program for v in voices
                       if len(v.data) >= reparto[v.program] * PARTE_LLENA]
        if sobra <= 0 or not hambrientos:
            break
        for program in hambrientos:
            reparto[program] += sobra // len(hambrientos)
            del hechas[program]         # sólo se rearman los que cambiaron
    return voices
