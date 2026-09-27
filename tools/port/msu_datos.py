"""Lo que el cartucho guarda en el `.msu`: el puerto de datos del MSU-1.

El `.msu` es el archivo que enciende el MSU-1, y hasta el 2026-09-25 iba vacío.
El MSU-1 lo expone como un flujo: la ROM escribe una posición de 32 bits en
$2000..$2003 —la escritura a $2003 es la que busca—, espera a que se apague el
bit 7 de $2000 y lee de $2001 byte por byte, avanzando solo; por DMA con el
origen fijo en $2001 se lee a la velocidad de cualquier DMA. El mecanismo de
este lado y del de la ROM está en docs/port/msu-datos.md.

Lo que lleva primero son **los fondos de batalla de calidad**, 8bpp y 96
colores, y **todos los del juego**, estén o no en los mapas del cartucho: ver
"Qué fondos hay" en tools/port/escena.py. **Sin MSU-1 el juego tiene que
andar igual** —Mednafen no lo tiene—, así que la ROM lleva un respaldo
liviano, 4bpp y 16 colores, de los pocos que entran, y uno de reemplazo para
los demás; el `.msu` los reemplaza cuando está y es el de este cartucho. Son
distintos a propósito: ver "El respaldo liviano" en tools/port/escena.py.

## El formato

Todo en little-endian:

    $00     8  la firma: los primeros 8 bytes del sha256 de todo lo que
               sigue
    $08     4  "ABLD"
    $0C     2  la versión del formato, hoy 2
    $0E     2  cuántas entradas hay, N
    $10     8N por entrada: dónde empieza en el archivo y cuánto mide, 4 y 4
    ...        ceros, hasta FONDOS_DESDE
    $10000     los fondos, uno cada FONDO_LUGAR bytes y en orden de número:
               el fondo k en `fondo_en(k)`
    ...        detrás del último, las demás entradas, una detrás de la otra
               y en el orden del índice

**La región de los fondos es fija.** Hasta la versión 1 las entradas iban
todas seguidas detrás del índice, así que el lugar de un fondo dependía de
cuántas entradas hubiera —y los efectos son de cada cartucho— y de qué fondos
llevara el cartucho. Desde el 2026-09-27 el `.msu` lleva todos los fondos del
juego, cada uno con su número, y el fondo k está en el mismo byte en el
`.msu` de cualquier cartucho: `FONDOS_DESDE + k * FONDO_LUGAR` sus tiles, y
`COLORES_EN` más adelante sus colores. El índice sigue estando, y dice lo
mismo, para las herramientas. Si el índice llegara a pasar de
`FONDOS_DESDE` —más de ocho mil entradas— `armar` se niega.

Cada lugar mide 32.768 bytes de tiles, 192 de colores y relleno hasta el
próximo múltiplo de 512: así los tiles de cada fondo empiezan en un sector de
la tarjeta SD, que es de donde los lee el FX Pak. No está medido que eso lo
haga más rápido; cuesta 320 bytes por fondo.

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
snes_convert.py, y la ROM sabe dónde está cada uno por `msu_fondo_pos`, que
emite `escribir_msu`.

Detrás de los fondos van los efectos de sonido de calidad, una entrada por
efecto de cada paquete de audio, en BRR: los ordena `escribir_msu` en
snes_convert.py, y el porqué está en tools/audio/efectos_msu.py.
"""

import hashlib
import struct

MAGIA = b"ABLD"
VERSION = 2
FIRMA = 8
CABECERA = 16
ENTRADA = 8

# La región de los fondos: ver "El formato".
FONDOS_DESDE = 0x10000
COLORES_EN = 0x8000                 # 512 tiles de 8bpp
FONDO_LUGAR = 0x8200                # y los 192 bytes de colores, al sector
SECTOR = 512
assert FONDO_LUGAR % SECTOR == 0 and FONDO_LUGAR >= COLORES_EN + 96 * 2


def fondo_en(k):
    """Dónde están los tiles del fondo número `k`; sus colores, `COLORES_EN`
    más adelante."""
    return FONDOS_DESDE + k * FONDO_LUGAR


def armar(entradas, fondos=0):
    """El `.msu` con estas entradas, y dónde quedó cada una.

    `entradas` son los bytes de cada una, en orden. Las primeras `2 *
    fondos` son los fondos —tiles y colores de cada uno— y van en su lugar
    fijo, `fondo_en`; las demás detrás de la región de los fondos, una tras
    otra. Sin fondos, todas seguidas detrás del índice. Devuelve `(archivo,
    posiciones)`, con `posiciones[k]` el desplazamiento de la entrada `k`
    desde el principio del archivo.
    """
    posiciones = []
    donde = CABECERA + ENTRADA * len(entradas)
    if fondos:
        if donde > FONDOS_DESDE:
            raise ValueError("el índice del .msu mide %d B y pisa la región de "
                             "los fondos, en $%X" % (donde, FONDOS_DESDE))
        for k in range(fondos):
            tiles, colores = entradas[2 * k], entradas[2 * k + 1]
            if len(tiles) > COLORES_EN or \
                    COLORES_EN + len(colores) > FONDO_LUGAR:
                raise ValueError("el fondo %d no entra en su lugar del .msu"
                                 % k)
            posiciones += [fondo_en(k), fondo_en(k) + COLORES_EN]
        # Lo que sigue va detrás de la región entera, no del último byte
        # escrito: así tampoco depende de cuánto mida el último fondo.
        donde = fondo_en(fondos)
    for datos in entradas[2 * fondos:]:
        posiciones.append(donde)
        donde += len(datos)
    indice = b"".join(struct.pack("<II", p, len(d))
                      for p, d in zip(posiciones, entradas))
    cuerpo = bytearray(MAGIA + struct.pack("<HH", VERSION, len(entradas))
                       + indice)
    for p, datos in zip(posiciones, entradas):
        # Relleno con ceros hasta donde va: la firma lo cubre como a todo.
        cuerpo += bytes(p - FIRMA - len(cuerpo))
        cuerpo += datos
    cuerpo = bytes(cuerpo)
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
