"""La pantalla de la pelea, y el arnés de las que **congelan el reloj del
juego**.

Lo que sigue vale también para `test_menu_golden.py`, `test_guardar_golden.py`
y `test_titulo_golden.py`: lo que los junta no es de qué habla cada caso sino
cómo hay que correrlo.

En todos los demás, un tick de la ROM es una vuelta del lazo principal y
`vueltas` lo cuenta; acá no: la pantalla de batalla corre su propio lazo, y el
menú de pausa, la lista de ranuras y la de título no son el juego. Esperar un
tick ahí adentro no termina nunca —el 2026-09-10 una captura sin ese cuidado se
comió una hora de CPU y 42 GiB antes de que alguien la viera en `ps`—.

Así que acá se cuentan **cuadros de hardware**, que es el `--sin-contador` del
corredor, y por eso estos casos no usan `Partida` sino `consola_cruda`: una
`Partida` es el reloj de ticks, y una que no pueda contarlos sería una que
miente sobre lo que sabe.

De ahí sale la trampa que hay que tener a la vista: **`toques` y
`toques_hardware` cuentan con un cuadro de diferencia.** Con el reloj en
cuadros, el primero cae en el cuadro `n-1` y el segundo en el `n`, que es lo
que hacía el corredor —ver `pruebas/arnes/tanda.py`—. Medido: ninguna golden de hoy los distingue —se
probó unificarlos y no se puso nada rojo— pero un caso nuevo que caiga en el
borde sí. Está explicado en `correr_hardware`.

Y los que vuelven al mapa —`*-vuelve-*`— son los otros: ahí la pantalla ya se
cerró, el reloj del juego corre de nuevo y los ticks vuelven a ser ticks, con
los toques todavía en cuadros de hardware porque caen adentro de la pantalla.

El nombre que abre cada docstring es el del caso, que es también el de su
golden.
"""

import pytest

from tanda import (consola_cruda, correr_hardware, golden, partida,
                   ticks_de_avance)


# La pantalla de batalla: nombre, la página de prueba —la pelea, con su
# grupo de tres y su inventario—, cuántos cuadros de hardware, los toques que
# pelean y el cartucho, si no es el de pruebas.
#
# La pelea de `batalla` recién toma el control en el cuadro 186: antes van la
# transición de entrada —dos destellos, el fundido del mapa, la carga del
# paquete de audio en negro y el mosaico, ver `fundido_de_pelea.s`— y un toque
# que caiga ahí se pierde. Hasta el 2026-09-26 la tomaba en el 118, y todos
# los números de acá se corrieron 68 cuadros sin que cambiara ninguna golden.
BATALLAS = (
    ("batalla", "batalla", 268, (), None),
    ("batalla-blanco", "batalla", 268, ("a:198", "down:208", "down:218"),
     None),
    # La tropa del droide del mapa 2 sobre su fondo: un enemigo y otro fondo,
    # o sea el otro camino de
    # `scene.py`. Sin esto, el único fondo que la tanda miraría sería el de
    # los Lazer Teeth.
    ("batalla-droide", "batalla-droide", 268, (), None),
    # Los dos modos de `Use Item`: la lista de ítems donde iban los enemigos, y
    # la misma lista en gris con el cursor eligiendo a quién curárselo. El
    # inventario lo pone la página de prueba —tres Potion y dos Cold Sandwich—.
    # Verificado que dan rojo corriendo dos celdas la columna de la cuenta: 142
    # pixeles.
    #
    # **Son tres derechas**: el menú tiene el orden del original —Attack /
    # <habilidad> / Defend / Use Item— y `Use Item` es la cuarta.
    ("batalla-item", "batalla-item", 288,
     ("right:198", "right:208", "right:218", "a:228"), None),
    ("batalla-item-blanco", "batalla-item", 318,
     ("right:198", "right:208", "right:218", "a:228", "a:238", "down:248"),
     None),
    # Los tres modos de las habilidades. Una derecha lleva el cursor a la
    # segunda orden, que **no dice "Tech Skill"** sino el `skill_name` del
    # actor: con Kersh primero, "AgentTrain".
    #
    #   batalla-hab         la lista de las dos de Kersh, con la descripción de
    #                       la primera arriba y el costo en SP a la derecha de
    #                       cada nombre. Es la forma de la captura del original
    #   batalla-hab-dos     la misma lista con el cursor en la segunda, o sea
    #                       con otra descripción arriba: sin esto, el renglón
    #                       de arriba podría estar escrito con la habilidad
    #                       equivocada y la golden lo defendería
    #   batalla-hab-blanco  Healing Syringe apunta al grupo —`scope` 3— así que
    #                       después de elegirla el cursor se va a los actores,
    #                       con la lista en gris. Es el camino que la de ítems
    #                       ya tenía y que una habilidad de enemigo no toca
    ("batalla-hab", "batalla", 288, ("right:198", "a:208"), None),
    ("batalla-hab-dos", "batalla", 308, ("right:198", "a:208", "right:218"),
     None),
    ("batalla-hab-blanco", "batalla", 308,
     ("right:198", "a:208", "a:218"), None),
    # Y el menú con los textos del cartucho **pasados del 255**, que es lo que
    # taro jugó: en la ROM que se juega los textos de la batalla arrancaban
    # pasado el 255, así que la tabla de un byte que los nombraba dibujaba
    # otros cuatro uno encima del otro, y con eso el menú era ilegible. El
    # relleno, en `test-special`, lo garantiza sin depender de cuántos
    # ítems y mapas lleve el de pruebas.
    #
    # El relleno son textos muertos de largo cero. Verificado en rojo con la
    # tabla de un byte puesta: 754 pixeles, 1,31%, todos en los dos renglones
    # del menú.
    ("batalla-textos-lejos", "batalla", 268, (), "test-special"),
)


