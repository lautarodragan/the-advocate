"""Quién puede ser líder del grupo, que es de quién sale el gráfico del héroe.

Los tiles del héroe viven en VRAM y no se cargan en caliente, así que el
conversor tiene que saber de antemano qué actores pueden llegar a ir primeros y
guardar las poses de todos ellos. Si se le escapa uno, la ROM lo dibuja sin
gráfico: no falla, no avisa, el personaje simplemente no está.

Esta prueba no arranca ninguna ROM —le pregunta al conversor,
`rm2k-snes-convert leaders`— y está acá igual porque lo que cuida es lo mismo
que cuidan las otras: que el juego se vea.

El caso que la motivó lo encontró taro jugando el 2026-09-07. En la apertura,
al final de la escalera, aparecían Core y Manta pero no Kersh. Kersh es el
héroe en esa escena, y su gráfico sale de ser el primero del grupo.
"""

import conversor
from datos import DEMO

KERSH, DUMMY_HERO, TALAN = 11, 10, 14



def test_kersh_puede_liderar_en_la_apertura():
    """El `pone Kersh` de la apertura tiene que contar aunque el mapa 4 vaya
    antes en el directorio.

    Falla si la simulación arrastra el grupo de un mapa al siguiente: la página
    del "1 year earlier" del mapa 4 pone a Talan, y con el grupo compartido
    Kersh entraba **detrás** de él y no era líder nunca.
    """
    lideres = conversor.lideres(DEMO, [DUMMY_HERO])
    assert KERSH in lideres, \
        "Kersh no quedó como líder posible, así que el héroe se va a dibujar " \
        "sin gráfico en la apertura; los líderes fueron %s" % lideres


def test_el_orden_de_los_mapas_no_cambia_el_resultado():
    """La misma ROM con los mapas en otro orden tiene que dar lo mismo.

    Es la propiedad que faltaba: el orden del directorio no es el orden en que
    se juega, así que no puede decidir quién se dibuja.
    """
    derecho = conversor.lideres(DEMO, [DUMMY_HERO])
    revés = conversor.lideres(list(reversed(DEMO)), [DUMMY_HERO])
    assert set(derecho) == set(revés), \
        "los líderes dependen del orden de los mapas: %s contra %s" % (
            derecho, revés)
