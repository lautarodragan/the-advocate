"""Perder una pelea sin manejador de derrota vuelve al arranque.

En RM2k un `EnemyEncounter` con `defeat_mode` 0 no trae bloque de manejadores:
perder no es una rama de la página sino `Scene_Gameover`, o sea la imagen de
Game Over y, al apretar, la pantalla de título. Son **15 páginas del juego**,
y entre ellas las tres del `EV0006` del mapa 26, que es el jefe de los Rat
Tracks: hasta el 2026-09-13 ninguna compilaba y el jefe no aparecía nunca.

Ahora compilan, con el destino de la derrota puesto en `eventos.BATALLA_PERDER`
—$FFFF, un destino imposible adentro de una página— y la ROM lo resuelve en
`op_batalla` con un `jml reset`. **La imagen no se dibuja**; ver
`assets/LIMITACIONES.md`.

Esto va acá y no en la tanda de pixeles por una razón que conviene tener
escrita: del lado de la referencia la pelea no se juega —`OP_BATALLA` se va
siempre por la rama de victoria, ver tools/eventos.py— así que no hay ningún
cuadro que comparar. Sin esta prueba, el `jml reset` sería exactamente lo que
AGENTS.md llama "un camino que ninguna prueba ejecuta".

**Cómo se pierde sin pelear**: con todo el grupo en cero HP, `batalla_correr`
contesta derrota antes de abrir la pantalla —el `ba_actor_siguiente` que
devuelve $FF, "nadie en pie: se pierde sin pelear"—. Así la prueba no depende
de ningún tiro de dado.

El control es el mismo caso con la derrota apuntando al final del bloque, que
es lo que emiten las peleas con manejadores: ahí la ROM **no** se reinicia y la
página sigue. Sin él, un reinicio por cualquier otra causa —una pelea que
cuelgue, una pila que se desborde— pasaría por verde.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import eventos                                              # noqa: E402
import lcf                                                  # noqa: E402
from render_map import GAME_DIR                             # noqa: E402

# La tropa del droide del mapa 2, que es la que ya viaja en los cartuchos de
# prueba: cuál sea da lo mismo, porque nadie llega a pelearla.
TROPA = 82
# Ticks que la página de prueba espera antes de abrir la pelea. Son los que la
# prueba usa para poner los HP en cero; con menos, la pelea se abre antes de
# que la escritura llegue.
ESPERA = 20
# El jefe de los Rat Tracks, que es lo que todo esto destraba.
RAT_TRACKS_B2, JEFE = 26, 6


def sin_hp(una):
    """Todo el grupo caído, escrito en la RAM lejana."""
    largo = una.simbolos["FAR_SP"] - una.simbolos["FAR_HP"]
    una.consola.escribir_ram(una.simbolos["FAR_HP"], [0] * largo)
    return una


def cuadros_hasta_reiniciar(una, tope=900):
    """Cuántos cuadros de hardware pasan hasta que `vueltas` se va para atrás.

    Se cuenta en cuadros y no en ticks a propósito: `Partida.correr` avanza
    hasta que `vueltas` **suba**, y un reinicio la pone en cero, así que
    esperar un tick después del Game Over no terminaría nunca.
    """
    alto = una.palabra("vueltas")
    for n in range(tope):
        una.consola.correr(1)
        ahora = una.palabra("vueltas")
        if ahora < alto:
            return n
        alto = ahora
    return None


# --- lo que se emite -------------------------------------------------------

def pagina_del_jefe(numero):
    """La página `numero` del evento del jefe de los Rat Tracks, compilada."""
    game_map = lcf.Map(os.path.join(GAME_DIR,
                                    "Map%04d.lmu" % RAT_TRACKS_B2))
    evento = [e for e in game_map.events if e.id == JEFE][0]
    for indexar in (eventos.indexar_variables, eventos.indexar_animaciones,
                    eventos.indexar_comunes, eventos.indexar_audio_de_batalla,
                    eventos.indexar_actores):
        indexar(GAME_DIR)
    del_mapa = eventos.Eventos(game_map).para(evento.id)
    return eventos.compilar_pagina(
        evento.pages[numero], lambda mid: 0, eventos.Mensajes(), del_mapa,
        eventos.Temas(), eventos.Graficos(), eventos.Imagenes(GAME_DIR))


def test_las_tres_paginas_del_jefe_compilan():
    """Las tres del `EV0006` del mapa 26, que son las que taro no podía ver.

    Su `EnemyEncounter` viene con `escape_mode` 0 y `defeat_mode` 0, o sea sin
    bloque de manejadores: son las dos cosas que hasta el 2026-09-13 la cortaban
    —una el `raise` del Game Over y la otra "una batalla sin cerrar"— y por eso
    destrabar una sola daba cero páginas.
    """
    for numero in (0, 1, 2):
        assert pagina_del_jefe(numero) is not None, (
            "la página %d del jefe de los Rat Tracks no compila" % numero)


def test_la_derrota_del_jefe_apunta_al_game_over():
    """Y el destino que se emite es `BATALLA_PERDER`, no el comando siguiente.

    Es lo que separa "el jefe aparece" de "el jefe aparece y perder no pasa
    nada": sin esto la página seguiría como si hubiera ganado, que es
    exactamente la clase de mentira que el `raise` estaba evitando.
    """
    codigo = pagina_del_jefe(0)
    peleas = [i for i, b in enumerate(codigo) if b == eventos.OP_BATALLA]
    # El opcode puede aparecer como operando de otro comando, así que se busca
    # el que además lleva la tropa que el LDB dice.
    for i in peleas:
        if codigo[i + 1] | (codigo[i + 2] << 8) != 97:
            continue
        derrota = codigo[i + 7] | (codigo[i + 8] << 8)
        assert derrota == eventos.BATALLA_PERDER, (
            "la derrota de la pelea del jefe va a %d y tendría que ser el "
            "Game Over" % derrota)
        return
    raise AssertionError("la página del jefe no emite ninguna pelea")


# --- y lo que la consola hace con eso --------------------------------------

def test_perder_sin_manejador_vuelve_al_arranque(partida):
    una = partida(batalla=TROPA, game_over=True, espera=ESPERA)
    sin_hp(una)
    cuando = cuadros_hasta_reiniciar(una)
    assert cuando is not None, (
        "la ROM perdió la pelea y siguió como si nada: el destino "
        "BATALLA_PERDER tendría que haberla mandado a `reset`")
    # Y lo que hay del otro lado del reinicio es el arranque de siempre: la
    # cuenta de cuadros vuelve a empezar y el mapa es el primero de la tabla.
    una.consola.correr(una.simbolos["BOOT_CUADROS"] + 3)
    assert una.palabra("mapa_actual") == 0


def test_perder_con_manejador_no_reinicia(partida):
    """El control. Misma pelea perdida, con la derrota apuntando a la página."""
    una = partida(batalla=TROPA, game_over=False, espera=ESPERA)
    sin_hp(una)
    assert cuadros_hasta_reiniciar(una, tope=300) is None, (
        "la ROM se reinició con una pelea que sí tiene a dónde volver: "
        "entonces el reinicio del otro caso no lo causa BATALLA_PERDER")


# --- y el otro camino a una pelea: el encuentro al azar ---------------------
#
# Hasta el 2026-09-13 el Game Over era sólo del `EnemyEncounter` de una página:
# `op_batalla` miraba `BA_RESULT` y saltaba al destino, y `BATALLA_PERDER` lo
# mandaba a `reset`. El encuentro al azar arranca la pelea **sin bytecode**
# —`pelea_arrancar` desde `move_hero`— así que nadie miraba el resultado y
# perder devolvía el control al mapa.
#
# Lo que eso dejaba puesto es lo que taro reportó jugando: el grupo vuelve al
# mapa con todos en cero HP, `modo_fin` los guarda así en `FAR_HP`, y de ahí en
# más **cada pelea se pierde sola antes de abrirse**, porque `batalla_correr`
# contesta derrota con nadie en pie. O sea que los tres síntomas —no hay Game
# Over, el grupo queda en cero, y toda pelea siguiente se pierde— son este solo
# defecto.
#
# Un encuentro al azar no puede traer manejador de derrota: no hay página que
# lo emita. Así que la derrota es siempre Game Over, como en RM2k.

RAT_TRACKS_B1 = 21
# Cada cuántos pasos sale un encuentro, en vez de los 80 que dice el árbol:
# con los de verdad la prueba caminaría minutos. Es `--encuentros-de-prueba`,
# el mismo que usa el caso `snes-encuentro` de la tanda.
PASOS = 8
# El grupo de la intro, que **gana** las peleas de ese mapa en un turno: es lo
# que hace que el control no dependa de ningún tiro de dado. Medido el
# 2026-09-13: contra las tropas 94, 95 y 96 el enemigo cae siempre en el
# primer turno y el grupo no pierde un solo HP.
GRUPO = (11, 12, 13)
DIRECCIONES = ("up", "down", "left", "right")


def caminar(una, cuadros, tope_sin_reinicio=False):
    """Camina con el pad en cuadros de hardware y dice en cuál se reinició.

    No se puede caminar por ticks: la pelea corre su propio lazo y `vueltas`
    no avanza mientras dura, así que `_un_tick` se quedaría esperando. Se
    cambia de dirección cada cuarenta cuadros para no clavarse contra una
    pared del mapa.
    """
    alto = una.palabra("vueltas")
    for n in range(cuadros):
        una.consola.apretar(DIRECCIONES[(n // 40) % 4])
        una.consola.correr(1)
        ahora = una.palabra("vueltas")
        if ahora + 5 < alto:
            una.consola.apretar()
            return n
        alto = max(alto, ahora)
    una.consola.apretar()
    return None


def con_encuentros(partida):
    return partida(mapas=(RAT_TRACKS_B1, []), encuentros=PASOS, grupo=GRUPO)


def test_perder_un_encuentro_al_azar_es_game_over(partida):
    """Con el grupo caído, el primer encuentro tiene que volver al arranque."""
    una = con_encuentros(partida)
    sin_hp(una)
    cuando = caminar(una, 900)
    assert cuando is not None, (
        "se perdió un encuentro al azar y la ROM siguió en el mapa: la "
        "derrota de una pelea que nadie arrancó desde una página también "
        "tiene que ser Game Over")
    una.consola.correr(una.simbolos["BOOT_CUADROS"] + 3)
    assert una.palabra("mapa_actual") == 0


def test_ganar_encuentros_al_azar_no_reinicia(partida):
    """El control: el mismo mapa y el mismo grupo, con los HP que trae.

    Sin él, un reinicio por cualquier otra causa —una pila que se desborde al
    entrar a la pelea, un cuelgue— pasaría por Game Over verificado.
    """
    una = con_encuentros(partida)
    assert caminar(una, 900) is None, (
        "la ROM se reinició ganando encuentros al azar")
