"""Que las ocho voces del DSP se repartan nota a nota, sobre temas de
verdad: `escape_newyork`, el que taro oyó y el que motivó el cambio, y el de
batalla, el que el cambio rompió.

Hasta el 2026-09-26 cada canal del MIDI tenía sus voces fijas, y en este tema
eso eran una voz para los acordes de tres notas de las cuerdas (canal 2) y
ninguna para el clavinet (canal 5) ni la onda cuadrada (canal 7): no sonaban
nunca, y sus programas ni siquiera entraban al banco. Las pruebas de
`pruebas/herramientas/test_musica_stream.py` miran la regla con notas armadas
a mano; ésta, que el stream que sale del conversor para el tema de verdad
tenga lo que la regla promete.

No corre ninguna ROM: arma el tema con `build_varios`, solo, y lee sus
escrituras —las mismas que la ROM le manda al DSP, lo cobra
`test_musica_escrituras.py`—.
"""

import collections


def _tema():
    from audio import snes_music
    _d, _v, temas, banco = snes_music.build_varios(["escape_newyork"])
    return snes_music.leer_tema("escape_newyork"), temas[0], banco


def test_el_acorde_de_las_cuerdas_suena_entero():
    """El primer cuadro en que las cuerdas arrancan tres notas juntas tiene
    que disparar por lo menos tres voces."""
    from audio import sdsp
    leido, tema, _banco = _tema()
    arranques = collections.Counter(n.start for n in leido["notas"]
                                    if n.channel == 2)
    cuadro = min(c for c, cuantas in arranques.items() if cuantas >= 3)
    kon = 0
    for c, registro, valor in tema["escrituras"]:
        if c == cuadro and registro == sdsp.KON:
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
    536 notas. El orden de cada cuadro es `_orden_del_cuadro`."""
    from audio import snes_music
    _d, _v, _temas, banco = snes_music.build_varios([BATALLA])
    leido = snes_music.leer_tema(BATALLA)
    reparto = []
    snes_music.build_events(leido["notas"], leido["voces"],
                            leido["programas"], banco, leido["controles"],
                            reparto)
    arriba = {}
    for entrada in reparto:
        nota = entrada[0]
        if nota.channel == 0 and (nota.start not in arriba or
                                  nota.pitch > arriba[nota.start][0].pitch):
            arriba[nota.start] = entrada
    assert len(arriba) > 500, "la melodía tiene %d notas" % len(arriba)
    segundos = snes_music.TICKS_PER_SECOND
    perdidas = ["%.2f s" % (n.start / segundos)
                for n, voz, robada, fin in sorted(arriba.values(),
                                                  key=lambda e: e[0].start)
                if voz is None or (robada is not None and robada < fin)]
    assert not perdidas, "%d notas de la melodía no suenan enteras: %s" % (
        len(perdidas), ", ".join(perdidas[:12]))


def test_el_clavinet_y_la_onda_cuadrada_suenan():
    """Los dos canales que el reparto fijo dejaba sin voz: sus muestras están
    en el banco y alguna voz las toca."""
    from audio import sdsp
    leido, tema, banco = _tema()
    srcn = {valor for _c, registro, valor in tema["escrituras"]
            if registro < 0x80 and registro & 0x0F == sdsp.V_SRCN}
    for canal in (5, 7):
        programa = leido["programas"][canal]
        assert programa in banco.melodicas, (
            "el programa %d del canal %d no está en el banco" % (programa, canal))
        assert banco.melodicas[programa] in srcn, (
            "ninguna voz toca el programa %d del canal %d" % (programa, canal))
