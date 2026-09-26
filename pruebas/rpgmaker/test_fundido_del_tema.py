"""Que un `FadeOutBGM` baje el tema y nada más: los efectos de sonido que
caen durante el fundido y después suenan enteros. Y que salir de la pantalla
de título a un mapa callado tampoco los calle.

En RM2k el fundido es del tema (`Game_System::BgmFade`), y un `PlaySound`
que venga detrás suena igual. Hasta el 2026-09-26 la ROM, sin MSU-1, bajaba
el volumen general del DSP —que los efectos también oyen— y lo dejaba en
cero hasta el próximo tema: el trueno del final del mapa 3 salía mudo. La
pantalla de título hacía lo mismo para callar su tema al empezar la partida.

El caso `efecto-tras-el-fundido` corre, como todos, después de pasar el
título. Toca `Switch1` antes de que suene ningún tema; después prende
`evilrhys` en el mapa 3, lo funde en dos segundos, toca `Switch1` cuando al
fundido le quedan dieciocho cuadros —el volumen, en 15%— y otra vez cuando ya
terminó. Se escucha el audio del core: el primero y el tercero tienen que
sonar, y el segundo, en los cuadros en que el fundido sigue andando, tan
fuerte como el tercero en los mismos cuadros de su vida. Con el volumen
general en cero el primero y el tercero daban cero muestras, y el segundo,
fundido, a lo sumo un 15%.

Qué cuadros son de cada efecto lo dice la ROM, no un número copiado: una voz
de efecto está ocupada mientras `SE_CUADROS` —o su pendiente— no es cero.
"""

from array import array

from consola import en_la_wram

# Por debajo de esto un pico es ruido de redondeo, no un efecto que suena.
AUDIBLE = 1000

# Cuánto del pico del efecto de después tiene que tener el de durante. La
# música, que sigue al 15% y bajando, suma o resta un poco; el volumen general
# fundido lo dejaba en menos de 0,15.
PROPORCION = 0.6


def _ocupadas(una):
    s = una.simbolos
    ocupada = 0
    for base in ("SE_CUADROS", "SE2_CUADROS"):
        cuadros = una.consola.ram(en_la_wram(s[base]), 3)
        ocupada |= cuadros[0] | cuadros[1] | cuadros[2]   # y el pendiente
    return bool(ocupada)


def _pico(audio):
    muestras = array("h", bytes(audio))
    return max((abs(m) for m in muestras), default=0)


def test_los_efectos_suenan_durante_y_despues_del_fundido(partida):
    una = partida(caso="efecto-tras-el-fundido")
    # Por tick: el tramo de audio que produjo, si había efecto, y el estado
    # del fundido al empezarlo.
    ticks = []
    for _ in range(900):
        antes = len(una.consola.audio)
        fundiendo = una.byte("bgm_fundido")
        callado = una.byte("music_apagada")
        una.correr(1)
        ticks.append((antes, len(una.consola.audio), _ocupadas(una),
                      fundiendo, callado))
        if not ticks[-1][2] and len(list(_tramos(ticks))) == 3:
            break

    efectos = list(_tramos(ticks))
    assert len(efectos) == 3, (
        "el caso tenía que tocar tres efectos y se vieron %d: cambió el caso "
        "o el efecto dura otra cosa" % len(efectos))
    antes, durante, despues = efectos
    assert antes[0][4] and not antes[0][3], (
        "el primer efecto no cayó con la música callada: el caso no mide la "
        "salida del título")
    fundido = [t for t in durante if t[3]]
    assert len(fundido) >= 5, (
        "el segundo efecto no cayó adentro del fundido (%d cuadros): el caso "
        "no mide lo que dice" % len(fundido))
    assert despues[0][4] and not despues[0][3], (
        "el tercer efecto arrancó con el fundido sin terminar: el caso no "
        "mide el después")

    audio = una.consola.audio
    pico_antes = _pico(audio[antes[0][0]:antes[-1][1]])
    assert pico_antes >= AUDIBLE, (
        "el efecto de antes del primer tema picó %d: al salir de la pantalla "
        "de título a un mapa callado, los efectos quedaron mudos" % pico_antes)
    pico_despues = _pico(audio[despues[0][0]:despues[-1][1]])
    assert pico_despues >= AUDIBLE, (
        "el efecto de después del fundido picó %d: con el tema ya fundido, "
        "los efectos quedaron mudos" % pico_despues)

    n = len(fundido)
    pico_durante = _pico(audio[durante[0][0]:durante[n - 1][1]])
    mismo_tramo = _pico(audio[despues[0][0]:despues[min(n, len(despues)) - 1][1]])
    assert pico_durante >= PROPORCION * mismo_tramo, (
        "en sus primeros %d cuadros, con el fundido andando, el efecto picó "
        "%d, y el mismo efecto sin fundido %d: el fundido está bajando los "
        "efectos y no sólo el tema" % (n, pico_durante, mismo_tramo))


def _tramos(ticks):
    """Las corridas de ticks seguidos con alguna voz de efecto ocupada."""
    actual = []
    for tick in ticks:
        if tick[2]:
            actual.append(tick)
        elif actual:
            yield actual
            actual = []
    if actual:
        yield actual
