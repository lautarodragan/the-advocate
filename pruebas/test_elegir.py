"""`ShowChoice`: la ventana con opciones, el cursor y a dónde salta cada una.

El banco es el Insta-Shave del pad de Talan —mapa 7, evento 6, página 1—, que
es la única elección de la apertura y la que taro encontró muerta el
2026-09-07:

    TALAN  "It's my Insta-Shave Unit, ..."
    TALAN  "Should I use it?"
    elegir "Yes" / "No", cancelar = 2
      Yes: cuatro sonidos, un mensaje, y **switch 25 prendido**
      No:  un mensaje

El switch 25 es lo que hace comprobable la rama que corrió: no hay nada más en
la página que se pueda mirar desde afuera, y las dos ramas terminan con la
página cerrada igual.

**Esto vive acá y no en la tanda de pixeles a propósito.** Mover el cursor pide
apretar arriba y abajo, y la tanda sólo sabe apretar A; por eso la referencia
tampoco modela el movimiento —ver el comentario de `Interprete.cuadro`— y por
eso esta prueba existe. Lo que la tanda sí cubre es cómo se ve la ventana.
"""

import pytest

MAPA = 7
SHAVE_X, SHAVE_Y = 6, 5     # la celda de abajo del Insta-Shave, mirando arriba
LISTO = 24                  # el switch que enciende los eventos del pad
USADO = 25                  # el que prende la rama "Yes"


def abierta(una):
    """Si la elección está en pantalla y lista para que alguien elija.

    Los dos, y no sólo `eleg_activo`: el cuadro de texto tarda unos cuadros en
    componerse, y mientras tanto la ROM no mira el pad —igual que con un
    mensaje común—. Apretar ahí no hace nada, y una prueba que lo hiciera
    estaría midiendo su propio apuro.
    """
    return bool(una.byte("eleg_activo") and una.byte("msg_abierto"))


def pasar_mensajes(una, cuantos):
    """Cierra `cuantos` mensajes, esperando a que cada uno esté en pantalla."""
    for _ in range(cuantos):
        for _ in range(200):
            if una.byte("msg_abierto"):
                break
            una.correr(1)
        else:
            raise AssertionError("no se abrió el mensaje que se esperaba")
        una.tocar("a")
    return una


def frente_al_shave(partida):
    """Una partida parada frente al Insta-Shave, con la elección ya abierta."""
    una = partida(switch=[LISTO])
    una.ir_al_mapa(MAPA, SHAVE_X, SHAVE_Y)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    # A dispara el evento y después pasa sus dos mensajes. Se toca y se le dan
    # cuadros para que el compositor termine; en cuanto la elección está
    # abierta se corta, porque un toque más ya sería elegir.
    for _ in range(30):
        if abierta(una):
            return una
        una.tocar("a")
        for _ in range(60):
            if abierta(una):
                return una
            una.correr(1)
    raise AssertionError(
        "la elección no se abrió: el evento no disparó, o la página no compiló")


def test_la_eleccion_se_abre_con_el_cursor_en_la_primera(partida):
    una = frente_al_shave(partida)
    assert una.byte("eleg_n") == 2, "no leyó las dos opciones"
    assert una.byte("eleg_sel") == 0, \
        "el cursor no arranca en la primera opción, como `Window_Selectable`"


def test_a_elige_la_marcada(partida):
    una = frente_al_shave(partida)
    una.tocar("a")
    # La rama "Yes" dice algo antes de prender el switch, así que hay que
    # cerrarle el mensaje para que la página llegue hasta el final.
    pasar_mensajes(una, 1)
    una.correr(60)
    assert una.switch(USADO), "no corrió la rama de la opción marcada"


def test_abajo_mueve_el_cursor_y_elige_la_otra(partida):
    una = frente_al_shave(partida)
    una.tocar("down")
    assert una.byte("eleg_sel") == 1, "abajo no movió el cursor"
    una.tocar("a")
    pasar_mensajes(una, 1)
    una.correr(60)
    assert not una.switch(USADO), \
        "eligió la primera opción con el cursor en la segunda"
    assert not una.corriendo_una_pagina(), \
        "la página no terminó: el salto de la opción se pasó de largo"


def test_el_cursor_da_la_vuelta(partida):
    """Arriba desde la primera va a la última, que es `column_max` en uno."""
    una = frente_al_shave(partida)
    una.tocar("up")
    assert una.byte("eleg_sel") == 1, "arriba no dio la vuelta"
    una.tocar("down")
    assert una.byte("eleg_sel") == 0, "abajo no dio la vuelta"


def test_cancelar_elige_la_que_dice_el_dato(partida):
    """`cancel_type` es 2, o sea que B elige la opción 1: el "No".

    Es `choice_result = GetChoiceCancelType() - 1` de `Window_Message`.
    """
    una = frente_al_shave(partida)
    assert una.byte("eleg_cancel") == 2, "no leyó el `cancel_type` del dato"
    una.tocar("b")
    pasar_mensajes(una, 1)
    una.correr(60)
    assert not una.switch(USADO), "cancelar corrió la rama equivocada"
    assert not una.corriendo_una_pagina(), "la página no terminó"
