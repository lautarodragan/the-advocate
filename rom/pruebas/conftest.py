"""Las piezas compartidas de las pruebas de estado.

**La ROM no cambia entre prueba y prueba.** Lo que cambia es el estado inicial,
y eso se escribe en la RAM —ver `Partida.prender`— o lo pone el caso, en vez de
hornearse en un cartucho distinto para cada prueba. Desde el paso 9f el
cartucho es el mismo que usa la tanda —ver `tools/ensamblado/cartuchos.py`— y las
pruebas no arman nada: piden un caso por el nombre.

Una prueba que no pide ninguno arranca en el mapa 5 con el grupo del juego, que
es `en-5`: la prueba del recuerdo tiene una lista de toques de A afinada al
cuadro y conviene no moverle el arranque. Las demás llegan a su mapa con un
caso `en-<mapa>`, o con `Partida.ir_al_mapa`, que le pide a la ROM el mismo
fundido que una puerta.

Lo que **no** se comparte es la partida: cada prueba arranca su propia consola
desde el reset. Compartirla dejaría a una corriendo sobre lo que dejó otra, que
es la clase de error que este repo ya cobró con `mapdata.inc`.
"""

import os

import pytest

import tanda
from comun import proyecto
from consola import EMPEZAR
from ensamblado import cartuchos

# Dónde arranca una prueba de estado que no pide otra cosa: el mapa 5, con el
# grupo del juego. Es el caso `en-5`, el `Teleport` a la celda donde el héroe
# caía cuando el 5 era el mapa de arranque de su cartucho.
ARRANQUE = "en-5"


# Las pruebas cuyas capturas son todas la misma pantalla **a propósito**, con
# su porqué. Cualquier otra que dé eso no está mirando lo que cree: ver
# `_capturas_distintas`.
MISMA_PANTALLA = {
    # Lo que pasa en el primer tick y después tiene que quedarse quieto: el
    # último mira que no se deshaga ni llegue tarde, y lo que distingue el caso
    # es la golden, no la diferencia entre sus ticks.
    "test_pan[pan-cero]": "cero cuadros: el tinte ya está en el tick 1",
    "test_tecla[tecla-dir]": "el tinte llega con el toque del 40 y se queda",
    "test_npc[npc-encara]": "girar hacia el héroe es instantáneo",
    "test_npc[npc-encara-lado]": "girar hacia el héroe es instantáneo",
    "test_lugar[lugar-quieto]": "plantado sin ruta, no tiene a dónde ir",
    "test_escena[bloqueo]": "el droide lo frena en (7,73) antes del 40",
    "test_escena[ascensor]": "el ascensor abierto con el switch 11, quieto",
    "test_cinematica[factoria]": "el reparto de VRAM, que no cambia solo",
    # Las ramas: cada caso es la mitad de un par, contestan en el primer tick,
    # y lo que cobra la respuesta es la diferencia con su pareja.
    "test_rama_item[rama-item]": "contesta en el primer tick",
    "test_rama_item[rama-item-no]": "contesta en el primer tick",
    "test_rama_actor[rama-equipo]": "contesta en el primer tick",
    "test_rama_actor[rama-equipo-no]": "contesta en el primer tick",
    "test_rama_actor[rama-hab]": "contesta en el primer tick",
    "test_rama_actor[rama-hab-no]": "contesta en el primer tick",
    # Las que tienen que no hacer nada, o hacer siempre lo mismo.
    "test_vars[cofre-no]": "sin página activa el cofre no está, ni antes ni "
                           "después: lo que se ve lo distingue `cofre-30`",
    "test_vars[cofre-llave]": "la página del ítem no dibuja, igual que ninguna",
    "test_ruta_pisa[ruta-pasa]": "pasa por encima y no abre nada, nunca",
    "test_hablar[hablar-sin-switch]": "sin el switch, A no hace nada",
    "test_hablar[hablar-repetido]": "el mismo mensaje cada vez que le habla",
}


