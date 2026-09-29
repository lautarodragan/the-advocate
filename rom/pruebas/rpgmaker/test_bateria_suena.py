"""Que lo que la música les escribe a las voces 6 y 7 —las de la batería hasta
el 2026-09-26, y desde entonces las que el reparto le da primero— les llegue.

Esas dos voces las comparte la música con los efectos de sonido, así que
`dsp_musica` (rom/src/efectos_de_sonido.s) no manda sus escrituras derecho al
DSP: las guarda primero en la sombra de la voz —`SE_SOMBRA` para la 7,
`SE2_SOMBRA` para la 6—, que es lo que se le devuelve cuando el efecto
termina, y recién después las manda si la voz no tiene efecto. El valor que va
a la sombra y el que va al DSP son **el mismo registro B**, en la misma pasada.

Desde `854dba9` (la voz 7) y `8c9c182` (la 6) ese B se borraba al armar el
índice de la sombra con un `and #$000F` de dieciséis bits: las dos recibían
ceros —volumen, pitch y muestra— y **la batería no sonó en ningún tema**
durante dos semanas. No lo cobró nada porque el silencio no cambia un pixel y
ninguna prueba miraba esas voces. Grabando un stream de sólo batería salía
silencio de principio a fin.

Lo que se mira es la sombra y no el audio: el audio mezcla las ocho voces y
aislar dos pide un cartucho aparte, y la sombra sale de la misma línea que el
valor para el DSP, así que si la sombra tiene lo que la música mandó, el DSP
también. Lo que se le pregunta es que cada byte que aparezca en la sombra sea
uno de los que el stream le escribe a ese registro —leídos del cartucho— y que
el volumen y el pitch de las dos voces lleguen a ser distintos de cero, que es
lo mínimo para que un golpe se oiga.

El tema es el del título, que es el único que se oye sin jugar nada: no hay
efectos de sonido que le saquen las voces, y en las pruebas suena el SPC700 y
no el MSU-1 —ver `test_musica_paquete.py`—.
"""

from consola import EMPEZAR, en_la_wram

# Los registros de una voz del DSP que la música escribe: la parte baja del
# número del registro. ENVX y OUTX (8 y 9) son de lectura y no se escriben.
VOL_L, VOL_R, PITCH_L, PITCH_H = 0, 1, 2, 3
REGISTROS_DE_VOZ = 8
NOMBRE = ["VOL L", "VOL R", "PITCH L", "PITCH H", "SRCN", "ADSR1", "ADSR2",
          "GAIN"]

# Los cuadros de más que se corre después de que el stream escribió lo que
# hace falta, por el título que tarda en arrancar el tema y porque el conteo
# de cuadros de acá y el de la IRQ no tienen por qué coincidir al cuadro.
MARGEN = 120


def test_las_voces_de_la_bateria_reciben_lo_que_la_musica_les_manda(partida):
    una = partida(titulo=EMPEZAR).quedarse_en_el_titulo()
    s = una.simbolos
    tema = s["TEMA_TITULO"]
    assert una.palabra("tema_actual") == tema and not una.byte(
        "music_apagada"), "la pantalla de título no está tocando su tema"

    voces = {7: (s["SE_REG"], s["SE_SOMBRA"]), 6: (s["SE2_REG"], s["SE2_SOMBRA"])}

    # Qué valores le escribe el stream a cada registro de las dos voces, y
    # para qué cuadro ya les escribió volumen y pitch distintos de cero.
    posibles = {v: [{0} for _ in range(REGISTROS_DE_VOZ)] for v in voces}
    faltan = {(v, r) for v in voces for r in (VOL_L, VOL_R, PITCH_L)}
    hasta = None
    for cuadro, registro, valor in una.escrituras_del_tema(tema):
        for voz, (base, _sombra) in voces.items():
            if base <= registro < base + REGISTROS_DE_VOZ:
                posibles[voz][registro - base].add(valor)
                if valor:
                    faltan.discard((voz, registro - base))
        if not faltan and hasta is None:
            hasta = cuadro
    assert hasta is not None, (
        "el tema del título no le escribe volumen y pitch a las dos voces de "
        "la batería (faltan %s), así que el caso no compara nada: buscar "
        "otro tema con percusión" % sorted(faltan))

    # Lo que la sombra tiene antes de que la música le escriba no cuenta: la
    # sombra no se inicializa, así que es lo que la WRAM traía —$55 en snes9x—.
    # Cada byte se empieza a mirar desde que cambia por primera vez.
    antes = {v: una.consola.ram(en_la_wram(sombra), REGISTROS_DE_VOZ)
             for v, (_base, sombra) in voces.items()}
    escrito = {v: [False] * REGISTROS_DE_VOZ for v in voces}
    vistos = {v: [set() for _ in range(REGISTROS_DE_VOZ)] for v in voces}
    for _ in range(hasta + MARGEN):
        una.consola.correr(1)
        for voz, (_base, sombra) in voces.items():
            crudo = una.consola.ram(en_la_wram(sombra), REGISTROS_DE_VOZ)
            for registro, valor in enumerate(crudo):
                escrito[voz][registro] |= valor != antes[voz][registro]
                if escrito[voz][registro]:
                    vistos[voz][registro].add(valor)

    for voz in voces:
        for registro in range(REGISTROS_DE_VOZ):
            ajenos = vistos[voz][registro] - posibles[voz][registro]
            assert not ajenos, (
                "la sombra de la voz %d tuvo en %s los valores %s, que el "
                "stream nunca le escribe: el valor se ensucia en el camino"
                % (voz, NOMBRE[registro], sorted(ajenos)))
        for registro in (VOL_L, VOL_R, PITCH_L):
            assert vistos[voz][registro] - {0}, (
                "la voz %d de la batería tuvo %s en cero durante %d cuadros "
                "del título, y el stream le escribe %s desde el cuadro %d: "
                "`dsp_musica` le está mandando ceros en vez de lo que la "
                "música le escribe, o sea que la batería no suena"
                % (voz, NOMBRE[registro], hasta + MARGEN,
                   sorted(posibles[voz][registro] - {0}), hasta))
