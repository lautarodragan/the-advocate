"""Lo que las pruebas leen del juego original para saber qué esperar.

La base de datos y el System de las ventanas, los máximos de cada actor, una
página compilada, y los dos índices que arma el conversor —qué ranura le toca
a cada variable y a cada par (actor, habilidad)— con la misma cuenta que usó
al armar el cartucho.

Todo sale de `render_map.GAME_DIR`, que es `ABL_GAME_DIR` si está puesta.

**La base se lee una vez por proceso y se comparte**, y eso vale mientras
nadie la modifique: ni las pruebas ni lo que llaman de `tools/port/` le
escriben —`pantallas.equipar` y el modelo de la pelea copian lo que toman—.
Antes cada prueba la leía de nuevo, así que una que le escribiera a la
compartida sería un cambio de comportamiento, no de arnés.
"""

import functools
import json
import os

from ensamblado import cartuchos
from render.render_map import GAME_DIR


@functools.lru_cache(maxsize=None)
def base():
    """`RPG_RT.ldb`, ya leído."""
    from rpgmaker import lcf
    return lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))


@functools.lru_cache(maxsize=None)
def skin():
    """El System del juego, con el que se dibujan las ventanas de los
    dibujos de Python contra los que se comparan las pantallas."""
    from port import ventana
    return ventana.skin(GAME_DIR, base().system_name)


def maximos():
    """Los HP y SP máximos de cada actor, sacados del LDB y no de la ROM.

    Es la misma cuenta que emite `actor_hpmax`, pero leída del otro lado: si
    la ROM copiara de una tabla equivocada, comparar contra esa misma tabla
    daría verde.
    """
    from port import titulo
    return {a: (titulo.parametro_de(actor, "maxhp"),
                titulo.parametro_de(actor, "maxsp"))
            for a, actor in base().actors.items()}


def pagina_de(map_id, evento_id, numero):
    """La página `numero` del evento `evento_id` del mapa, compilada."""
    from port import eventos
    from rpgmaker import lcf
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
    evento = [e for e in game_map.events if e.id == evento_id][0]
    for indexar in (eventos.indexar_variables, eventos.indexar_animaciones,
                    eventos.indexar_comunes, eventos.indexar_audio_de_batalla,
                    eventos.indexar_actores, eventos.indexar_habilidades):
        indexar(GAME_DIR)
    del_mapa = eventos.Eventos(game_map).para(evento.id)
    return eventos.compilar_pagina(
        evento.pages[numero], lambda mid: 0, eventos.Mensajes(), del_mapa,
        eventos.Temas(), eventos.Graficos(), eventos.Imagenes(GAME_DIR))


# --- los índices del cartucho --------------------------------------------------
#
# Se arman acá y no se leen de la ROM porque la ROM no los lleva: el conversor
# resuelve cada número a su ranura al compilar. Y se arman **como el
# conversor**, con los comandos de los casos del cartucho, porque las ranuras
# van por número de variable y una de un caso que el juego no nombra corre a
# todas las que vienen detrás.

@functools.lru_cache(maxsize=None)
def comandos_de_los_casos(cartucho=cartuchos.PRUEBAS):
    """Los comandos de todos los casos del cartucho, seguidos: lo que barre
    `comandos_de_casos` en el conversor."""
    from rpgmaker import lcf
    comandos = []
    for nombre in cartuchos.casos_de(cartucho):
        with open(os.path.join(cartuchos.CASOS, nombre + ".json"),
                  encoding="utf-8") as archivo:
            comandos += lcf.comandos_escritos(json.load(archivo))
    return tuple(comandos)


@functools.lru_cache(maxsize=None)
def ranuras_de_variable(cartucho=cartuchos.PRUEBAS):
    """{número de variable: ranura} del cartucho: las del juego, las de sus
    casos y, si lleva más de uno, la que elige el caso —ver
    `eventos.VARIABLE_DE_CASO`—. Es lo que le pasa a `indexar_variables` el
    conversor."""
    from port import eventos
    extra = eventos.variables_de_comandos(comandos_de_los_casos(cartucho))
    if len(cartuchos.casos_de(cartucho)) > 1:
        extra.add(eventos.VARIABLE_DE_CASO)
    return eventos.variables_de(GAME_DIR, None, extra)


@functools.lru_cache(maxsize=None)
def ranuras_de_habilidad(cartucho=cartuchos.PRUEBAS):
    """{(actor, habilidad): bit} del cartucho: los pares del juego con los que
    nombran sus casos, que es lo que le pasa el conversor."""
    from port import eventos
    return eventos.pares_de_habilidad(
        GAME_DIR, eventos.pares_de_habilidad_de_comandos(
            comandos_de_los_casos(cartucho)))
