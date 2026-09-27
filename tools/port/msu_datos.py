"""Lo que el cartucho guarda en el `.msu`: el puerto de datos del MSU-1.

El `.msu` es el archivo que enciende el MSU-1, y hasta el 2026-09-25 iba vacío.
El MSU-1 lo expone como un flujo: la ROM escribe una posición de 32 bits en
$2000..$2003 —la escritura a $2003 es la que busca—, espera a que se apague el
bit 7 de $2000 y lee de $2001 byte por byte, avanzando solo; por DMA con el
origen fijo en $2001 se lee a la velocidad de cualquier DMA. El mecanismo de
este lado y del de la ROM está en docs/port/msu-datos.md.

Es un piloto, y lo que lleva son **los fondos de batalla de calidad**: 8bpp y
96 colores. **Sin MSU-1 el juego tiene que andar igual** —Mednafen no lo
tiene—, así que la ROM lleva de cada uno un respaldo liviano, 4bpp y 16
colores, y el `.msu` lo reemplaza cuando está y es el de este cartucho. Son
distintos a propósito: ver "El respaldo liviano" en tools/port/escena.py.

## El formato

Todo en little-endian:

    $00  8  la firma: los primeros 8 bytes del sha256 de todo lo que sigue
    $08  4  "ABLD"
    $0C  2  la versión del formato, hoy 1
    $0E  2  cuántas entradas hay, N
    $10  8N por entrada: dónde empieza en el archivo y cuánto mide, 4 y 4
    ...     los datos de las entradas, uno detrás del otro y en el orden del
            índice

**La firma es del contenido, no del build.** La ROM lleva la que espera —el
conversor la emite en el `.inc`— y la compara con los 8 primeros bytes del
`.msu` antes de leer nada: si no coinciden —un `.msu` de otro build, uno
vacío, uno cortado— usa la ROM. Que sea del contenido y no del commit quiere
decir que un `.msu` de otro build **con los mismos datos** se acepta, y eso
está bien: lo que se protege es que los bytes sean los que la ROM espera, y
cubrir el índice con el hash cubre también dónde está cada cosa.

**Las posiciones las lee la ROM de su `.inc`, no del índice.** Una vez
aceptada la firma, el índice del archivo y las constantes del `.inc` son el
mismo dato por construcción —salen de `armar`—, y leerlo en la consola sería
una búsqueda más por pelea para no aprender nada. El índice está para las
herramientas de este lado (`leer`) y para que sumar otra cosa después sea
sumar entradas, sin cambiar el formato.

Cada fondo son dos entradas, en este orden: sus 512 tiles de 8bpp —32.768
bytes, tal cual van a la WRAM— y sus 96 colores de 15 bits —192 bytes, tal
cual van a la CGRAM desde la entrada 32—. Los arma `fondo_bytes` en
snes_convert.py.

Detrás de los fondos van los efectos de sonido de calidad, una entrada por
efecto de cada paquete de audio, en BRR: los ordena `escribir_msu` en
snes_convert.py, y el porqué está en tools/audio/efectos_msu.py.
"""

import hashlib
import struct

MAGIA = b"ABLD"
VERSION = 1
FIRMA = 8
CABECERA = 16
ENTRADA = 8


def armar(entradas):
    """El `.msu` con estas entradas, y dónde quedó cada una.

    `entradas` son los bytes de cada una, en orden. Devuelve `(archivo,
    posiciones)`, con `posiciones[k]` el desplazamiento de la entrada `k`
    desde el principio del archivo.
    """
    posiciones = []
    donde = CABECERA + ENTRADA * len(entradas)
    indice = bytearray()
    for datos in entradas:
        posiciones.append(donde)
        indice += struct.pack("<II", donde, len(datos))
        donde += len(datos)
    cuerpo = (MAGIA + struct.pack("<HH", VERSION, len(entradas)) + indice
              + b"".join(entradas))
    return firma_de(cuerpo) + cuerpo, posiciones


def firma_de(cuerpo):
    """Los 8 bytes que van al principio: del sha256 de lo que sigue."""
    return hashlib.sha256(cuerpo).digest()[:FIRMA]


def indice(archivo):
    """El índice de un `.msu`: `(donde, largo)` por entrada, o `ValueError` si
    no es uno válido."""
    if len(archivo) < CABECERA or archivo[FIRMA:FIRMA + 4] != MAGIA:
        raise ValueError("no es un .msu con datos de este port")
    if firma_de(archivo[FIRMA:]) != archivo[:FIRMA]:
        raise ValueError("la firma no coincide con el contenido")
    version, n = struct.unpack_from("<HH", archivo, FIRMA + 4)
    if version != VERSION:
        raise ValueError("versión %d, y esto lee la %d" % (version, VERSION))
    return [struct.unpack_from("<II", archivo, CABECERA + ENTRADA * k)
            for k in range(n)]


def leer(archivo):
    """Las entradas de un `.msu`, o `ValueError` si no es uno válido."""
    return [archivo[donde:donde + largo] for donde, largo in indice(archivo)]


def fondos(tiles_y_colores):
    """El `.msu` de los fondos de batalla: por fondo, sus tiles y sus colores.

    Devuelve `(archivo, firma, posiciones)`, con `posiciones[k]` el par
    `(tiles, colores)` del fondo `k`: es lo que la ROM lee de `msu_fondo_pos`.
    """
    entradas = [parte for par in tiles_y_colores for parte in par]
    archivo, donde = armar(entradas)
    return (archivo, archivo[:FIRMA],
            [(donde[2 * k], donde[2 * k + 1])
             for k in range(len(tiles_y_colores))])
