#!/usr/bin/env python3
"""Mide qué frecuencia tiene un WAV, para verificar que suena lo que se pidió.

No hace falta escuchar: si se pidió un La de 440 y la señal grabada tiene su
período en 440 Hz, la cadena entera —carga al SPC700, muestra en BRR, registros
del DSP— funcionó.

La medición es por autocorrelación, que para un tono sostenido es suficiente y
no necesita ninguna biblioteca.
"""

import struct
import sys
import wave


def read(path):
    with wave.open(path, "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())

    if width != 2:
        sys.exit("esperaba 16 bits por muestra, no %d" % (width * 8))
    values = struct.unpack("<%dh" % (len(frames) // 2), frames)
    return rate, list(values[::channels])   # un solo canal alcanza


def fundamental(samples, rate, low=50, high=4000):
    """La frecuencia del período que mejor se correlaciona consigo mismo."""
    best, best_score = 0, 0.0
    energy = sum(s * s for s in samples)
    if not energy:
        return 0.0

    for lag in range(rate // high, rate // low):
        score = sum(samples[i] * samples[i + lag]
                    for i in range(0, len(samples) - lag, 3))
        if score > best_score:
            best_score, best = score, lag
    return rate / best if best else 0.0


def main():
    path = sys.argv[1]
    expected = float(sys.argv[2]) if len(sys.argv) > 2 else None

    rate, samples = read(path)
    peak = max(abs(s) for s in samples) if samples else 0
    print("%s: %.1f s a %d Hz, pico %d de 32767" %
          (path, len(samples) / rate, rate, peak))

    if peak < 200:
        print("SILENCIO: no salió sonido.")
        return 1

    # Se mide en el medio, ya pasado el arranque.
    middle = samples[len(samples) // 3:len(samples) // 3 + rate // 2]
    hertz = fundamental(middle, rate)
    print("frecuencia medida: %.1f Hz" % hertz)

    if expected:
        cents = 1200 * (hertz / expected).bit_length() if False else (
            1200 * __import__("math").log2(hertz / expected) if hertz else 0)
        print("esperada: %.1f Hz, diferencia %.0f cents" % (expected, cents))
        if abs(cents) < 50:
            print("COINCIDE")
            return 0
        print("NO COINCIDE")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
