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

from tanda import (cartucho, cuadros_de_hardware, golden, partida, plan,
                   ticks_de_avance)

DIRECCIONES = ("none", "right", "left", "up", "down")

# Los trece mapas de `heroe` en `rom/hitos.txt`, en el mismo orden: de mayor a
# menor, que es lo que hacía que la tanda repartida no arrancara el 52 —dos mil
# ticks por dirección— cuando los demás trabajadores ya habían terminado. Con
# pytest en serie el orden no cambia nada, y se deja igual para poder leer una
# lista contra la otra mientras las dos existan.
MAPAS_DE_HEROE = (52, 11, 20, 8, 17, 21, 32, 6, 1, 73, 18, 119, 348)


@pytest.mark.parametrize("mapa", MAPAS_DE_HEROE)
@pytest.mark.parametrize("direccion", DIRECCIONES)
def test_heroe(mapa, direccion):
    """`just heroe <mapa>`: parado y caminando en las cuatro direcciones.

    El 21 es Rat Tracks B1, el que destapó la página automática vacía: sus dos
    —el idioma con el que RM2k desactiva un evento— dejaban el mapa congelado
    para siempre. Antes de ese arreglo el caso tardaba catorce minutos, porque
    la referencia se comía sus 100.000 ticks de `correr_automaticos`; acá no
    hay referencia que correr y lo que queda es lo que la ROM tarde.

    Cuánto dura cada caminata lo dice el plan y no un número elegido a ojo: son
    ocho ticks por celda más lo que la ROM tarde en frenar contra la pared.
    El corredor le sumaba `--margen 0`, o sea nada, así que acá el plan es el
    número exacto.

    **El nombre de la captura lleva el mapa además de la dirección.** Con sólo
    la dirección, cada mapa de la tanda escribía su `none.png` encima del
    anterior: en serie era sobreescritura inofensiva, pero el PNG que uno
    querría mirar cuando algo falla ya lo pisó un mapa posterior. Con las
    goldens el nombre pasó a ser **la clave**, así que ahora además es
    obligatorio.

    Una consola nueva por dirección, como hace el corredor: arrancar de cero es
    parte de lo que se compara.
    """
    sfc, simbolos, mapas = cartucho("heroe-%d" % mapa, "--map-id", mapa,
                                    "--descartar-eventos")
    ticks = plan(str(mapa))[direccion]
    p = partida(sfc, simbolos, mapas)
    p.correr(ticks, sosteniendo=() if direccion == "none" else (direccion,))
    golden("%d-%s" % (mapa, direccion), p.imagen())


