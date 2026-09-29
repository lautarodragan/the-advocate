"""Los efectos de sonido de calidad, que la ROM lee del `.msu` con MSU-1.

Con MSU-1 y el tema sonando por su pista, el SPC700 no toca música: la ARAM
queda para los efectos. Pero la ROM no puede llevar una versión de calidad
de cada efecto para cada paquete —medido el 2026-09-26, los 92 efectos de
`release` enteros a 22 kHz eran 1,1 MB, y el paquete del mapa 3 solo pedía
291 KB contra los 62 de la ARAM—, así que las lleva el `.msu`, que no tiene
tope, y la ROM las sube a la ARAM por el puerto de datos del MSU-1 al cargar
cada paquete. Sin MSU-1, o con un `.msu` que no es el de este cartucho, usa
los suyos: los de siempre, que reparte `snes_music`. El mecanismo es el de
los fondos de batalla —ver docs/port/msu-datos.md— y el diseño con sus
números, la tarea `efectos-de-calidad-con-msu-1.md`.

**Cada paquete tiene su versión de cada efecto**, a la tasa que le entra.
Una sola por efecto —la que le entra a su peor paquete— dejaba a 4,7 kHz los
efectos que el mapa 3 comparte con otros diez paquetes que tienen lugar de
sobra: el mismo día, 48 de los 159 pares (paquete, efecto) de `release`
perdían. Lo que cuesta es que la ROM vuelve a subir los efectos en cada
paquete aunque ya estuvieran en la ARAM, porque no tiene dónde anotar qué
versión quedó: ver `se_msu_preparar` en tools/runtime/efectos_con_msu.s.

**Enteros siempre, y a la tasa más alta que entre**: la misma para todos los
efectos del paquete —`TASAS`, de la de los WAV para abajo— salvo que la del
cartucho sea mayor. Un efecto que el cartucho ya lleva entero no queda peor
que sin MSU-1: su tasa es el piso. Uno que el cartucho lleva recortado puede
quedar a menos tasa que allá, pero entero: es lo que pidió taro primero, la
longitud.
"""

import collections

from audio import muestras_brr
from audio import snes_music
from audio import snes_samples

# Las tasas entre las que se elige, de mayor a menor. 22.050 Hz es la de los
# WAV del RTP, así que no se remuestrea; una fija para todos los efectos de un
# paquete, y escalonada para que la misma versión sirva a más de un paquete
# —el caché del BRR la codifica una vez—.
TASAS = (22050, 20000, 18000, 16000, 14000, 12000, 11025, 10000, 9000, 8000,
         7500, 7000, 6500, 6000, 5500, 5000, 4500, 4000, 3500, 3000)
# Lo que se deja libre en cada paquete, como la música: `ARAM_MARGEN`.
MARGEN = snes_music.ARAM_MARGEN


# `rate` y no `tasa`: así la lee `snes_music.altura_de_efecto`, igual que a
# un `Efecto`.
Version = collections.namedtuple("Version", "nombre rate data")


def armar(nombre, tasa, game_dir):
    """El efecto entero, sin bucle, a `tasa` —o a la de su WAV, si es menor—,
    en BRR. Es lo que hace `snes_music.build_efecto` con un efecto de
    `se_enteros()`, y la normalización es la misma: suena igual de fuerte que el
    de la ROM."""
    crudo, fuente = snes_music.leer_wav(nombre.split("@")[0], game_dir)
    tasa = min(tasa, fuente)
    salen = max(muestras_brr.BLOQUE_MUESTRAS,
                int(round(len(crudo) * tasa / float(fuente)))
                // muestras_brr.BLOQUE_MUESTRAS * muestras_brr.BLOQUE_MUESTRAS)
    audio = snes_samples.normalize(snes_samples.resample(crudo, salen))
    return Version(nombre, tasa, muestras_brr.codificar(audio))


def _pesa(largo, fuente, tasa):
    """Lo que ocupa en BRR un efecto de `largo` muestras a `fuente` Hz,
    entero a `tasa`: la misma cuenta que `armar`, sin armarlo."""
    tasa = min(tasa, fuente)
    salen = max(16, int(round(largo * tasa / float(fuente))) // 16 * 16)
    return salen // 16 * muestras_brr.BLOQUE_BYTES


def tasas(paquetes, efectos, libre, game_dir):
    """{nombre del paquete: {efecto: tasa}}: a qué tasa va cada efecto de cada
    paquete en el `.msu`.

    `paquetes` son (nombre, efectos, bytes de la música que sí se sube con
    MSU-1): la de los temas del paquete que no tienen pista. `efectos` es
    `banco.efectos` —{nombre: (SRCN, Efecto)}—, de donde sale el piso de cada
    uno: la tasa del cartucho si allá va entero. `libre` es lo que hay en la
    ARAM para muestras.
    """
    wavs = {}
    salida = {}
    for nombre, suyos, musica in paquetes:
        suyos = [e for e in dict.fromkeys(suyos) if e in efectos]
        if not suyos:
            continue
        for e in suyos:
            if e not in wavs:
                crudo, fuente = snes_music.leer_wav(e.split("@")[0], game_dir)
                wavs[e] = (len(crudo), fuente)
        piso = {e: 0 if efectos[e][1].repite else efectos[e][1].rate
                for e in suyos}
        hay = libre - MARGEN - musica
        elegida = {}
        for tasa in TASAS:
            elegida = {e: max(tasa, piso[e]) for e in suyos}
            if sum(_pesa(*wavs[e], elegida[e]) for e in suyos) <= hay:
                break
        else:
            print("  efectos de calidad: el paquete %s no entra ni a %d Hz; "
                  "los que no entren no suenan con MSU-1" % (nombre, TASAS[-1]))
        salida[nombre] = elegida
    return salida
