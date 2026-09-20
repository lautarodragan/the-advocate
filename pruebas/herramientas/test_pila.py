"""Cuánto baja la pila de verdad, contra lo que `PILA` le reserva.

Es la red que le faltaba al mapa de memoria. La pila arranca en `$1FFF`, crece
hacia abajo y abajo está la BSS: si una cadena de llamadas se pasa de
`bancos.PILA`, la pila **se come la BSS** y no lo ve ninguna de las otras dos
redes. Las goldens no lo distinguen —un byte pisado de `npc_buf` puede no
cambiar un pixel en el cuadro que la golden congeló— y `test_cores.py` tampoco,
porque snes9x y bsnes se corromperían igual: la comparación entre los dos daría
cero.

Así que acá no se compara nada contra nada: se **mide**. Se llena la zona de la
pila con centinelas, se corren los caminos más hondos que conocemos, y se lee el
byte más bajo que dejó de ser el suyo. Ver `consola.marcar_la_pila`.

**La marca la pone el arnés y no la ROM, y eso no pierde cobertura.** La
alternativa era marcar en el `reset`, que cuesta bytes del banco 0 —que es
justamente lo que se está tratando de liberar— y ciclos de arranque, y que
además **inicializaría memoria para todas las pruebas**, tapándole a
`test_cores.py` la basura de la WRAM justo en la zona que mira. El arnés no
tiene ninguno de esos dos costos y mide lo mismo: `marcar_la_pila` corre
**después de `retro_load_game` y antes del primer `retro_run`**, o sea con el
cartucho ya cargado y sin una sola instrucción ejecutada, así que lo que aparece
abajo de `$2000` lo escribió la ROM y el `reset` queda adentro de la medición.
Lo único que no cubre es un core que arranque ejecutando algo antes del primer
`retro_run`, que no es cómo funciona libretro.

**Qué no cubre esta prueba**, y hay que decirlo: los caminos que ninguna prueba
ejecuta. Lo que se mide es la cadena más honda de las que se corren acá, no la
más honda que existe en la ROM. Por eso el umbral no está pegado al tope.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "tools"))

from ensamblado import bancos                              # noqa: E402

from consola import hondura_de_la_pila                     # noqa: E402
from tanda import consola_cruda, correr_hardware, encender, partida  # noqa: E402

# Cuándo avisar. **La mitad de lo reservado**, y el porqué es que una prueba que
# esperara el desborde no serviría de nada: cuando la pila llega a la BSS ya
# pisó algo, y lo que se quiere es enterarse mientras queda lugar para decidir.
# Con el umbral a la mitad, el día que se ponga roja quedan todavía tantos bytes
# de pila sin usar como bytes reservados hay del otro lado del umbral.
UMBRAL = bancos.PILA // 2

# Los A que pelean hasta ganar, en cuadros de hardware porque adentro de la
# pelea no hay ticks. Es la misma lista de `test_tanda_pantallas.py`, y sobran a
# propósito: los que caen después de que la pelea terminó no hacen nada.
PELEAR = tuple("a:%d" % n for n in range(140, 3001, 9))

# Los toques que abren cada pantalla, copiados de las recetas de la tanda que
# ya las abren: ver `pruebas/rpgmaker/test_tanda_pantallas.py`.
AL_MENU = ("b:40",)
AL_EQUIPO = ("b:40", "down:52", "down:56", "a:60", "a:72", "a:92", "down:112")
A_LOS_ITEMS = ("b:40", "a:52", "down:64", "down:68")
A_LAS_RANURAS = ("down:130", "down:134")
A_LAS_RANURAS_DEL_TITULO = ("down:2", "a:6")

# La pantalla de título se come más cuadros de arranque que el mapa.
ARRANQUE_CON_TITULO = 150


def _pelea():
    """La pelea **peleada hasta el final** y la vuelta al mapa.

    Es la más honda que se conoce, y el porqué está en el mapa de memoria: la
    pelea vive en el banco 1, se entra con `jsl` y se vuelve por los puentes,
    así que cada nivel cuesta tres bytes en vez de dos.
    """
    consola = consola_cruda("vuelta-ventana", pila=True)
    return correr_hardware(consola, 400, toques_hardware=PELEAR)


def _paralelos():
    """El HQ de los Lazer Teeth, que es el mapa con más páginas paralelas.

    Cada intérprete paralelo guarda en la pila el contexto del de primer plano
    —doce bytes— así que es la otra forma que hay acá de anidar.
    """
    consola = consola_cruda("en-11", pila=True)
    return correr_hardware(consola, 240)


def _menu():
    consola = consola_cruda("grupo-11-en-73", pila=True)
    return correr_hardware(consola, 60, toques_hardware=AL_MENU)


def _equipo():
    """La pantalla del equipo, con el cursor adentro de la lista.

    Desde `3696278` el equipo vive en el banco 1 y se llama con `jsl`, igual que
    la pelea, así que es el camino que hay que mirar cuando algo más se muda.
    """
    consola = consola_cruda("equipo", pila=True)
    return correr_hardware(consola, 130, toques_hardware=AL_EQUIPO)


def _items():
    consola = consola_cruda("items", pila=True)
    return correr_hardware(consola, 80, toques_hardware=A_LOS_ITEMS)


def _tocar(consola, boton, cuadros=8):
    """Un flanco del botón y `cuadros` de hardware de espera.

    Es `test_menu.tocar` a mano, en cuadros de hardware: adentro de un menú el
    reloj del juego no corre, así que `Partida.correr` no termina nunca.
    """
    consola.apretar(boton)
    consola.correr(1)
    consola.apretar()
    consola.correr(cuadros)


def _tienda():
    """La tienda del mapa 10, que es el otro que se fue al banco 1.

    Adentro se **compra y se vende**, que es lo que baja: con la tienda recién
    abierta son 36 bytes, y metiéndose en los submenús, 41. Los ticks llegan
    hasta hablarle al vendedor y de ahí en más van cuadros de hardware, porque
    la tienda congela el reloj del juego.
    """
    una = partida("tienda", pila=True)
    una.correr(85, apretar_a=(25,))
    consola = una.consola
    _tocar(consola, "a", 40)            # "Yo. I got weapons.", y la tienda
    for _ in range(120):
        if una.menu_abierto():
            break
        consola.correr(1)
    assert una.menu_abierto(), (
        "la tienda no se abrió, así que esto mediría el mapa y no la tienda")
    # Comprar dos caños y venderlos: los dos submenús de `Scene_Shop`, cada uno
    # con su pantalla de cuántos, que es lo que llama más hondo.
    for boton in ("a", "down", "a", "right", "a", "b", "down", "a", "a", "up",
                  "a"):
        _tocar(consola, boton)
    return consola


def _ranuras():
    """La pantalla de ranuras del save point, con el cursor movido."""
    consola = consola_cruda("guardar", pila=True)
    return correr_hardware(consola, 145, toques=A_LAS_RANURAS)


def _titulo():
    """El título y su pantalla de ranuras, que es otro arranque entero."""
    consola = encender("juego", ARRANQUE_CON_TITULO, pila=True)
    return correr_hardware(consola, 20, toques=A_LAS_RANURAS_DEL_TITULO)


# Los caminos hondos, cada uno con lo que baja. Un `CallEvent` anidado **no está
# acá y no falta**: desde el 2026-09-12 se compila en línea —ver
# `_compilar_llamada` en `tools/port/eventos.py`— así que el cuerpo del llamado
# es bytecode del llamador y no cuesta un solo byte de pila.
CAMINOS = (
    ("pelea", _pelea),
    ("paralelos", _paralelos),
    ("menu", _menu),
    ("equipo", _equipo),
    ("items", _items),
    ("tienda", _tienda),
    ("ranuras", _ranuras),
    ("titulo", _titulo),
)


@pytest.mark.parametrize("nombre,camino", CAMINOS,
                         ids=[c[0] for c in CAMINOS])
def test_la_pila_no_pasa_del_umbral(nombre, camino):
    """Cada camino hondo, medido contra la mitad de lo que `PILA` reserva."""
    usado = hondura_de_la_pila(camino())
    assert usado, (
        "el camino %r dice no haber bajado la pila ni un byte, y eso no puede "
        "ser: la marca no llegó a la WRAM, o la zona que se mira no es la de "
        "la pila. Ver consola.marcar_la_pila." % nombre)
    assert usado <= UMBRAL, (
        "el camino %r bajó la pila %s bytes, y el umbral es %d —la mitad de "
        "PILA, que reserva %d—. La pila crece hacia la BSS, así que pasarse de "
        "%d la pisa sin que ninguna golden ni test_cores.py lo vean. Hay dos "
        "salidas: subir PILA en tools/ensamblado/bancos.py, que le saca esos "
        "bytes a la BSS, o mover la pila a la RAM lejana, que es lo que ya hace "
        "la pelea con su banco de datos."
        # "al menos" cuando la zona marcada quedó tocada hasta el último byte:
        # ahí la pila ya se pasó de lo reservado y lo que hay debajo es BSS, que
        # nadie marcó, así que no se puede decir cuánto más bajó.
        % (nombre, ("al menos %d" % usado) if usado >= bancos.PILA else usado,
           UMBRAL, bancos.PILA, bancos.PILA))
