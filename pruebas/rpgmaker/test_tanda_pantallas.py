"""Las pantallas que **congelan el reloj del juego**: menús, batalla y título.

Lo que junta a este archivo no es de qué habla cada caso sino cómo hay que
correrlo. En todos los demás, un tick de la ROM es una vuelta del lazo principal
y `vueltas` lo cuenta; acá no: la pantalla de batalla corre su propio lazo, y el
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

Ninguna de las recetas de este archivo existe ya: el nombre que abre cada
docstring es el del caso, que es también el de su golden.
"""

import pytest

from tanda import (consola_cruda, correr_hardware,
                   encender, golden, partida, ticks_de_avance)

@pytest.mark.parametrize("cuadro", (60, 400))
def test_espera(cuadro):
    """`espera`: que una espera espere de verdad, con una página inventada.

    El intérprete corre tick a tick desde que dejó de colapsar el tiempo, pero
    **ninguna página del juego que compile tiene una espera**, así que ese
    camino —el corazón del cambio— no lo ejercitaba nada. Lo sintético es la
    entrada y no la comparación.

    Se mira antes y después, no el tick exacto en que cambia: el arranque de la
    ROM incluye la subida al SPC700 y la referencia no modelaba eso, así que el
    borde caía en cuadros distintos de cada lado. Con margen a los dos lados la
    prueba sigue siendo filosa: si la espera no esperara, el tick de antes ya
    estaría teñido.
    """
    p = partida("espera")
    p.correr(cuadro)
    golden("espera-%d" % cuadro, p.imagen())


# El save point abre su pantalla diez cuadros después de que la espera de la
# página termina.
ABRE_LA_DE_RANURAS = 130


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("guardar", 130, ()),
    # El cursor dos ranuras más abajo, que es lo único que ejercita el DMA del
    # otro tilemap; y de paso cobra que sostener abajo no baje un renglón por
    # cuadro, porque estos menús miran **flancos**.
    ("guardar-2", 140, ("down:130", "down:134")),
))
def test_guardar_pantalla(nombre, cuantos, toques):
    """`guardar`: la pantalla de ranuras abierta desde el save point.

    Las cuatro ranuras salen vacías porque la SRAM del emulador arranca virgen.
    La variante "llena" no la cubre esta tanda —haría falta precargar un
    `.srm`— y la cubren las pruebas de estado, que sí pueden guardar antes de
    mirar.

    Del arnés: los toques van con el nombre `toques` y no `toques_hardware`
    porque así los pasaba la receta, y eso les corre el cuadro en uno. Ver la
    cabecera de este archivo.
    """
    consola = consola_cruda("guardar")
    correr_hardware(consola, cuantos, toques=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (122, 200))
@pytest.mark.parametrize("nombre,toques", (
    # Con B se sale sin guardar y con A se guarda: de vuelta en el mapa las dos
    # tienen que dar la misma pantalla, porque **guardar no cambia un pixel**.
    # Por eso los dos comparten golden en la receta y acá comparten tabla.
    ("guardar-vuelve", ("down:130", "down:134", "b:138")),
    ("guardar-elige", ("down:130", "a:134")),
))
def test_guardar_vuelve(nombre, toques, cuadro):
    """`guardar`: el mapa de vuelta, después de cerrar la de ranuras.

    Acá el reloj del juego vuelve a correr, así que los ticks son ticks; los
    toques siguen en cuadros de hardware porque caen adentro de la pantalla,
    donde no hay ticks en los que caer.
    """
    p = partida("guardar")
    p.correr(cuadro, toques_hardware=toques)
    golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("menu", 52, ("b:40",)),
    ("menu-2", 62, ("b:40", "down:52", "down:56")),
))
def test_menu(nombre, cuantos, toques):
    """`menu`: el menú de pausa, abierto con B desde el mapa."""
    consola = consola_cruda("grupo-11-en-73")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (50, 120))
def test_menu_vuelve(cuadro):
    """`menu`: el mapa de vuelta al cerrar el menú de pausa."""
    p = partida("grupo-11-en-73")
    p.correr(cuadro, toques_hardware=("b:40", "b:52"))
    golden("menu-vuelve-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("items", 64, ("b:40", "a:52")),
    ("items-2", 74, ("b:40", "a:52", "down:64", "down:68")),
))
def test_items(nombre, cuantos, toques):
    """`items`: la lista de ítems del menú de pausa.

    Tres ítems distintos y uno de ellos repetido trece veces, que es lo que
    ejercita la columna de la cuenta además de la de los nombres.
    """
    consola = consola_cruda("items")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (60, 120))
