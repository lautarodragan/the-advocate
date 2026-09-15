"""Cinco casos de `rom/hitos.txt`, mudados a pytest. El piloto de los 47.

Cada uno es la misma ROM y los mismos cuadros que su receta de `just`, con dos
diferencias: contra qué se compara —la captura congelada y no la referencia de
Python— y cuántos procesos hace falta para averiguarlo. **Las recetas siguen
existiendo y en verde**: que los dos caminos den la misma imagen es la prueba de
que la mudanza es fiel, y por eso no se borra ninguna todavía.

Los cinco están elegidos para que ejerciten cosas distintas del arnés, no del
juego: las cinco direcciones con plan, el plan de un cambio de mapa, una ventana
de mensaje con un toque de A, una ruta forzada mirada en cuatro cuadros, y una
pantalla que **congela el reloj del juego**, que es lo único de los cinco que
`Partida` no sabía correr.

Lo que cada docstring de acá abajo lleva es la trampa **del arnés** que vivía en
el comentario de la receta. Las del caso —por qué este mapa, por qué este
cuadro— se quedan allá mientras la receta exista.
"""

import pytest

from tanda import cartucho, cuadros_de_hardware, golden, partida, plan

DIRECCIONES = ("none", "right", "left", "up", "down")


@pytest.mark.parametrize("direccion", DIRECCIONES)
def test_heroe_6(direccion):
    """`just heroe 6`: parado y caminando en las cuatro direcciones.

    Cuánto dura cada caminata lo dice el plan y no un número elegido a ojo: son
    ocho ticks por celda más lo que la ROM tarde en frenar contra la pared.
    El corredor le sumaba `--margen 0`, o sea nada, así que acá el plan es el
    número exacto.

    **El nombre de la captura lleva el mapa además de la dirección.** Con sólo
    la dirección, una tanda escribía `none.png` nueve veces: en serie era
    sobreescritura inofensiva, pero el PNG que uno querría mirar cuando algo
    falla ya lo pisó un mapa posterior. Con las goldens el nombre pasó a ser la
    clave, así que ahora además es obligatorio.

    Una consola nueva por dirección, como hace el corredor: arrancar de cero es
    parte de lo que se compara.
    """
    sfc, simbolos, mapas = cartucho("heroe-6", "--map-id", "6",
                                    "--descartar-eventos")
    ticks = plan("6")[direccion]
    p = partida(sfc, simbolos, mapas)
    p.correr(ticks, sosteniendo=() if direccion == "none" else (direccion,))
    golden("6-%s" % direccion, p.imagen())


def test_puerta_30_28():
    """`just puerta`: el héroe camina, pisa la puerta y aparece en el otro mapa.

    Lo que se compara es la pantalla entera después de cruzar, así que cubre de
    una vez el cambio de mapa completo —tiles, paleta, capa de encima, sprites,
    NPCs— y que el héroe haya caído en la celda que la puerta dice.

    **El plan cuenta los 70 ticks del fundido además de los ocho por celda**: en
    este caso son 142 y no 72, y la pantalla queda quieta exactamente en el 142.
    Eso es un dato en sí mismo —la carga del mapa pasa adentro del negro y no
    corre el reloj—. El `--margen 16` que la receta le pasa a la referencia es
    aire de cuando la ROM se tomaba siete cuadros que nadie contaba; al corredor
    le pasa `--margen 0`, y ése es el número que vale.

    El mapa destino tiene que estar en el cartucho: una puerta a un mapa que no
    entró no lleva a ningún lado, ni en la consola ni en la referencia.
    """
    sfc, simbolos, mapas = cartucho("puerta-30-28", "--map-id", "30",
                                    "--mapas", "28")
    p = partida(sfc, simbolos, mapas)
    p.correr(plan("puerta-30-28")["down"], sosteniendo=("down",))
    golden("puerta-30-28", p.imagen())


MENSAJE = ("SEWELL",
           "There you are, Talan. Ready for",
           "the big night?")