def test_puerta_30_28():
    """`just puerta`: el héroe camina, pisa la puerta y aparece en el otro mapa.

    Lo que se compara es la pantalla entera después de cruzar, así que cubre de
    una vez el cambio de mapa completo —tiles, paleta, capa de encima, sprites,
    NPCs— y que el héroe haya caído en la celda que la puerta dice.

    **El plan cuenta el fundido de la puerta además de los ocho ticks por
    celda**, así que es bastante más que celdas por ocho, y la pantalla se queda
    quieta antes de que termine: los últimos ticks son el fundido ya resuelto.
    Eso es un dato en sí mismo —la carga del mapa pasa adentro del negro y no
    corre el reloj, y la ROM pierde cuadros de hardware ahí sin perder un solo
    tick—. El `--margen 16` que la receta le pasa a la referencia es aire de
    cuando la ROM se tomaba cuadros que nadie contaba; al corredor le pasa
    `--margen 0`, y ése es el que vale.

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

    Y una que es del mapa pero se paga en el arnés: **el mapa 6 es mudo**, y eso
    es lo que hace usable el desfasaje de arranque. La ROM no empieza a
    interpretar en el cuadro 0 y la referencia no modela nada de eso; con música
    el desfasaje cambia y los cuadros del medio se corren todos juntos.

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


@pytest.mark.parametrize("direccion", ("none", "down"))
def test_varios(direccion):
    """`just varios`: el mapa 18 en un cartucho donde **no** es el primero.

    Lo que prueba no es que el mapa se vea bien —eso ya lo cubre `heroe`— sino
    que se vea bien cuando su registro no está al principio de la tabla: con el
    índice 0 el desplazamiento es cero y cualquier cuenta mal hecha da el
    resultado correcto por casualidad.

    Del arnés hay una sola cosa, y es que **el plan es por dirección y no por
    mapa**: la receta llamaba a `walk` una vez por dirección y cada llamada
    escribía su propio archivo, así que acá los planes son
    `plan-varios-18-none` y `plan-varios-18-down` y no un `plan-18` con las
    cinco. Se dejan como están: son los congelados, y rearmarlos en uno sería
    regenerar una golden para ahorrar una línea.
    """
    sfc, simbolos, mapas = cartucho("varios-18", "--map-id", "18",
                                    "--mapas", "7", "19", "--inicial", "2")
    nombre = "varios-18-%s" % direccion
    p = partida(sfc, simbolos, mapas)
    p.correr(plan(nombre)[direccion],
             sosteniendo=() if direccion == "none" else (direccion,))
    golden(nombre, p.imagen())


# Mapa, celda y nombre de la captura, de `parado` en `rom/hitos.txt`.
PARADOS = ((1, 75, 88, "borde"),
           (1, 75, 90, "medias"),
           (1, 66, 40, "tapado"),
           (261, 59, 2, "paquete"))


@pytest.mark.parametrize("mapa,tx,ty,nombre", PARADOS)
def test_parado(mapa, tx, ty, nombre):
    """`just parado`: el héroe plantado en una celda elegida, sin caminar.

    Llegar a un lugar puntual caminando depende de cuánto se mantenga la
    cruceta; acá la celda se fija con `--inicio` y la captura no se negocia.

    Del arnés: **los 240 son ticks y no cuadros de hardware**. La receta los
    pedía por `shot`, que le pasa `--teclas` vacío al corredor, y ése es el
    camino que cuenta `vueltas` igual que los demás. En un mapa que no pierde
    cuadros da lo mismo; en uno que sí, no.
    """
    sfc, simbolos, mapas = cartucho("parado-%d-%d-%d" % (mapa, tx, ty),
                                    "--map-id", mapa, "--inicio", tx, ty)
    p = partida(sfc, simbolos, mapas)
    p.correr(240)
    golden(nombre, p.imagen())


def test_encima():
    """`just encima`: el héroe en prioridad 2 de objeto, partido por la capa.

    Es la única manera de ejercitar esa prioridad —la de los eventos "above",
    que en el orden del modo 3 queda por encima de BG2—: el juego tiene un solo
    evento así, el Package del mapa 261, y la capa de encima de ese mapa no
    llega a tocarlo, así que con datos de verdad las prioridades 1 y 2 dan la
    misma pantalla.

    La celda se eligió midiendo: en (66,40) del mapa 1 la capa de encima parte
    al sprite en dos, así que la silueta tiene que coincidir de los dos lados.
    """
    sfc, simbolos, mapas = cartucho("encima", "--map-id", "1",
                                    "--inicio", "66", "40", "--heroe-encima")
    p = partida(sfc, simbolos, mapas)
    p.correr(240)
    golden("encima", p.imagen())


@pytest.mark.parametrize("otros,nombre", ((("1",), "evento"),
                                          (("7", "19", "1"), "tabla")))
def test_evento(otros, nombre):
    """`just evento`: la cinemática del mapa 4 vista en su cuadro asentado.

    El mapa 4 es una habitación vacía y negra cuyo único trabajo es prender dos
    switches, teñir la pantalla y teletransportar: es la página que abre A
    Blurred Line, y lo que se ve al arrancar es el mapa destino ya teñido sin
    haber tocado una tecla.

    Los dos mapas tienen que estar en la ROM: un teletransporte a un mapa que
    no entró no compila, y entonces la página no se emite y el evento no hace
    nada. Con el mapa 4 solo la pantalla se queda en negro, y eso es correcto.

    El segundo caso —`tabla`— es el mismo con el destino **último** en la lista
    de mapas, o sea con el teletransporte resolviendo un índice que no es 0
    ni 1.

    **La receta se queda aunque el caso esté acá**: `bsnes` la llama.
    """
    sfc, simbolos, mapas = cartucho("evento-4-%s" % "-".join(otros),
                                    "--map-id", "4", "--mapas", *otros)
    p = partida(sfc, simbolos, mapas)
    p.correr(240)
    golden(nombre, p.imagen())


@pytest.mark.parametrize("mapa,arranca,nombre", ((121, "10", "grupo-121"),
                                                 (74, "21", "ruta-74")))
def test_pagina(mapa, arranca, nombre):
    """`just pagina`: una página automática del juego, con el grupo que pide.

    El grupo es parte del caso y no decoración, y por eso va explícito:

        121  `ChangePartyMembers` saca al actor 10 y agrega al 14 y al 28. En
             RM2k el gráfico del héroe es el del primero del grupo, así que
             arrancando con [10] el héroe pasa de `DummyHero` —una celda vacía
             que no se dibuja— a Talan. Con [11] el 10 no está, sacarlo no hace
             nada, y la prueba no probaría nada.
        74   Una ruta forzada de `MoveEvent` sobre el héroe: `face_up` y una
             espera. Su página pide al actor 21 en el grupo, así que sin
             arrancar con él no corre. Es la única página del juego que compila
             y ejercita una ruta.

    Del arnés: el grupo es el único argumento del conversor que `cartucho` no
    toma como flag suelto, porque hay que pasárselo también a la ROM.
    """
    sfc, simbolos, mapas = cartucho(nombre, "--map-id", mapa, grupo=arranca)
    p = partida(sfc, simbolos, mapas)
    p.correr(240)
    golden(nombre, p.imagen())


# Mapa, dirección y los avances en pixeles, de `caminando` en `rom/hitos.txt`.
CAMINANDO = ((73, "right", (40, 60, 80)),
             (6, "down", (40, 60, 80)),
             (5, "left", (40, 46, 48, 50)),
             (3, "down", (54, 56, 58, 60)))


@pytest.mark.parametrize("mapa,direccion,avances", CAMINANDO)
def test_caminando(mapa, direccion, avances):
    """`just caminando`: el héroe a mitad de camino, con N pixeles andados.

    Es el único caso que mira el movimiento en sí. Todos los demás comparan el
    cuadro final, y ahí el héroe choca contra una pared: `moving` vale cero, la
    pose es siempre la parada y las tres columnas del ciclo no las verifica
    nadie. Acá además se ejercitan la velocidad y la cámara a mitad del scroll.

    Y por lo mismo es donde entra la animación del ChipSet: un avance de N px
    es el tick N/2 + 1, así que se puede pedir el cuadro exacto en que el agua
    o los tiles animados cambian de dibujo. Hacen falta los dos mapas: el del
    agua no tiene tiles animados y el de los tiles animados no aporta agua.

    Del arnés: **el avance no es un número de ticks sino una cuenta**, la de
    `ticks_de_avance`, y errarle por uno mueve media pantalla. Los avances de
    un mismo mapa salen de una sola conversión, que es lo caro.

    **La receta se queda aunque el caso esté acá**: `bsnes` la llama.
    """
    sfc, simbolos, mapas = cartucho("caminando-%d" % mapa, "--map-id", mapa)
    for pixeles in avances:
        p = partida(sfc, simbolos, mapas)
        p.correr(ticks_de_avance(pixeles), sosteniendo=(direccion,))
        golden("%d-%s-%d" % (mapa, direccion, pixeles), p.imagen())