@pytest.mark.parametrize(
    "nombre,caso,cuantos,toques,en", BATALLAS,
    ids=[caso[0] for caso in BATALLAS])
def test_batalla(nombre, caso, cuantos, toques, en):
    """`batalla`: la pantalla de la pelea.

    **La pelea no cuesta ningún tick**: `batalla_correr` corre su propio lazo y
    `vueltas` no avanza mientras dura, así que todo acá va en cuadros de
    hardware, los toques incluidos.

    El grupo son tres actores y no el de los demás casos: la pantalla muestra
    a los tres. La pelea es la misma todas las veces porque el azar está
    clavado en `BATALLA_SEMILLA`.
    """
    consola = consola_cruda(caso, en=en)
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.image())


# Los A que pelean hasta ganar, en cuadros de hardware porque adentro de la
# pelea no hay ticks. Sobran a propósito: si la pelea terminara antes, los que
# quedan caen en el mapa y no hacen nada; si no terminara, `Partida.correr`
# corta diciendo que la ROM no llegó al tick.
PELEAR = tuple("a:%d" % n for n in range(140, 3001, 9))


@pytest.mark.parametrize("cuadro", (30, 100))
def test_vuelta(cuadro):
    """`vuelta`: la pelea **peleada hasta el final**, y el mapa al volver.

    Es lo que `batalla` no puede mirar: aquélla abre la pantalla y nunca sale
    de ahí. La escena de la batalla sube 32 KB de VRAM, así que volver al mapa
    es reponer todo lo que se llevó puesto.

    Y es lo que lo hace barato: **la pelea no cuesta ningún tick**. Se sale
    del `OP_BATTLE` por la rama de victoria en el mismo tick en que se entra,
    o sea que el tick N es el mapa quieto, igual que si no hubiera habido
    pelea, y que la ROM dibuje eso mismo **es** la prueba.

    Es con ventana, que es donde la pelea más se lleva puesto: los tiles de la
    ventana y los dos tilemaps.
    """
    nombre = "vuelta-ventana"
    p = partida(nombre)
    p.correr(cuadro, toques_hardware=PELEAR)
    golden("%s-%d" % (nombre, cuadro), p.imagen())


# En qué paso sale el encuentro, congelado con la golden: el paso 8, contra la
# tropa 96. El avance de la
# captura de control es `(paso - 1) * 16`, o sea una celda antes.
PASO_DEL_ENCUENTRO = 8


def test_encuentro():
    """`encuentro`: el encuentro al azar del mapa 21, Rat Tracks B1.

    Se camina para arriba hasta que sale, y lo que se compara es la pantalla de
    la pelea. Es el único caso donde la pelea no la arranca un
    `EnemyEncounter` de una página sino el azar de los pasos, y el grupo con el
    que se pelea **no es el del arranque**: las páginas del mapa lo cambian
    mientras se camina.

    Va en cuadros de hardware por lo de siempre: la pantalla de batalla no
    cuenta ticks.
    """
    consola = consola_cruda("grupo-11-12-13", en="test-special")
    correr_hardware(consola, 268, sosteniendo=("up",))
    golden("encuentro", consola.image())


def test_encuentro_antes():
    """`encuentro`: el mapa **una celda antes** del paso que lo dispara.

    Es lo que fija en qué paso sale: con la pelea puesta ahí se vería la
    pantalla de batalla en vez del mapa. Sin esto, un encuentro que saliera en
    el paso 3 daría la misma comparación que el de arriba, porque la pantalla
    de batalla es la misma.

    Del arnés: **acá el reloj es de ticks otra vez**, porque el mapa todavía no
    dio paso a la pelea, y el tick sale de la cuenta del avance —`--avance` del
    corredor—, no de un número suelto.
    """
    p = partida("grupo-11-12-13", en="test-special")
    p.correr(ticks_de_avance((PASO_DEL_ENCUENTRO - 1) * 16),
             sosteniendo=("up",))
    golden("encuentro.antes", p.imagen())