@pytest.fixture(autouse=True)
def _capturas_distintas(request):
    """Falla si todas las goldens de una prueba son la misma pantalla.

    Varios ticks idénticos quieren decir que entre el primero y el último no
    pasó nada: `ev41` estuvo así desde que nació —el evento nunca corría— y
    `varios-18-down` desde `6cfce1e` —una página automática no dejaba caminar
    al héroe—, y las dos pasaban en verde porque una golden defiende lo que
    congeló. Esto no sabe si lo congelado está bien; sabe que tres fotos
    iguales no prueban tres cosas.
    """
    del tanda.CAPTURAS[:]
    yield
    capturas = list(tanda.CAPTURAS)
    if len(capturas) < 2 or len({h for _n, h in capturas}) > 1:
        return
    if request.node.name in MISMA_PANTALLA:
        return
    pytest.fail(
        "las %d goldens de %s son la misma pantalla (%s): entre el primer "
        "tick y el último no cambió nada. O el caso no ejercita lo que dice, "
        "o sobran ticks; si es a propósito, va en `MISMA_PANTALLA` de "
        "pruebas/conftest.py con su porqué."
        % (len(capturas), request.node.name,
           ", ".join(n for n, _h in capturas)), pytrace=False)


@pytest.fixture
def partida():
    """Una fábrica: `partida()`, o `partida(switch=[16])`.

    Devuelve la partida arrancada en el caso que se pida —`en-5` si no se
    pide ninguno—, pasando la pantalla de título por "Begin the Story". `switch`
    se escribe en la RAM antes del primer cuadro de juego; para ir a otro mapa,
    `.ir_al_mapa(...)`. Con `titulo` y sin caso, la partida es **la de
    verdad**: `release` desde el título, con la página que no hace nada
    —la 0 sin el mapa de debug; ver `tanda.partida`—.
    """
    def hacer(switch=(), caso=None, titulo=None, en=None):
        if titulo is not None and caso is None:
            return tanda.partida(None, en=en or cartuchos.RELEASE,
                                 switches=switch, titulo=titulo)
        return tanda.partida(caso or ARRANQUE, en=en, switches=switch,
                             titulo=titulo)

    return hacer


# Dónde quedan las capturas de cada hito de las pruebas que **juegan**, una
# carpeta por tramo. Las goldens de `pruebas/golden/playthrough/<tramo>/` se
# buscan por ese mismo nombre: ver `Recorrido.foto`.
FOTOS = os.path.join(proyecto.snapshots(), "playthrough")


# Las dos que siguen **importan `recorrido` adentro** y no arriba, y no es
# descuido: ese módulo arrastra el lector de `.lmu` y el renderer, y eso no
# tiene por qué pagarlo cada prueba que no juega —este conftest lo carga
# pytest antes que cualquiera—. Vivían en un `conftest.py` de `pruebas/abl/`
# hasta el 2026-09-23, y eso duró una corrida: acá no hay paquetes, así que los
# dos conftest se importan los dos como `conftest` y el segundo tapa al
# primero. `test_batalla.py` hacía `from conftest import LINKAGE` y cinco
# módulos se cayeron con `ImportError`.
@pytest.fixture(scope="session")
def mundo():
    """La colisión y los teletransportes del juego original, una vez por
    corrida: leer los `.lmu` y resolverles los cuatro bits a cada celda cuesta
    más que todo el BFS que viene después."""
    from recorrido import Mundo
    return Mundo()


@pytest.fixture
def recorrido(partida, mundo):
    """Una jugada sobre `release`, la ROM que se juega, entrando por la
    pantalla de título, con sus capturas en `FOTOS/<nombre>`."""
    from recorrido import Recorrido

    def hacer(nombre, switch=(), caso=None):
        # "Begin the Story": una jugada empieza por ahí como cualquiera. Sin
        # `caso`, en la partida de verdad sin el mapa de debug —ver
        # `tanda.partida`—; con él, en esa página: la apertura entra por el
        # mapa de debug y cruza la puerta del comienzo normal.
        if caso is not None:
            return Recorrido(tanda.partida(caso, switches=switch), mundo,
                             fotos=os.path.join(FOTOS, nombre))
        return Recorrido(partida(switch=switch, titulo=EMPEZAR),
                         mundo, fotos=os.path.join(FOTOS, nombre))
    return hacer


@pytest.fixture
def con_musica(recorrido):
    """Una fábrica: `con_musica()` es la apertura de `release` jugada hasta
    que Kersh toma el control, con su tema sonando.

    Es el primer lugar de la ROM que se juega con música y con el control:
    después de "Begin the Story" no suena nada —el tema del título se corta y
    el mapa 4 no trae uno— hasta que la apertura pone el suyo, y el héroe no
    se mueve hasta que termina. Hasta el 2026-09-24 las pruebas de música
    tenían eso gratis: corrían en `juego`, que arrancaba con un tema puesto.
    """
    def hacer():
        r = recorrido("con-musica")
        r.esperar("que la apertura termine y Kersh tome el control",
                  lambda p: p.switch(3) and not p.corriendo_una_pagina(),
                  tope=6000)
        return r.p
    return hacer