def test_items_vuelve(cuadro):
    """`items`: el mapa de vuelta al cerrar la lista de ítems."""
    p = partida("items")
    p.correr(cuadro, toques_hardware=("b:40", "a:52", "down:64", "down:68",
                                      "a:74"))
    golden("items-vuelve-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("equipo", 84, ("b:40", "down:52", "down:56", "a:60", "a:72")),
    # La lista de lo que se puede equipar en esa ranura, que es el otro camino:
    # la pantalla del equipo con el cursor adentro de la lista.
    ("equipo-lista", 124, ("b:40", "down:52", "down:56", "a:60", "a:72",
                           "a:92", "down:112")),
))
def test_equipo(nombre, cuantos, toques):
    """`equipo`: la pantalla del equipo de un actor."""
    consola = consola_cruda("equipo")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (60, 120))
def test_equipo_vuelve(cuadro):
    """`equipo`: el mapa de vuelta, con tres B para salir de los tres
    niveles de menú."""
    p = partida("equipo")
    p.correr(cuadro, toques_hardware=("b:40", "down:52", "down:56", "a:60",
                                      "a:72", "a:92", "b:112", "b:132",
                                      "b:152"))
    golden("equipo-vuelve-%d" % cuadro, p.imagen())


# La pantalla de batalla: nombre, la página de prueba —la pelea, con su
# grupo de tres y su inventario—, cuántos cuadros de hardware, los toques que
# pelean y el cartucho, si no es el de pruebas.
BATALLAS = (
    ("batalla", "batalla", 200, (), None),
    ("batalla-blanco", "batalla", 200, ("a:130", "down:140", "down:150"),
     None),
    # La tropa del droide del mapa 2 sobre su fondo, que es la única pelea que
    # el jugador alcanza hoy: un enemigo y otro fondo, o sea el otro camino de
    # `escena.py`. Sin esto, el único fondo que la tanda miraría sería el de
    # los Lazer Teeth.
    ("batalla-droide", "batalla-droide", 200, (), None),
    # La misma tropa 86 en un cartucho que además lleva el mapa 2, o sea con
    # **dos** tropas y dos fondos, para que `tropa_id` y `escena_tropa_fondo` se
    # indexaran de verdad en vez de acertar siempre con el primer renglón.
    # Desde el 9f el cartucho de pruebas lleva todas las tropas y eso lo
    # cumplen todas; se deja por la golden.
    ("batalla-segunda", "batalla", 200, (), None),
    # Los dos modos de `Use Item`: la lista de ítems donde iban los enemigos, y
    # la misma lista en gris con el cursor eligiendo a quién curárselo. El
    # inventario lo pone la página de prueba —tres Potion y dos Cold Sandwich—.
    # Verificado que dan rojo corriendo dos celdas la columna de la cuenta sólo
    # del lado de la ROM: 142 pixeles.
    #
    # **Son tres derechas y no dos desde el 2026-09-13**: el menú pasó a tener
    # el orden del original —Attack / <habilidad> / Defend / Use Item— y
    # `Use Item` quedó cuarta.
    ("batalla-item", "batalla-item", 220,
     ("right:130", "right:140", "right:150", "a:160"), None),
    ("batalla-item-blanco", "batalla-item", 250,
     ("right:130", "right:140", "right:150", "a:160", "a:170", "down:180"),
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
    #                       equivocada y los dos lados darían igual igual
    #   batalla-hab-blanco  Healing Syringe apunta al grupo —`scope` 3— así que
    #                       después de elegirla el cursor se va a los actores,
    #                       con la lista en gris. Es el camino que la de ítems
    #                       ya tenía y que una habilidad de enemigo no toca
    ("batalla-hab", "batalla", 220, ("right:130", "a:140"), None),
    ("batalla-hab-dos", "batalla", 240, ("right:130", "a:140", "right:150"),
     None),
    ("batalla-hab-blanco", "batalla", 240,
     ("right:130", "a:140", "a:150"), None),
    # Y el menú con los textos del cartucho **pasados del 255**, que es lo que
    # taro jugó: `abl` lleva 57 ítems y los textos de la batalla
    # arrancan en el 273, así que la tabla de un byte que los nombraba dibujaba
    # otros cuatro uno encima del otro, y con eso el menú era ilegible. El
    # relleno, en el cartucho chico, lo garantiza sin depender de cuántos
    # ítems y mapas lleve el de pruebas.
    #
    # El relleno son textos muertos de largo cero. Verificado en rojo con la
    # tabla de un byte puesta: 754 pixeles, 1,31%, todos en los dos renglones
    # del menú.
    ("batalla-textos-lejos", "batalla", 200, (), "chico"),
)


@pytest.mark.parametrize(
    "nombre,caso,cuantos,toques,en", BATALLAS,
    ids=[caso[0] for caso in BATALLAS])
def test_batalla(nombre, caso, cuantos, toques, en):
    """`batalla`: la pantalla de la pelea.

    **La pelea no cuesta ningún tick**: `batalla_correr` corre su propio lazo y
    `vueltas` no avanza mientras dura, así que todo acá va en cuadros de
    hardware, los toques incluidos.

    El grupo son tres actores y no el de las demás recetas: la pantalla muestra
    a los tres. La pelea es la misma todas las veces porque el azar está
    clavado en `BATALLA_SEMILLA`.
    """
    consola = consola_cruda(caso, en=en)
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


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

    Y es lo que lo hace barato: **la pelea no cuesta ningún tick**. La
    referencia salía del `OP_BATTLE` por la rama de victoria en el mismo tick
    en que entraba, o sea que el tick N es el mapa quieto, igual que si no
    hubiera habido pelea, y que la ROM dibuje eso mismo **es** la prueba.

    Es con ventana, que es donde la pelea más se lleva puesto: los tiles de la
    ventana y los dos tilemaps. Hasta el 2026-09-17 había un segundo caso sin
    ventana, con otro reparto de VRAM; la ventana pasó a ser obligatoria.
    """
    nombre = "vuelta-ventana"
    p = partida(nombre)
    p.correr(cuadro, toques_hardware=PELEAR)
    golden("%s-%d" % (nombre, cuadro), p.imagen())


# En qué paso sale el encuentro, que es lo que la referencia contestaba y ahora
# está congelado con la golden: el paso 8, contra la tropa 96. El avance de la
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
    consola = consola_cruda("grupo-11-12-13", en="chico")
    correr_hardware(consola, 200, sosteniendo=("up",))
    golden("encuentro", consola.imagen())


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
    p = partida("grupo-11-12-13", en="chico")
    p.correr(ticks_de_avance((PASO_DEL_ENCUENTRO - 1) * 16),
             sosteniendo=("up",))
    golden("encuentro.antes", p.imagen())


# La pantalla de título se come cuadros de arranque que el mapa no: 150 en vez
# de los 115 de todo lo demás.
ARRANQUE_CON_TITULO = 150

@pytest.mark.parametrize("nombre,sosteniendo,toques", (
    ("titulo", (), ()),
    # El cursor una opción más abajo. No es un adorno: es lo único que
    # ejercita el DMA que sube el otro tilemap, que es como está hecho el
    # cursor. Y de paso cobra que **sostener abajo no baje un renglón por
    # cuadro** —se corre con el botón apretado veinte cuadros y el cursor tiene
    # que haberse movido una sola vez—.
    ("titulo-2", ("down",), ()),
    # La pantalla de ranuras, a la que se llega bajando el cursor a "Resume the
    # Story" y apretando A. Van con toques y no sostenidos porque el menú mira
    # **flancos**.
    ("titulo-ranuras", (), ("down:2", "a:6")),
    ("titulo-ranuras2", (), ("down:2", "a:6", "down:10", "down:14")),
))
def test_titulo(nombre, sosteniendo, toques):
    """`titulo`: la pantalla de título, contra la imagen del LDB.

    Es el caso que **más necesita** el reloj de cuadros: ahí `vueltas` no
    avanza, porque el título no es el juego —una ROM con título corre el mapa
    igual que una sin él—, así que esperar un tick no termina jamás.

    Las cuatro ranuras salen vacías porque la SRAM del emulador arranca virgen.
    """
    consola = encender("juego", ARRANQUE_CON_TITULO)
    correr_hardware(consola, 20, toques=toques, sosteniendo=sosteniendo)
    golden(nombre, consola.imagen())


# `test_titulo_es_el_mismo_juego` estuvo acá hasta el 2026-09-20 y se fue con
# el cartucho `titulo`, que existía para ser su otra mitad: comparaba la ROM
# con título contra la misma sin él, 300 ticks adentro del mapa, y era el único
# caso de la tanda que comparaba **una ROM contra otra**.
#
# Se fue por dos razones medidas, y la primera sola ya alcanzaba. Sus dos
# goldens —`titulo-juego` y `titulo-juego-sin`— eran **la pantalla entera en
# negro**: a los 300 ticks con `start` sostenido no se ve nada, así que la
# comparación que daba nombre al caso comparaba negro contra negro. Y con el
# título mudado al cartucho del juego ya no hay dos ROMs que se distingan sólo
# por la pantalla: la que la lleva arranca en el 4 y con cronómetro.
#
# Lo que la pregunta buscaba —¿la ROM con título dibuja lo mismo adentro del
# mapa?— lo cobran ahora las diecisiete goldens de `cinematica`, `apertura` y
# `cartel` de `pruebas/abl/test_tanda_escenas.py`: se congelaron cuando el
# cartucho no llevaba título y hoy se sacan a través de él, byte por byte
# iguales, en imágenes que no son negras.
