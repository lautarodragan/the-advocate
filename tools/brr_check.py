#!/usr/bin/env python3
"""Mide cuánto pierde el BRR sobre las muestras reales del SoundFont.

Comprimir a cuatro bits por muestra pierde algo por definición; la pregunta es
cuánto, y cuánto de eso recuperan los filtros de predicción. Con las ondas de un
ciclo del banco viejo no había forma de saberlo, porque una onda sintética es
fácil de predecir. Con grabaciones sí.

Se mide dos veces la misma señal: con el filtro 0 solo, que es lo que hacíamos
antes, y con los cuatro. La diferencia es lo que ganaron los filtros.

Uso:
    python3 tools/brr_check.py --programs 0 46 48
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brr
import sf2
import snes_samples


def measure(audio, loop_block, filters):
    """Codifica y devuelve (bytes, error de pico %, error medio %)."""
    padded = list(audio)
    if len(padded) % brr.BLOCK_SAMPLES:
        padded += [0] * (brr.BLOCK_SAMPLES - len(padded) % brr.BLOCK_SAMPLES)

    blocks = len(padded) // brr.BLOCK_SAMPLES
    out, old, older = bytearray(), 0, 0
    for index in range(blocks):
        chunk = padded[index * brr.BLOCK_SAMPLES:(index + 1) * brr.BLOCK_SAMPLES]
        fresh = index == 0 or index == loop_block
        data, old, older, _ = brr.encode_block(
            chunk, old, older,
            loop=index == blocks - 1 and loop_block is not None,
            end=index == blocks - 1,
            filters=(0,) if fresh else filters)
        out += data

    decoded = brr.decode(bytes(out))
    count = min(len(padded), len(decoded))
    peak = max((abs(s) for s in padded[:count]), default=1) or 1
    worst = max(abs(padded[i] - decoded[i]) for i in range(count))
    mean = sum(abs(padded[i] - decoded[i]) for i in range(count)) / count
    return bytes(out), 100.0 * worst / peak, 100.0 * mean / peak


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--programs", type=int, nargs="+", required=True)
    parser.add_argument("--soundfont", default=snes_samples.SOUNDFONT)
    parser.add_argument("--budget", type=int, default=snes_samples.ARAM_BUDGET)
    args = parser.parse_args()

    font = sf2.SoundFont(args.soundfont)
    share = args.budget // max(1, len(args.programs))

    print("%-24s %18s %18s" % ("", "sólo filtro 0", "los cuatro filtros"))
    print("%-24s %8s %9s %8s %9s" % ("instrumento", "pico", "medio",
                                     "pico", "medio"))

    for program in args.programs:
        voice = snes_samples.build_voice(font, program, share)
        if voice is None:
            print("  programa %d: sin preset" % program)
            continue

        audio = brr.decode(voice.data)      # lo que quedó tras remuestrear
        zone, sample = font.zone_for(program, snes_samples.REFERENCE_KEY)
        original = _rebuild(font, zone, sample, voice)

        _, flat_peak, flat_mean = measure(original, voice.loop_block, (0,))
        _, all_peak, all_mean = measure(original, voice.loop_block, brr.FILTERS)
        print("  %-22s %7.1f%% %8.1f%% %7.1f%% %8.1f%%"
              % (voice.name[:22], flat_peak, flat_mean, all_peak, all_mean))


def _rebuild(font, zone, sample, voice):
    """Reconstruye el audio remuestreado que se le dio al codificador."""
    looped = voice.loop_block > 0
    loop_start = sample.loop_start if looped else sample.end
    attack = voice.loop_block * brr.BLOCK_SAMPLES
    loop = voice.frames - attack

    audio = snes_samples.resample(font.pcm(sample.start, loop_start), attack)
    if looped:
        audio += snes_samples.resample(
            font.pcm(sample.loop_start, sample.loop_end), loop)
    return snes_samples.normalize(audio)


if __name__ == "__main__":
    main()
