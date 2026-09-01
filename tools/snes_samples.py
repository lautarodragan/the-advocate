#!/usr/bin/env python3
"""Arma el banco de muestras de la SNES a partir del SoundFont.

Reemplaza las ondas de un ciclo de sdsp.py por grabaciones reales. El problema
deja de ser inventar un timbre y pasa a ser uno de presupuesto: el SPC700 tiene
64 KB para todo, y una sola muestra de piano de FluidR3 son 17 KB antes de
comprimir.

La palanca es la tasa de muestreo. El DSP remuestrea igual para cambiar la
altura de la nota, así que guardar a 8 o 12 kHz no cuesta nada extra en tiempo
de ejecución: sólo cuesta agudos. Es exactamente lo que hacían los juegos de la
consola, y por eso suenan como suenan.

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

Uso:
    python3 tools/snes_samples.py --map-id 67
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brr
import sf2

SOUNDFONT = "/usr/share/soundfonts/FluidR3_GM.sf2"
BLOCK = brr.BLOCK_SAMPLES          # 16 muestras por bloque de BRR
REFERENCE_KEY = 60                 # do central: con qué nota se elige la zona
PEAK = 0x6800                      # a cuánto se normaliza cada muestra

# El SPC700 tiene 64 KB y no todo es nuestro: el driver, el directorio de
# muestras y el buffer de eco viven ahí también. 56 KB para el banco deja aire
# de sobra y todavía es cuarenta veces lo que usábamos con las ondas sintéticas.
ARAM_BUDGET = 56 * 1024

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
    allowed = budget * BLOCK / float(brr.BLOCK_BYTES)     # muestras que entran
    rate = source_rate * allowed / frames
    return int(max(MIN_RATE, min(MAX_RATE, min(rate, source_rate))))


def build_voice(font, program, budget, key=REFERENCE_KEY):
    """Extrae un instrumento del SoundFont y lo deja en BRR.

    El ajuste fino está en que el loop caiga justo en un bloque. Se elige
    primero cuántas muestras va a tener el loop —un múltiplo de 16— y de ahí
    sale la tasa real, que puede diferir un poco de la pedida. Después el
    ataque se lleva al múltiplo de 16 más cercano con esa misma tasa.
    """
    zone, sample = font.zone_for(program, key)
    if sample is None:
        return None

    modes = zone.get(sf2.GEN_SAMPLE_MODES, sf2.LOOP_NONE)
    looped = modes in (sf2.LOOP_CONTINUOUS, sf2.LOOP_UNTIL_RELEASE)

    start, end = sample.start, sample.end
    loop_start = sample.loop_start if looped else end
    loop_end = sample.loop_end if looped else end
    if not looped or loop_end <= loop_start:
        looped = False
        loop_start = loop_end = end

    attack_frames = loop_start - start
    loop_frames = loop_end - loop_start
    rate = plan_rate(attack_frames, loop_frames, sample.rate, budget)
    ratio = rate / float(sample.rate)

    if looped:
        # El loop primero: su largo tiene que ser múltiplo de 16, y de ese
        # redondeo sale la tasa que realmente vamos a declarar.
        loop_out = max(BLOCK, int(round(loop_frames * ratio / BLOCK)) * BLOCK)
        ratio = loop_out / float(loop_frames)
        rate = int(round(sample.rate * ratio))
    else:
        loop_out = 0

    attack_out = int(round(attack_frames * ratio / BLOCK)) * BLOCK

    audio = resample(font.pcm(start, loop_start), attack_out)
    if looped:
        audio += resample(font.pcm(loop_start, loop_end), loop_out)
    audio = normalize(audio)

    root = zone.get(sf2.GEN_ROOT_KEY)
    if root is None or root > 127:
        root = sample.root_key
    # El SoundFont corrige la afinación en cents por tres lados distintos.
    cents = (sample.correction + zone.get(sf2.GEN_FINE_TUNE, 0)
             + 100 * zone.get(sf2.GEN_COARSE_TUNE, 0))

    data = brr.encode(audio, loop_block=attack_out // BLOCK if looped else None)
    return Voice(program, sample.name, data, rate * 2.0 ** (-cents / 1200.0),
                 root, attack_out // BLOCK if looped else 0, len(audio))


def build_bank(programs, budget=ARAM_BUDGET, soundfont=SOUNDFONT,
               key=REFERENCE_KEY):
    """Un banco con todos los instrumentos pedidos, repartiendo el presupuesto.

    Se reparte en partes iguales. Podría ponderarse por cuánto suena cada uno,
    pero el que más suena no es el que más resolución necesita: un bajo aguanta
    4 kHz sin que se note y un arpa no.
    """
    font = sf2.SoundFont(soundfont)
    share = budget // max(1, len(programs))

    voices = []
    for program in programs:
        voice = build_voice(font, program, share, key)
        if voice is not None:
            voices.append(voice)
    return voices


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--programs", type=int, nargs="+", required=True)
    parser.add_argument("--soundfont", default=SOUNDFONT)
    parser.add_argument("--budget", type=int, default=ARAM_BUDGET)
    args = parser.parse_args()

    voices = build_bank(args.programs, args.budget, args.soundfont)
    total = sum(len(v.data) for v in voices)

    print("Banco de %d instrumentos, %d bytes de %d (%.0f%% de los 64 KB)"
          % (len(voices), total, args.budget, 100.0 * total / 65536))
    for voice in voices:
        print("  programa %3d %-22s %6d B  %5.0f Hz  nota %3d  loop en bloque %d"
              % (voice.program, voice.name[:22], len(voice.data), voice.rate,
                 voice.root, voice.loop_block))


if __name__ == "__main__":
    main()
