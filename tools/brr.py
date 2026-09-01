"""Codificador BRR, el formato de muestras comprimidas de la Super Nintendo.

Una muestra BRR son bloques de 9 bytes: uno de cabecera y ocho de datos, que
guardan 16 muestras a 4 bits cada una. La cabecera trae un rango —cuántos bits
se corre cada valor al descomprimir— y un filtro, que predice cada muestra a
partir de las anteriores.

Acá se usa siempre el filtro 0, que no predice nada. Con formas de onda de un
ciclo, que es lo que genera el banco, los filtros con predicción no ganan casi
nada y complican la reproducción exacta.
"""

BLOCK_SAMPLES = 16
BLOCK_BYTES = 9

FLAG_END = 0x01
FLAG_LOOP = 0x02


def encode_block(samples, loop=False, end=False):
    """Un bloque de 16 muestras de 16 bits con signo.

    El rango es cuánto hay que correr los nibbles a la izquierda; se elige el
    más chico que entre, que es el que menos resolución pierde.
    """
    peak = max((abs(s) for s in samples), default=0)
    for shift in range(13):
        # Un nibble con signo va de -8 a 7, y al descomprimir se corre `shift`.
        if peak >> shift <= 7:
            break

    header = (shift << 4) | (FLAG_LOOP if loop else 0) | (FLAG_END if end else 0)
    data = bytearray([header])
    for i in range(0, BLOCK_SAMPLES, 2):
        nibbles = []
        for sample in samples[i:i + 2]:
            value = max(-8, min(7, round(sample / (1 << shift))))
            nibbles.append(value & 0x0F)
        data.append((nibbles[0] << 4) | nibbles[1])
    return bytes(data)


def encode(samples, loop_block=0):
    """Una muestra entera, con el punto de loop en el bloque que se le diga.

    El largo se completa con ceros hasta un múltiplo de 16, porque el DSP sólo
    entiende bloques enteros.
    """
    padded = list(samples)
    if len(padded) % BLOCK_SAMPLES:
        padded += [0] * (BLOCK_SAMPLES - len(padded) % BLOCK_SAMPLES)

    blocks = len(padded) // BLOCK_SAMPLES
    out = bytearray()
    for index in range(blocks):
        chunk = padded[index * BLOCK_SAMPLES:(index + 1) * BLOCK_SAMPLES]
        last = index == blocks - 1
        out += encode_block(chunk, loop=last and loop_block is not None, end=last)
    return bytes(out)


def decode(data):
    """Descomprime, para poder verificar sin ejecutar nada."""
    samples = []
    for index in range(0, len(data), BLOCK_BYTES):
        header = data[index]
        shift = header >> 4
        for byte in data[index + 1:index + BLOCK_BYTES]:
            for nibble in ((byte >> 4) & 0x0F, byte & 0x0F):
                value = nibble - 16 if nibble >= 8 else nibble
                samples.append(value << shift)
    return samples
