"""Codificador BRR, el formato de muestras comprimidas de la Super Nintendo.

Una muestra BRR son bloques de nueve bytes: uno de cabecera y ocho de datos, que
guardan 16 muestras a cuatro bits cada una. La cabecera trae un rango —cuántos
bits se corre cada valor al descomprimir— y un filtro.

El filtro es lo que hace que 4 bits alcancen. En vez de guardar la muestra,
guarda la diferencia contra lo que predice a partir de las dos anteriores; en
audio real esa diferencia es mucho más chica que la señal, así que entra en
menos bits. Los cuatro filtros son:

    0   sin predicción
    1   old·15/16                       una pendiente
    2   old·61/32 − older·15/16         una parábola
    3   old·115/64 − older·13/16        idem, más agresiva

Con las ondas de un ciclo del banco viejo daba casi igual cuál se usara. Con
grabaciones de verdad la diferencia es grande, así que se prueban los cuatro
por cada bloque y se elige el que menos error deja.

Dos bloques van siempre con el filtro 0, y no es una simplificación: los
filtros 1 a 3 se apoyan en las dos muestras anteriores, y ni al arrancar ni al
volver del loop se sabe con certeza cuáles son. Forzar el 0 ahí cuesta un poco
de precisión en 16 muestras y evita un chasquido en cada vuelta.
"""

BLOCK_SAMPLES = 16
BLOCK_BYTES = 9
MAX_SHIFT = 12

FLAG_END = 0x01
FLAG_LOOP = 0x02

FILTERS = (0, 1, 2, 3)


def predict(filter_id, old, older):
    """Lo que el decodificador espera que valga la próxima muestra.

    Las cuentas son con enteros y corrimientos, tal como las hace el chip: si
    acá se usaran fracciones exactas, el codificador estaría optimizando contra
    un decodificador que no existe y el error real sería otro.
    """
    if filter_id == 0:
        return 0
    if filter_id == 1:
        return old + ((-old) >> 4)
    if filter_id == 2:
        return (old << 1) + ((-((old << 1) + old)) >> 5) - older + (older >> 4)
    return (old << 1) + ((-(old * 13)) >> 6) - older + ((older * 3) >> 4)


def _clamp16(value):
    return max(-32768, min(32767, value))


def _try(samples, filter_id, shift, old, older):
    """Codifica un bloque con un filtro y un rango dados.

    La predicción de cada muestra usa las que el decodificador ya reconstruyó,
    no las originales. Por eso hay que simularlo muestra por muestra: si se
    usaran las originales, el error se acumularía sin que el codificador lo vea.
    """
    nibbles, error = [], 0
    for target in samples:
        guess = predict(filter_id, old, older)
        residual = target - guess
        nibble = max(-8, min(7, (residual + (1 << shift) // 2) >> shift
                             if residual >= 0 else
                             -((-residual + (1 << shift) // 2) >> shift)))
        decoded = _clamp16(guess + (nibble << shift))
        error += (target - decoded) ** 2
        older, old = old, decoded
        nibbles.append(nibble & 0x0F)
    return nibbles, error, old, older


def encode_block(samples, old=0, older=0, loop=False, end=False,
                 filters=FILTERS):
    """El mejor de los 4x13 pares (filtro, rango) para estas 16 muestras."""
    best = None
    for filter_id in filters:
        for shift in range(MAX_SHIFT + 1):
            nibbles, error, new_old, new_older = _try(samples, filter_id,
                                                      shift, old, older)
            if best is None or error < best[0]:
                best = (error, filter_id, shift, nibbles, new_old, new_older)
            if error == 0:
                break

    error, filter_id, shift, nibbles, new_old, new_older = best
    header = (shift << 4) | (filter_id << 2) | (FLAG_LOOP if loop else 0) \
        | (FLAG_END if end else 0)

    data = bytearray([header])
    for i in range(0, BLOCK_SAMPLES, 2):
        data.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(data), new_old, new_older, error


# Lo ya codificado en esta corrida, por (muestras, loop). Está acá y no en
# quien llama porque la repetición es de acá abajo: cada tema arma su banco de
# tambores desde cero y vuelve a pedir las mismas muestras. Medido el
# 2026-09-10 sobre `demo-ciudad`, ocho mapas: 1611 llamadas a `encode` para 111
# entradas distintas, 44 s de los 77 del build. La salida es una función pura
# de la entrada, así que devolver lo mismo es exactamente lo mismo; se
# comprobó comparando el `.sfc` byte por byte con y sin esto.
_hechas = {}


def encode(samples, loop_block=None):
    """Una muestra entera, con el punto de loop en el bloque que se le diga.

    `loop_block` es el índice del bloque al que vuelve, o None si no se repite.
    El largo se completa con ceros hasta un múltiplo de 16, porque el DSP sólo
    entiende bloques enteros.
    """
    clave = (tuple(samples), loop_block)
    hecha = _hechas.get(clave)
    if hecha is None:
        hecha = _hechas[clave] = _encode(samples, loop_block)
    return hecha


def _encode(samples, loop_block):
    padded = list(samples)
    if len(padded) % BLOCK_SAMPLES:
        padded += [0] * (BLOCK_SAMPLES - len(padded) % BLOCK_SAMPLES)

    blocks = len(padded) // BLOCK_SAMPLES
    out, old, older, total = bytearray(), 0, 0, 0

    for index in range(blocks):
        chunk = padded[index * BLOCK_SAMPLES:(index + 1) * BLOCK_SAMPLES]
        last = index == blocks - 1
        # Sin estado previo confiable, el filtro 0 es el único honesto.
        fresh = index == 0 or index == loop_block
        data, old, older, error = encode_block(
            chunk, old, older,
            loop=last and loop_block is not None, end=last,
            filters=(0,) if fresh else FILTERS)
        out += data
        total += error
    return bytes(out)


def decode(data):
    """Descomprime, para poder verificar sin ejecutar nada.

    Tiene que reproducir exactamente lo que hace el chip, filtros incluidos: es
    el patrón contra el que se compara lo que sale del emulador.
    """
    samples, old, older = [], 0, 0
    for index in range(0, len(data) - BLOCK_BYTES + 1, BLOCK_BYTES):
        header = data[index]
        shift = header >> 4
        filter_id = (header >> 2) & 0x03

        for byte in data[index + 1:index + BLOCK_BYTES]:
            for nibble in ((byte >> 4) & 0x0F, byte & 0x0F):
                value = nibble - 16 if nibble >= 8 else nibble
                decoded = _clamp16(predict(filter_id, old, older)
                                   + (value << shift))
                samples.append(decoded)
                older, old = old, decoded
    return samples


def error(original, data):
    """Cuánto se perdió, en porcentaje de la amplitud de la señal."""
    decoded = decode(data)
    count = min(len(original), len(decoded))
    if not count:
        return 0.0
    peak = max((abs(s) for s in original[:count]), default=1) or 1
    worst = max(abs(original[i] - decoded[i]) for i in range(count))
    return 100.0 * worst / peak