@pytest.mark.parametrize("cuadro", (60, 400))
def test_cerrar(cuadro):
    """`just cerrar`: la ventana de mensaje abierta, y cerrada con A.

    Dos cuadros, y el segundo es el único que ejercita el cierre: `flush_video`
    apaga el HDMA de la ventana cuando `msg_abierto` vuelve a cero.

        60    la ventana en pantalla y la página frenada: el tinte que viene
              después del mensaje todavía no se aplicó
        400   la ventana borrada y el tinte puesto, o sea que A la cerró y la
              página siguió

    Dos trampas del arnés, las dos del toque de A:

    * **el toque cae un tick antes del número**, que es `RETRASO_DE_PANTALLA`:
      la ROM dibuja lo que armó la vuelta anterior, así que para que su cuadro N
      salga cerrado el flanco tiene que caer en la vuelta N-1. `Partida.correr`
      lo resta con la misma convención que el corredor, así que la lista de
      toques es la misma en los dos lados;
    * **los cuadros se miran con margen y no en el borde.** A los 60 ticks los
      dos lados tienen el mensaje abierto hace rato y a los 400 hace rato que se
      cerró. Pegado al borde no se puede mirar: la ROM compone la ventana cuadro
      a cuadro y tarda entre nueve y diecinueve ticks según el texto.

    Y una que no se ve en el código: **el mensaje va escrito acá y no sale de
    ningún mapa.** Lo pone `--mensaje-de-prueba`, y el `--pagina-de-prueba
    0 0 0 50` es el tinte de atrás, con espera en cero: es lo que hace visible
    que la página siguió.
    """
    sfc, simbolos, mapas = cartucho(
        "cerrar", "--map-id", "7", "--mensaje-de-prueba", *MENSAJE,
        "--pagina-de-prueba", "0", "0", "0", "50")
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro, apretar_a=(200,))
    golden("cerrar-%d" % cuadro, p.imagen())


RUTA = "1 1 1 1 23 23 2 2 2 2 23 23 0 0 0 0"


@pytest.mark.parametrize("cuadro", (18, 60, 120, 400))
def test_ruta(cuadro):
    """`just ruta`: una ruta forzada sobre el héroe, en cuatro cuadros.

    La ruta la pone `--ruta-de-prueba` en una página de prueba, con
    `--frecuencia 8`: sin pasarla, la frecuencia de la página sería otra y los
    pasos caerían en otros ticks.

    La trampa del arnés es que **la caminata no se sostiene con el pad**: acá no
    se aprieta nada —`--walk none`— y el que camina es la ruta. Un pad sostenido
    sería una segunda fuente de movimiento y la referencia no modela las dos
    juntas.

    Y los cuatro cuadros salen de una sola conversión, que es lo caro; correr el
    emulador cuatro veces no lo es.
    """
    sfc, simbolos, mapas = cartucho("ruta", "--map-id", "6",
                                    "--ruta-de-prueba", *RUTA.split(),
                                    "--frecuencia", "8")
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro)
    golden("ruta-%d" % cuadro, p.imagen())


def test_batalla():
    """`just batalla`: la pantalla de la pelea contra la tropa 86.

    El raro de los cinco, y lo que lo hace raro es el reloj: **la pelea no
    cuesta ningún tick.** `batalla_correr` corre su propio lazo y `vueltas` no
    avanza mientras dura, así que esperar un tick adentro de la pelea no termina
    nunca —es el `--sin-contador` del corredor, y acá `cuadros_de_hardware`—. El
    2026-09-10 una captura sin ese cuidado se comió una hora de CPU y 42 GiB
    antes de que alguien la viera en `ps`.

    De ahí sale lo otro: los toques que pelean van en **cuadros de hardware** y
    no en ticks. Este caso no aprieta nada —la pelea se abre sola y lo que se
    mira es cómo entra— pero los ocho hermanos que sí lo hacen necesitan eso, y
    es lo que `Partida` todavía no sabe.

    El grupo son tres actores y no el de las demás recetas: la pantalla muestra
    a los tres. La pelea es la misma todas las veces porque el azar está clavado
    en `BATALLA_SEMILLA`.
    """
    sfc, simbolos, mapas = cartucho(
        "batalla", "--map-id", "6", "--con-ventana",
        "--pagina-de-prueba", "20", "0", "0", "0",
        "--batalla-de-prueba", "86",
        "--fondo-de-prueba", "ABLBackdropSJ03", grupo="11 12 13")
    p = partida(sfc, simbolos, mapas)
    cuadros_de_hardware(p, 200)
    golden("batalla", p.imagen())
