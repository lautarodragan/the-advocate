"""El descompresor de referencia del LC_LZ2, contra el que se prueba todo lo
demás: el compresor de `tools/snes/lz2/` y `lz2_decompress` de la ROM.

Escrito aparte a propósito, desde el formato y no desde el binario: si los dos
lados salieran del mismo código, un error en la lectura del formato daría cero
diferencias en la ida y vuelta. Es lo que mordió dos veces con la referencia
de Python del render —ver "La regla que sostiene todo" en AGENTS.md—.

El formato, en una línea por comando: un encabezado `CCCLLLLL` (largo L+1, de
1 a 32) o `111CCCLL LLLLLLLL` (de 1 a 1024), y
    0  literal      los L+1 bytes que siguen
    1  relleno      un byte, repetido
    2  palabra      dos bytes, alternados, cortados en el largo
    3  creciente    un byte, y cada uno el anterior más uno
    4  repetición   dos bytes de dirección **big-endian**, absoluta en la
                    salida: se copia desde ahí, de a un byte, hacia adelante
y `$FF` al final.
"""


def descomprimir(flujo, desde=0):
    """(los bytes, dónde termina el flujo): el índice del byte después del
    `$FF`, que es donde empieza el siguiente si hay otro pegado."""
    salida = bytearray()
    i = desde
    while True:
        encabezado = flujo[i]
        i += 1
        if encabezado == 0xFF:
            return bytes(salida), i
        if encabezado >> 5 == 7:
            comando = (encabezado >> 2) & 7
            largo = ((encabezado & 3) << 8 | flujo[i]) + 1
            i += 1
        else:
            comando = encabezado >> 5
            largo = (encabezado & 31) + 1
        if comando == 0:
            salida += flujo[i:i + largo]
            assert len(flujo[i:i + largo]) == largo, "el literal se corta"
            i += largo
        elif comando == 1:
            salida += bytes([flujo[i]]) * largo
            i += 1
        elif comando == 2:
            par = flujo[i:i + 2]
            salida += bytes(par[k % 2] for k in range(largo))
            i += 2
        elif comando == 3:
            salida += bytes((flujo[i] + k) & 0xFF for k in range(largo))
            i += 1
        elif comando == 4:
            origen = flujo[i] << 8 | flujo[i + 1]
            i += 2
            assert origen < len(salida), (
                "una repetición desde %d con la salida en %d" % (origen, len(salida)))
            for k in range(largo):
                salida.append(salida[origen + k])
        else:
            raise AssertionError("no hay comando %d, en el byte %d" % (comando, i - 1))
        assert len(salida) <= 0x10000, "la salida pasa de 64 KB"
