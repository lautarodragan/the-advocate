"""Que el tema que la ROM dice estar tocando tenga sus muestras en la ARAM.

Esto es la otra mitad de la red, y acá se ve por qué hace falta: **el silencio
no cambia un pixel**. La tanda de `rom/hitos.txt` compara la pantalla cuadro por
cuadro contra la referencia y da cero igual con la música muda, así que un tema
que suena contra un directorio de silencios pasa entero por delante de ella sin
que nada se ponga rojo. El defecto de la pantalla de título vivió un día por
eso, y encima tapado: con archivos de MSU-1 al lado de la ROM la pista suena y
el SPC700 no toca nada, así que el único camino roto era justamente el que
siempre tiene que andar.

Lo que se pregunta es lo mismo que mira `tema_asegurar` en main.s: para cada
muestra que el stream del tema escribe en SRCN —`tema_muestras`, leída del
cartucho—, que `FAR_ARAM_DE` diga dónde está. Una muestra que no está apunta al
bloque de silencio, o sea una nota que no se oye.

La pantalla de título es el caso interesante y no un caso cualquiera: su tema
sale de `title_music` del LDB y **no entra en el paquete de audio de ningún
mapa**, porque los paquetes se arman con los temas que las páginas de cada mapa
pueden prender. O sea que es el único tema de la ROM que depende de que
`tema_asegurar` lo cargue en caliente, y por eso es el que delata el camino.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

EMPEZAR = 0

# Un tema para el mapa de arranque: los mapas de estas pruebas no traen música
# propia, y sin uno `TEMA_ARRANQUE` es $FF y no hay con qué comparar.
TEMA_DEL_MAPA = "escape_newyork"


def test_el_tema_del_titulo_tiene_sus_muestras_en_la_aram(partida):
    """La pantalla de título, sin MSU-1: el tema arranca y sus muestras están.

    Es el caso que cobra el defecto del 2026-09-12. Con él puesto la ROM decía
    estar tocando `Fantasia_Of_The_Wind` —`tema_actual` con el tema del título
    y `music_apagada` en cero— y las muestras que ese tema pide seguían sin
    subir, así que las ocho voces atacaban el silencio.

    No hace falta apagar el MSU-1 para probar esto: el core no emula el
    cartucho con la extensión, así que `msu_detectar` no encuentra la firma y
    `music_start` cae siempre por `sin_pista`, que es el camino que se quiere
    medir.
    """
    una = partida(titulo=EMPEZAR).quedarse_en_el_titulo()

    tema = una.simbolos["TEMA_TITULO"]
    assert tema != 0xFF, (
        "esta ROM no lleva tema de título, así que el caso no compara nada")
    assert una.palabra("tema_actual") == tema, (
        "la pantalla de título dice estar tocando el tema %d y el suyo es el "
        "%d" % (una.palabra("tema_actual"), tema))
    assert not una.byte("music_apagada"), (
        "la pantalla de título quedó callada: `music_start` no llegó a "
        "prender el tema")

    faltan = sorted(set(una.muestras_del_tema(tema))
                    - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema del título dice estar sonando y le faltan en la ARAM las "
        "muestras %s de las %s que usa: son notas contra el bloque de "
        "silencio. Lo tenía que subir `tema_asegurar` al ver que el paquete "
        "del mapa no las traía"
        % (faltan, sorted(una.muestras_del_tema(tema))))


def test_entrar_al_juego_devuelve_las_muestras_del_tema_del_mapa(partida):
    """Y al salir del título, el tema del mapa recupera las suyas.

    Es la otra punta del mismo camino: subir el tema del título **desaloja** lo
    que había, porque la ARAM no alcanza para todo y `paquete_cargar` acomoda
    desde cero lo que el paquete nuevo quiere. Si volver al juego no rehiciera
    el paquete del mapa, el jugador entraría a la partida con el tema del mapa
    sonando mudo, que es el mismo defecto una pantalla más tarde.

    Los dos temas piden muestras distintas —se comprueba, porque si pidieran
    las mismas el caso pasaría sin mover nada—.
    """
    una = partida(titulo=EMPEZAR, tema=TEMA_DEL_MAPA)

    del_mapa = una.palabra("tema_actual")
    assert not una.byte("music_apagada"), (
        "esta ROM tenía que entrar al juego con el tema del mapa sonando")
    assert del_mapa != una.simbolos["TEMA_TITULO"], (
        "el tema del mapa y el del título son el mismo: no hay desalojo que "
        "probar")

    suyas = set(una.muestras_del_tema(del_mapa))
    del_titulo = set(una.muestras_del_tema(una.simbolos["TEMA_TITULO"]))
    assert suyas - del_titulo, (
        "los dos temas usan las mismas muestras, así que entrar al juego no "
        "tiene nada que reponer")

    faltan = sorted(suyas - una.muestras_en_la_aram())
    assert not faltan, (
        "se entró al juego y al tema del mapa le faltan en la ARAM las "
        "muestras %s de las %s que usa" % (faltan, sorted(suyas)))
