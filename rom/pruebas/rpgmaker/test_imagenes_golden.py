"""Las imágenes de `ShowPicture` en el plano de los sprites, contra sus
goldens: los comandos y sus opciones, con páginas de prueba, y las escenas
del juego que se dibujan desde que cada mapa lleva las suyas.

Las páginas de prueba saltan todas al mapa 12, Trash Dump 004, que no tiene
ninguna página automática que les gane la pantalla —el 4, donde arranca la
ROM, corre la apertura encima— y tiene lugar en sus sprites para las imágenes
de todas: el conversor las pone en el banco del mapa donde corre cada página,
y ahí se quedan. Usan las imágenes del juego: `Fortitude`, con su color
transparente, y `ABLrec`, al 50 %.

Las escenas se llaman con `CallEvent` sobre la página del mapa, que el
compilador pega en la página de prueba con el contexto de ese mapa: es la
misma página que corre en el juego, sin tener que jugar hasta ella. Las
comparé contra el RPG_RT con Wine: ver la tarea
`workflow/tasks/*/varias-imagenes-en-sprites.md`.
"""

import pytest

from tanda import correr_hardware, golden, partida

# `nombre` —el de su caso en `pruebas/casos/` y el de sus goldens— y los ticks.
COMANDOS = (
    # Dos imágenes a la vez, en dos números: el rótulo con su color
    # transparente y "REC" al 50 % de zoom. A los 90 el rótulo ya se borró y
    # "REC" sigue. Visto en rojo con las dos ranuras en la paleta 7 —`eor
    # #$07` cambiado por `lda #$07` en `pic_draw`—: 325 pixeles.
    ("imagen-dos", (10, 90)),
    # El tono y la transparencia de `MovePicture`: aparece desde 100 de
    # transparencia —a los 5 no se ve—, va al tono (200, 50, 50) en dos
    # segundos, y la pantalla se tiñe detrás sin teñirla. Visto en rojo sin
    # guardar la transparencia de la rampa en `pic_tick`: a los 40 no se ve,
    # 674 pixeles.
    ("imagen-tono", (5, 40, 140)),
    # Por variables: el centro sale de la 17 y la 18, y la segunda vez queda
    # medio afuera por la izquierda —la x es negativa, y la cuenta de cuatro
    # quintos redondea para abajo—. Visto en rojo leyendo la variable de la x
    # también para la y: 1172 pixeles.
    ("imagen-variable", (5, 30)),
    # Con el mapa: la imagen se queda en su lugar del mapa mientras la cámara
    # se corre a la derecha y abajo. Visto en rojo dibujándola como si fuera
    # de la pantalla —el `beq still` de `pic_draw` cambiado por `bra`—: 349
    # pixeles.
    ("imagen-mapa", (5, 120)),
)


@pytest.mark.parametrize("nombre,cuadros", COMANDOS,
                         ids=[caso[0] for caso in COMANDOS])
def test_comando(nombre, cuadros):
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# Los A que pelean hasta ganar, en cuadros de hardware: ver `test_vuelta` en
# test_batalla_golden.py.
PELEAR = tuple("a:%d" % n for n in range(140, 3001, 9))


def test_vuelta_de_la_pelea():
    """`imagen-pelea`: las dos imágenes siguen después de una pelea, con su
    tono. La pelea sube su escena a la VRAM y sus paletas a la CGRAM; los
    tiles de las imágenes vuelven con el banco del mapa, y las paletas con
    `scene_cgram_restore`, desde `cgram_shadow`, donde las deja
    `pic_palette`. **No cobra esa restauración**: la tropa 82 usa menos
    paletas de las que harían falta para llegar a la 6 y la 7 —cortarla antes
    de ésas, medido, deja la prueba en verde—. Lo que cobra es que las
    imágenes vuelvan, con sus tiles y su tono."""
    p = partida("imagen-pelea")
    p.correr(20, toques_hardware=PELEAR)
    golden("imagen-pelea-20", p.imagen())


def test_vuelta_del_menu():
    """`imagen-menu`: el menú de pausa tapa la imagen —es otra escena, como en
    RM2k— y al cerrarlo vuelve como estaba."""
    p = partida("imagen-menu")
    p.correr(10)
    correr_hardware(p.consola, 30, toques_hardware=("b:2",))
    p.consola.hold()
    golden("imagen-menu-abierto", p.imagen())
    correr_hardware(p.consola, 40, toques_hardware=("b:2",))
    golden("imagen-menu-vuelve", p.imagen())


# Las escenas: nombre, los ticks y los A, uno cada nueve cuadros de hardware
# para pasar los mensajes y pelear.
A_CADA = tuple("a:%d" % n for n in range(140, 6001, 9))
ESCENAS = (
    # El 81, la casa de Vago: "Meanwhile, in Lashe City", que entra desde el
    # negro con una rampa de tono, se queda y se va, sobre la pantalla teñida
    # de negro. Hasta hoy un fork del mapa lo cambiaba por un mensaje.
    ("escena-81", (1000, 1100, 1300)),
    # El 95, Into The Machine: el rótulo de la Fortitude, con su color
    # transparente, arriba del contador.
    ("escena-95", (550,)),
    # El 311, el claro: la sombra del hovertram, pegada al mapa y al 55 %, que
    # aparece desde 100 de transparencia y se queda en 50. Se dibuja opaca:
    # ver `PIC_HIDDEN` en picture_far.s.
    ("escena-311", (250,)),
)


@pytest.mark.parametrize("nombre,cuadros", ESCENAS,
                         ids=[caso[0] for caso in ESCENAS])
def test_escena(nombre, cuadros):
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro, toques_hardware=A_CADA)
        golden("%s-%d" % (nombre, cuadro), p.imagen())
