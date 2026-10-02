"""Lo que las pruebas leen del juego original para saber qué esperar.

La base de datos y el System de las ventanas, los máximos de cada actor, una
página compilada, y los dos índices que arma el conversor —qué ranura le toca
a cada variable y a cada par (actor, habilidad)— con la misma cuenta que usó
al armar el cartucho.

Todo sale de `resources.GAME_DIR`, que es `ABL_GAME_DIR` si está puesta.

**La base se lee una vez por proceso y se comparte**, y eso vale mientras
nadie la modifique: ni las pruebas ni lo que llaman del conversor le
escriben —`pantallas.equipar` y el modelo de la pelea copian lo que toman—.
Antes cada prueba la leía de nuevo, así que una que le escribiera a la
compartida sería un cambio de comportamiento, no de arnés.
"""

import functools
import json
import os

import cartuchos
from rpgmaker.resources import GAME_DIR


# Los mapas de la apertura, en el orden en que se le pasan al conversor: el 4,
# donde arranca, primero.
DEMO = [4, 1, 2, 3, 5, 6, 7]


@functools.lru_cache(maxsize=None)
def base():
    """`RPG_RT.ldb`, ya leído."""
    from rpgmaker import lcf
    return lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))


def maximos():
    """Los HP y SP máximos de cada actor en su nivel inicial, sacados del LDB
    y no de la ROM.

    Es la misma cuenta que emite `actor_hpmax`, pero leída del otro lado: si
    la ROM copiara de una tabla equivocada, comparar contra esa misma tabla
    daría verde. La hace el modelo de la pelea —una pelea con todos los
    actores y ningún paso—, que la toma de `rm2k-rules`: hasta el 2026-10-02
    había una copia en Python, `port/rules.py`, y era lo único que la usaba.
    """
    return dict(_maximos())


@functools.lru_cache(maxsize=None)
def _maximos():
    import modelo
    actores = sorted(base().actors)
    pelea = modelo.Battle([modelo.actor_of(a) for a in actores])
    return {a: (c.hp_max, c.sp_max) for a, c in zip(actores, pelea.actors)}


def pagina_de(map_id, evento_id, numero):
    """La página `numero` del evento `evento_id` del mapa, compilada sola:
    con su bloque de textos, sus temas y sus gráficos, en un cartucho con
    todos los mapas del juego. Es lo que contesta la primera llamada del
    compilador —ver `compiler.scan`—; None si no compila."""
    from port import compiler
    from rpgmaker import lcf
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
    evento = [n for n, e in enumerate(game_map.events) if e.id == evento_id][0]
    return compiler.compiled_pages(todo_el_juego(), map_id).get(
        (evento, numero))


@functools.lru_cache(maxsize=None)
def todo_el_juego():
    """La primera llamada del compilador con todos los mapas del juego."""
    from port import compiler
    dump = compiler.dump_of(GAME_DIR)
    mapas = sorted(int(n[3:7]) for n in os.listdir(os.path.join(dump, "maps"))
                   if n.startswith("Map") and n.endswith(".json"))
    return compiler.scan(dump, mapas)


# --- los índices del cartucho --------------------------------------------------
#
# Se arman acá y no se leen de la ROM porque la ROM no los lleva: el conversor
# resuelve cada número a su ranura al compilar. Y se arman **como el
# conversor**, con los comandos de los casos del cartucho, porque las ranuras
# van por número de variable y una de un caso que el juego no nombra corre a
# todas las que vienen detrás.

@functools.lru_cache(maxsize=None)
def comandos_de_los_casos(cartucho=cartuchos.RELEASE):
    """Los comandos de todos los casos del cartucho, seguidos: lo que barre
    `case_commands` en el conversor."""
    from rpgmaker import lcf
    comandos = []
    for nombre in cartuchos.casos_de(cartucho):
        with open(os.path.join(cartuchos.carpeta_de_casos(), nombre + ".json"),
                  encoding="utf-8") as archivo:
            comandos += lcf.handwritten_commands(json.load(archivo))
    return tuple(comandos)


@functools.lru_cache(maxsize=None)
def ranuras_de_variable(cartucho=cartuchos.RELEASE):
    """{número de variable: ranura} del cartucho: las del juego, las de sus
    casos y, si lleva más de uno, la que elige el caso —ver
    `events.CASE_VARIABLE`—. Las contesta el compilador, igual que al
    conversor."""
    from port import compiler, events
    extra = ({events.CASE_VARIABLE}
             if len(cartuchos.casos_de(cartucho)) > 1 else set())
    return compiler.slots(compiler.dump_of(GAME_DIR),
                          comandos_de_los_casos(cartucho), extra)[0]


@functools.lru_cache(maxsize=None)
def ranuras_de_habilidad(cartucho=cartuchos.RELEASE):
    """{(actor, habilidad): bit} del cartucho: los pares del juego con los que
    nombran sus casos, que es lo que contesta el compilador al conversor."""
    from port import compiler
    return compiler.slots(compiler.dump_of(GAME_DIR),
                          comandos_de_los_casos(cartucho))[1]
