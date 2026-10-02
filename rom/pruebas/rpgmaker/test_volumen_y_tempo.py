"""Que un `PlayBGM` toque el tema al volumen y al tempo que pide.

De los `PlayBGM` del juego, muchos piden un volumen distinto de 100 y unos
pocos otro tempo —`nightbg` a 80 en el bosque de noche, `Kfmus5` a 110—, y
hasta el 2026-09-30 la ROM tocaba todos al 100. Lo que hace RM2k lo dice
`Game_System::BgmPlay` de easyrpg, y lo que hace la ROM con eso,
`bgm_level` en el compilador de eventos: el volumen escala el CC7 de cada
canal —que el stream ya trae al cuadrado, así que 50 es un cuarto de la
amplitud— y el tempo apura o frena el stream sin cambiar la altura, que es
lo que hace con un MIDI.

Sin MSU-1 no cambia un pixel ni hay audio que comparar contra nada, así que
se mira lo que la ROM le pide al DSP: la bitácora de `dsp_music`, `MUS_LOG`,
la misma de `test_musica_escrituras.py`. El volumen es el último valor de
cada `VOL` contra lo que el stream quería escribir —`MUS_SHADOW`—; el tempo,
cuántos cuadros de música corren por cuadro de video, que son las marcas de
la bitácora.

El camino del MSU-1, que es el registro de volumen de la pista, lo mira
`test_con_msu_el_volumen_de_un_tema_que_sigue_baja_la_pista` en
`abl/test_msu.py`.
"""

from consola import en_la_wram, indice_del_tema

# Los cuadros de video que se mira, ya sonando el tema.
CUADROS = 120


def _escribir(una, simbolo, datos):
    una.consola.write_ram(en_la_wram(una.simbolos[simbolo]), bytes(datos))


def _prender_la_bitacora(una):
    _escribir(una, "MUS_LOG_I", [0, 0])
    _escribir(una, "MUS_LOG_YES", [1])
    return 0


def _leer_la_bitacora(una, desde):
    """Los pares (registro, valor) que llegaron a `dsp_music` desde `desde`,
    y dónde quedó: la bitácora es un anillo, y se lee en cada cuadro."""
    s = una.simbolos
    largo = s["MUS_LOG_LENGTH"]
    i = una.consola.ram(en_la_wram(s["MUS_LOG_I"]), 2)
    hasta = i[0] | i[1] << 8
    crudo = una.consola.ram(en_la_wram(s["MUS_LOG"]), largo)
    pares, j = [], desde
    while j != hasta:
        pares.append((crudo[j], crudo[j + 1]))
        j = (j + 2) % largo
    return pares, hasta


def _hasta_que_suene(una, nombre):
    tema = indice_del_tema(una, nombre)
    for _ in range(200):
        if una.palabra("song_current") == tema and not una.byte("music_off"):
            return tema
        una.correr(1)
    raise AssertionError("%s no llegó a sonar: la prueba no mide nada"
                         % nombre)


def _con_signo(v):
    return v - 256 if v >= 128 else v


def _volumenes(una, pares, ultimos):
    """El último valor que la ROM mandó a cada `VOL_L` y `VOL_R` de las
    voces de la música."""
    marca = una.simbolos["MUS_LOG_MARK"]
    for registro, valor in pares:
        if registro != marca and registro < 0x80 and registro & 0x0E == 0:
            ultimos[registro] = valor
    return ultimos


def _comparar_con_el_stream(una, ultimos, factor):
    """Cada `VOL` que el DSP tiene contra lo que el stream le escribió, por
    `factor`/256: es la cuenta de `volume_fade`, el multiplicador de la PPU
    con signo."""
    s = una.simbolos
    sombra = una.consola.ram(en_la_wram(s["MUS_SHADOW"]), 0x80)
    vistas = una.consola.ram(en_la_wram(s["MUS_VIEWS"]), 1)[0]
    medidos = 0
    for registro, valor in sorted(ultimos.items()):
        if not vistas & (1 << (registro >> 4)):
            continue
        quiere = (_con_signo(sombra[registro]) * factor) >> 8
        assert _con_signo(valor) == quiere, (
            "el registro $%02X quedó en %d y el stream le escribió %d: a "
            "volumen %d/256 tenía que quedar en %d"
            % (registro, _con_signo(valor), _con_signo(sombra[registro]),
               factor, quiere))
        if abs(_con_signo(sombra[registro])) >= 8:
            medidos += 1
    assert medidos >= 2, (
        "sólo %d voces con un volumen que se note: la prueba no distingue "
        "un volumen de otro" % medidos)


def test_un_tema_a_volumen_50_suena_a_un_cuarto(partida):
    """`PlayBGM evilrhys` a volumen 50: cada voz de la música, a un cuarto
    de lo que el stream le escribe —64 de 256—."""
    una = partida(caso="tema-a-volumen-50")
    _hasta_que_suene(una, "evilrhys")
    j = _prender_la_bitacora(una)
    ultimos = {}
    for _ in range(CUADROS):
        una.correr(1)
        pares, j = _leer_la_bitacora(una, j)
        _volumenes(una, pares, ultimos)
    _comparar_con_el_stream(una, ultimos, 64)


def test_un_tema_a_tempo_150_corre_uno_y_medio_cuadros_por_cuadro(partida):
    """`PlayBGM evilrhys` a tempo 150: en 120 cuadros de video, 180 de
    música. Se cuentan las marcas que `music_frame` deja en la bitácora, una
    por cuadro de música."""
    una = partida(caso="tema-a-tempo-150")
    _hasta_que_suene(una, "evilrhys")
    marca = una.simbolos["MUS_LOG_MARK"]
    j = _prender_la_bitacora(una)
    cuadros_de_musica = 0
    for _ in range(CUADROS):
        una.correr(1)
        pares, j = _leer_la_bitacora(una, j)
        cuadros_de_musica += sum(1 for r, _ in pares if r == marca)
    assert abs(cuadros_de_musica - CUADROS * 3 // 2) <= 1, (
        "en %d cuadros de video corrieron %d de música: a tempo 150 tenían "
        "que ser %d" % (CUADROS, cuadros_de_musica, CUADROS * 3 // 2))


def test_el_mismo_tema_con_otro_volumen_baja_sin_reiniciar(partida):
    """`PlayBGM evilrhys` a 100 y, treinta ticks después, a 50: el tema
    sigue por donde iba —`Game_System::BgmPlay` con el mismo nombre— y las
    voces que ya sonaban bajan a un cuarto sin esperar a la próxima nota."""
    una = partida(caso="tema-que-baja")
    _hasta_que_suene(una, "evilrhys")
    j = _prender_la_bitacora(una)
    ultimos = {}
    antes = una.avance_del_stream()
    for _ in range(300):
        una.correr(1)
        pares, j = _leer_la_bitacora(una, j)
        _volumenes(una, pares, ultimos)
        ahora = una.avance_del_stream()
        assert ahora >= antes, (
            "el stream volvió de $%06X a $%06X: el `PlayBGM` con otro "
            "volumen reinició el tema" % (antes, ahora))
        antes = ahora
        if not una.corriendo_una_pagina():
            break
    assert not una.corriendo_una_pagina(), "la página no llegó al final"
    _comparar_con_el_stream(una, ultimos, 64)
