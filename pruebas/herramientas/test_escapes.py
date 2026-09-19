"""Los dos escapes de texto de RM2k, del lado de Python: `\\|` y `\\^`.

No corre ninguna ROM, y por eso está acá y no en la tanda: lo que mira es el
**formato**, o sea el byte de cabecera del cuadro que el intérprete de la ROM y
el de la referencia leen con las mismas máscaras. Que el mensaje se pause y se
cierre solo en el mismo cuadro de los dos lados lo cobran `autocierre` y
`autocierre-3` en `pruebas/test_tanda*.py`, que comparan pixeles.

Lo que sí cubre y ningún cuadro comparado podría cubrir es la deduplicación:
dos cuadros con el mismo texto y distinta cola compartiendo desplazamiento
darían **cero** en la comparación, porque la ROM y la referencia leerían los
mismos bytes equivocados. Es exactamente la forma de falla que AGENTS.md nombra.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))

import eventos                                          # noqa: E402
import ventana                                          # noqa: E402


def test_la_cola_sale_del_texto_y_se_cuenta():
    """`\\|\\^` es lo que usa el juego 25 veces: una pausa y autocierre."""
    lineas, pausas, autocierre = eventos.cola_de_escapes(
        ["HELP!!", "That bandit... has a bow...\\|\\^"])
    assert lineas == ("HELP!!", "That bandit... has a bow...")
    assert (pausas, autocierre) == (1, True)


def test_tres_pausas_seguidas():
    """El `< Kiss >` del mapa 108, que es el máximo del juego."""
    _lineas, pausas, autocierre = eventos.cola_de_escapes(
        ["                  < Kiss >\\|\\|\\|\\^"])
    assert (pausas, autocierre) == (3, True)


def test_la_cola_con_espacios_entre_medio():
    """El `RunDirectorScene` del mapa 98 es el único que escribe `\\| \\| \\| \\^`.

    Los espacios de la cola se van con ella: un espacio al final de un renglón
    no dibuja un pixel, así que sacarlo da la misma pantalla de los dos lados.
    Los de antes del primer escape se quedan, porque ésos son texto.
    """
    lineas, pausas, autocierre = eventos.cola_de_escapes(
        ["  ya vuelvo \\| \\| \\| \\^"])
    assert lineas == ("  ya vuelvo ",)
    assert (pausas, autocierre) == (3, True)


def test_un_escape_que_no_conocemos_no_compila():
    """Los tres `\\V` de los eventos comunes: el valor de una variable metido en
    el texto. Siguen sin hacerse, y la página que los use tiene que seguir sin
    compilar en vez de dibujarlos como dos letras."""
    with pytest.raises(eventos.NoSePuede):
        eventos.cola_de_escapes(["tenés \\V[12] créditos"])


def test_un_escape_en_el_medio_tampoco():
    """Con la ventana dibujándose de golpe, una pausa a mitad del texto no se
    puede modelar sin inventar cuánto texto había dibujado. En los 328 mapas no
    hay ninguno: los 40 cuadros con escapes los traen como cola."""
    with pytest.raises(eventos.NoSePuede):
        eventos.cola_de_escapes(["uno\\|dos"])


def test_la_cabecera_lleva_los_renglones_el_cierre_y_las_pausas():
    """El byte que lee `msg_empezar`, con las mismas máscaras que la ROM."""
    cabecera = eventos.mensaje_bytes(("a", "b"), pausas=3, autocierre=True)[0]
    assert cabecera & eventos.CABECERA_LINEAS == 2
    assert cabecera & eventos.CABECERA_AUTOCIERRE
    assert cabecera >> 4 == 3


def test_dos_cuadros_con_el_mismo_texto_y_distinta_cola_no_se_comparten():
    """La trampa que daría cero: uno espera al jugador y el otro no."""
    mensajes = eventos.Mensajes()
    pelado = mensajes.agregar(["Ready for the big night?"])
    con_cola = mensajes.agregar(["Ready for the big night?\\|\\^"])
    assert pelado != con_cola, \
        "el mismo desplazamiento para dos cuadros que duran distinto"
    assert mensajes.lineas(pelado) == mensajes.lineas(con_cola), \
        "el texto es el mismo: lo único que cambia es la cola"
    assert mensajes.cola(pelado) == (0, False)
    assert mensajes.cola(con_cola) == (1, True)
    # Y el mismo cuadro dos veces sigue costando un solo desplazamiento.
    assert mensajes.agregar(["Ready for the big night?\\|\\^"]) == con_cola


def test_la_cola_se_saca_antes_de_recortar_el_renglon():
    """Al revés, un renglón lleno se comería su propio `\\|\\^` y el cuadro
    quedaría esperando un A que RM2k no pide."""
    mensajes = eventos.Mensajes()
    largo = "x" * ventana.COLUMNAS
    donde = mensajes.agregar([largo + "\\|\\^"])
    assert mensajes.lineas(donde) == (largo,)
    assert mensajes.cola(donde) == (1, True)
