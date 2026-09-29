"""Que las ocho voces del DSP se repartan nota a nota, sobre temas de
verdad: `escape_newyork`, el que taro oyó y el que motivó el cambio, y el de
batalla, el que el cambio rompió.

Hasta el 2026-09-26 cada canal del MIDI tenía sus voces fijas, y en este tema
eso eran una voz para los acordes de tres notas de las cuerdas (canal 2) y
ninguna para el clavinet (canal 5) ni la onda cuadrada (canal 7): no sonaban
nunca, y sus programas ni siquiera entraban al banco. Las pruebas del
reparto de `rm2k-snes-audio` miran la regla con notas armadas a mano; ésta,
que el stream que sale del compilador para el tema de verdad tenga lo que la
regla promete.

No corre ninguna ROM: le pide al compilador de música el tema solo, con sus
notas y su reparto, y lee sus escrituras —las mismas que la ROM le manda al
DSP, lo cobra `test_musica_escrituras.py`—.
"""

import collections

import musica

# Cada nota, como la da el compilador: (inicio, fin, canal, tecla, velocidad).
INICIO, FIN, CANAL, TECLA = 0, 1, 2, 3


def _tema():
    temas, banco, _libre = musica.compilar(["escape_newyork"])
    return temas[0], banco


def test_el_acorde_de_las_cuerdas_suena_entero():
    """El primer cuadro en que las cuerdas arrancan tres notas juntas tiene
    que disparar por lo menos tres voces."""
    tema, _banco = _tema()
    arranques = collections.Counter(n[INICIO] for n in tema["notes"]
                                    if n[CANAL] == 2)
    cuadro = min(c for c, cuantas in arranques.items() if cuantas >= 3)
    kon = 0
    for c, registro, valor in tema["writes"]:
        if c == cuadro and registro == musica.constantes()["kon"]:
            kon |= valor
    assert bin(kon).count("1") >= 3, (
        "en el cuadro %d arrancan tres notas de las cuerdas y el KON es $%02X"
        % (cuadro, kon))


BATALLA = "T_VGFighterMAX_Masako"


def test_la_melodia_de_la_batalla_no_pierde_notas():
    """La voz de arriba de los acordes del órgano del tema de batalla —el
    canal 0, el más fuerte de la mezcla por su CC7, y en la referencia lo que
    más se oye de los 15 a los 22 s—: cada nota consigue voz y nadie se la
    roba antes de su fin, en todo el tema.

    Es lo que taro oyó el 2026-09-26 con el reparto del paso 5: "la frase
    principal se interrumpe constantemente". En cada tiempo el tema pega
    cinco o seis golpes a la vez —dos bombos, dos cajas, el charles—, y con
    los dos bajos y los metales tomaban las ocho voces antes de que llegara
    la melodía, que por ser lo más agudo elegía última: no sonaban 214 de sus
    536 notas. El orden de cada cuadro es `frame_order`, en el compilador.

    Con el aire de siempre y no con el techo del tema: es el reparto el que
    se mira, y el de siempre es el que se oyó."""
    temas, _banco, _libre = musica.compilar(
        [BATALLA], aire=musica.constantes()["headroom"])
    notas = temas[0]["notes"]
    arriba = {}
    for entrada in temas[0]["allocation"]:
        nota = notas[entrada[0]]
        if nota[CANAL] == 0 and (nota[INICIO] not in arriba or
                                 nota[TECLA] > notas[arriba[nota[INICIO]][0]][TECLA]):
            arriba[nota[INICIO]] = entrada
    assert len(arriba) > 500, "la melodía tiene %d notas" % len(arriba)
    segundos = musica.constantes()["ticks_per_second"]
    perdidas = ["%.2f s" % (notas[n][INICIO] / segundos)
                for n, voz, robada, fin in sorted(
                    arriba.values(), key=lambda e: notas[e[0]][INICIO])
                if voz is None or (robada is not None and robada < fin)]
    assert not perdidas, "%d notas de la melodía no suenan enteras: %s" % (
        len(perdidas), ", ".join(perdidas[:12]))


def test_el_clavinet_y_la_onda_cuadrada_suenan():
    """Los dos canales que el reparto fijo dejaba sin voz: sus muestras están
    en el banco y alguna voz las toca."""
    tema, banco = _tema()
    srcn = {valor for _c, registro, valor in tema["writes"]
            if registro < 0x80
            and registro & 0x0F == musica.constantes()["v_srcn"]}
    for canal in (5, 7):
        programa = tema["programs"][str(canal)]
        assert programa in banco.melodic, (
            "el programa %d del canal %d no está en el banco" % (programa, canal))
        assert banco.melodic[programa] in srcn, (
            "ninguna voz toca el programa %d del canal %d" % (programa, canal))
