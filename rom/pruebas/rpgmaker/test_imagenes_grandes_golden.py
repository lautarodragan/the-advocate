"""Las imágenes grandes de `ShowPicture` —las que tapan la pantalla—, en BG1
pasado a modo 1 mientras se muestran, contra sus goldens. Ver
`workflow/tasks/*/las-imagenes-grandes-en-modo-1.md` y `big_picture.s`.

Las escenas que las muestran están casi todas en mapas que el cartucho no
lleva —las fotos del 212 al 216, las instrucciones del 285, el final del
309, las apariciones del 208, el 267 y el 288—, así que cada caso copia sus
comandos en una página de prueba que salta al mapa 12, igual que
`test_imagenes_golden.py`: son los de la escena, sin los mensajes de antes ni
los sonidos. La del 49, el cartel de la carrera, sí está, y corre la página
del juego.

Comparadas contra el RPG_RT de 2015 con Wine: ver la tarea.
"""

import pytest

from tanda import golden, partida, quince_bits

# Los A, uno cada nueve cuadros de hardware, para pasar los mensajes.
A_CADA = tuple("a:%d" % n for n in range(140, 6001, 9))

# `nombre` —el de su caso y el de sus goldens— y los ticks.
ESCENAS = (
    # La foto del 212, sobre el mapa; a mitad del fundido que reemplaza al
    # zoom a cero; en negro con el mensaje de la viuda encima; y el mapa de
    # vuelta, borrada.
    ("imagen-grande-foto", (5, 140, 290, 320)),
    # Las otras tres fotos, que son las que más tiles piden: cada una
    # reemplaza a la anterior sin volver al mapa.
    ("imagen-grande-fotos", (5, 65, 125)),
    # Las instrucciones del 285, más altas que la pantalla: quietas, a
    # mitad de la subida y arriba.
    ("imagen-grande-instrucciones", (5, 300, 480)),
    # El final del 309: subiendo desde negro, quieto y bajando.
    ("imagen-grande-final", (60, 190, 500)),
    # GTest4 del 208: las ondas a 6, bajando a 1, y la segunda, saturada y
    # con ondas a 8, con el mensaje ya cerrado.
    ("imagen-grande-ondas", (10, 40, 180)),
    # El 288: ShipFlash con bordes negros, que no pasa los costados, y
    # GTest4 con los suyos espejados.
    ("imagen-grande-nave", (40, 100)),
    # El montaje del 217: las cuatro fotos al 50 %, una tras otra con un
    # destello, cada una cargada con la pantalla apagada. La primera y la
    # segunda: el destello no se ve encima.
    ("imagen-grande-montaje-fotos", (3, 9)),
)


@pytest.mark.parametrize("nombre,cuadros", ESCENAS,
                         ids=[caso[0] for caso in ESCENAS])
def test_escena(nombre, cuadros):
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro, toques_hardware=A_CADA)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


def esperar(p, que, tope, apretando):
    """Corre hasta que `que(p)`, apretando A de a uno si `apretando`."""
    for _ in range(tope):
        if que(p):
            return
        if apretando:
            p.tocar_ticks("a")
            p.correr(7)
        else:
            p.correr(1)
    raise AssertionError("no pasó en %d ticks" % tope)


def test_el_cartel_de_la_carrera():
    """El 49, la primera vuelta de la carrera, con la página del juego: los
    mensajes de Talan, la pantalla a negro, `EscapeInst` hasta que se aprieta
    una tecla —su `KeyInputProc`—, y el mapa de vuelta. Hasta el 2026-10-02
    el cartel eran dos mensajes de un fork del mapa."""
    p = partida("escena-49")
    esperar(p, lambda p: p.imagen_grande(), 600, apretando=True)
    p.correr(10)
    golden("escena-49-el-cartel", p.imagen())
    esperar(p, lambda p: not p.imagen_grande(), 60, apretando=True)
    p.correr(60)
    golden("escena-49-despues", p.imagen())


def test_volver_de_la_imagen_deja_el_mapa_igual():
    """Una imagen grande puesta y borrada sobre Sorbe Village a la vista,
    con Kersh, un vecino, techos y agua: el mapa tiene que quedar **igual
    pixel por pixel**, a 15 bits, que el mismo caso sin la imagen en el mismo
    tick —`imagen-grande-vuelta-sin`—: el agua anima y el vecino camina, así
    que el mapa de antes no sirve. Lo que la capa pisó —los tiles del mapa y
    de los sprites, los dos tilemaps, el de la ventana, las paletas, el
    modo— lo repone la misma carga que la vuelta de la pelea. Sorbe es el
    reparto que más pisa: el de la capa de encima, con el tilemap del fondo
    abajo, en la VRAM de la imagen.

    Vista en rojo sacando `fill_window` de `big_back_far`, en picture.s: los
    tilemaps del fondo y de la capa de encima se quedan como los dejó la
    imagen, 9.727 pixeles.
    """
    sin = partida("imagen-grande-vuelta-sin")
    sin.correr(240)
    con = partida("imagen-grande-vuelta")
    con.correr(240)
    assert not con.imagen_grande()
    distintos = sum(1 for a, b in zip(quince_bits(sin.imagen()),
                                      quince_bits(con.imagen()))
                    if a != b)
    assert distintos == 0, (
        "el mapa volvió de la imagen con %d pixeles distintos" % distintos)
    golden("imagen-grande-vuelta", con.imagen())
