"""Las escenas del juego: las familias `escena` y `cinematica` de la tanda.

Una escena es el héroe plantado en una celda, una ruta forzada que lo lleva a
pisar o a encarar algo, y la página del juego que eso dispara, mirada en varios
ticks. Es la familia más usada de la tanda.

Dos cosas del arnés:

* **Los toques de A van en ticks y los de `toques` en cuadros de hardware.**
  Los primeros son `apretar_a`, con su tick de corrimiento por
  `RETRASO_DE_PANTALLA`; los segundos son `toques_hardware`, que es lo único
  que puede apretar adentro de la pantalla de ranuras del save point, donde
  `vueltas` no avanza. Ver `Partida.correr`.
* **`toques_hardware` ignoraba `apretar_a`** hasta el 2026-09-10, así que
  `savepoint-guarda` nunca apretaba el A que abre el save point. Pasaba en
  verde igual porque guardar no cambia un pixel. Acá los cuatro caminos de
  `Partida.correr` valen a la vez, que es lo que evita que se repita.

Los cuadros de cada caso —por qué el 380 y no el 400— son del caso y no del
arnés, y están en el docstring de cada uno.

El nombre que abre cada docstring es el del caso, que es también el de su
golden. La familia `hablar` corre con este mismo arnés y está en
`pruebas/rpgmaker/test_hablar_golden.py`: lo que cobra es la regla de RM2k para
hablarle a algo, y lo de acá son escenas de ABL.
"""

import pytest

from assembly.cartuchos import RELEASE
from consola import EMPEZAR
from tanda import golden, partida

# Cada caso es: nombre —que es también el de su página de prueba, con el
# `Teleport` a su mapa y su celda, la ruta forzada y el switch que arranca
# prendido—, los ticks que se capturan, los toques de A por tick y los toques
# por cuadro de hardware.
ESCENAS = (
    # Las dos del Sector 32: la puerta de la izquierda y la pantalla que se
    # lee. La segunda es la más larga de las dos y la que más mensajes encadena.
    ("puerta-izq", (100, 230, 600, 950),
     (20, 202, 323, 444, 565), ()),
    # El toque de 978 es del cuadro que se agregó al rearmar los textos para
    # la ventana: "According to this, the Catch Colony..." ya no entra en uno
    # y son dos. Sin él la escena queda un cuadro atrasada y 1300 y 1800
    # capturan otro momento.
    ("pantalla", (60, 200, 450, 930, 1300, 1800),
     (161, 282, 342, 584, 735, 857, 948, 978, 1008, 1099, 1159, 1219, 1430,
      1490, 1732), ()),
    # El save point de Lashe City, mirado sin abrirlo: los cuatro ticks son la
    # animación del brillo.
    ("savepoint", (20, 30, 40, 50), (), ()),
    # La tienda del mapa 10, y la B que la cierra. La B va por cuadro de
    # hardware porque adentro del menú de la tienda el reloj del juego no corre.
    ("tienda", (20, 60, 120, 200), (25, 90, 150),
     ("b:110",)),
    # El save point de verdad: parado encima del evento 67, A, la pantalla de
    # ranuras, y B por cuadros de hardware. Arranca **encima** del evento y no
    # enfrente a propósito: a un evento de la capa de abajo se le habla desde
    # su celda —`CheckEventTriggerHere`— y no desde la de al lado, y de frente
    # la página no corre y el caso pasa en vacío.
    ("savepoint-guarda", (60, 200), (10,), ("b:40",)),
    # Las puertas entre Lashe City y sus dos vecinos, Interiors (10) y 33,36
    # (9), pisadas con un paso de ruta, y la vuelta. El cruce 8→9 es el que
    # encontró el `PanScreen` de espera cero: la puerta EV0009 vuelve la cámara
    # antes del Teleport, y el auto rojo del 9 delataba el tick.
    ("puerta-8-10", (40, 120, 220), (), ()),
    ("puerta-10-8", (40, 120, 220), (), ()),
    ("puerta-8-9", (40, 120, 220), (), ()),
    ("puerta-9-8", (40, 120, 220), (), ()),
    # EV0041 del mapa 8: con el switch 24 corre la primera
    # —"Well, it's worth a try"— y el héroe salta la reja y se va para arriba.
    # El caso lo pone **encima** del evento, que es de la capa de abajo, por
    # lo mismo que `savepoint-guarda`: de frente la página no corre. Los ticks
    # son el mensaje, la subida, el salto en el aire y la llegada.
    ("ev41", (30, 60, 108, 200), (10, 40), ()),
    # El droide del Sector 32 y sus cuatro variantes: bloqueado, roto —con el
    # switch 22—, frenado, en cuadrado, y tapado por la capa de encima.
    ("bloqueo", (40, 60, 100), (), ()),
    ("droide", (3, 8, 25, 60, 106, 200), (), ()),
    ("droide-roto", (10, 20, 30, 45, 100), (), ()),
    ("droide-frenado", (20, 60, 120, 300), (), ()),
    ("droide-cuadrado", (50, 120, 300, 600), (), ()),
    # `ShowChoice`, del que la tanda sólo ve la ventana dibujada: acá sólo se
    # aprieta A, así que arriba, abajo y B no los toca nadie. El cursor lo
    # cubre `pruebas/rpgmaker/test_elegir.py`. Que la página corra lo dicen
    # los pixeles de la ventana, que si no corriera no estarían dibujados.
    ("elegir", (55, 90, 140, 210), (25, 60, 95, 150), ()),
    ("droide-tapado", (25, 50, 80, 95, 130), (), ()),
    # Core rompiendo la puerta, con el switch 7: los seis ticks caen alrededor
    # del golpe.
    ("core-puerta", (380, 407, 410, 425, 470, 600),
     (242, 311, 362, 457, 568, 588), ()),
    # Los escombros del Sector 32, abiertos con el switch 10 y cerrados sin él.
    ("escombros", (20, 40, 60, 90), (), ()),
    ("escombros-cerrados", (20, 60), (), ()),
    ("ascensor", (10, 30), (), ()),
    ("puerta-emisor", (10, 40), (20,), ()),
    # El más largo de la tanda: mil doscientos ticks de la escena entera del
    # Emitter Room. Un cero largo no prueba nada por sí solo —este caso estuvo
    # una vez en verde sin ejercitar nada, con la página sin compilar—, así
    # que lo que lo sostiene es que la página compile.
    ("talan", (40, 90, 120, 200, 400, 700, 1200), (), ()),
    # El Tram Officer del mapa 9 entero: cuatro mensajes, la elección
    # "1 minute", la caminata de espera, el cronómetro leído a una variable y
    # restado, la rama que dice "it's official, I'm late", y el azar que decide
    # "It's here!". Los ticks van después de que cada ventana esté compuesta:
    # la ROM tarda unos doce en componerla. El `CallEvent` al
    # Hover-Tram se acepta sin hacer.
    ("tram", (26, 50, 70, 88, 108, 150, 190, 220, 243, 256, 320),
     (10, 30, 54, 74, 91, 115, 224, 246, 260), ()),
)


@pytest.mark.parametrize(
    "nombre,cuadros,apretar,toques",
    ESCENAS, ids=[caso[0] for caso in ESCENAS])
def test_escena(nombre, cuadros, apretar, toques):
    """`escena`: una página del juego disparada desde una celda y una ruta.

    Cada cuadro corre desde cero: arrancar de nuevo es parte de lo que se
    compara.
    """
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro, apretar_a=apretar, toques_hardware=toques)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# Los toques de A de la cinemática de apertura: sus mensajes.
TOQUES_APERTURA = (841, 901, 961, 1021, 1474, 1595, 1776, 1897, 2018, 2078,
                   2259, 2380, 2489, 2683, 2743)

# Las cinemáticas: nombre, los ticks, los toques de A, cómo arranca y el
# cartucho. Las que arrancan en el 4 van en `release`, la ROM que se juega,
# que arranca ahí como el juego de verdad: llegar al 4 con un `Teleport` no da
# lo mismo —la rampa del fundido y el tinte salen corridos—. Ahí no hay
# páginas de prueba, así que "cómo arranca" son los switches que se escriben
# en la RAM antes del primer cuadro; en los demás es la página de prueba.
CINEMATICAS = (
    # La misma que `apertura`, mirada en otros ticks: los dos primeros caen
    # adentro de la rampa del primer fundido. Va con ventana: sin ella la
    # página que saca el tinte —que también tiene mensajes— no compila, y la
    # golden del 750 congelaba la escena teñida y sin personajes.
    ("cinematica", (50, 68, 170, 370, 750, 1110), TOQUES_APERTURA,
     (), "release"),
    # La cinemática no termina en el teletransporte: el último paso pisa el
    # evento 2, que es la escena de apertura entera, con cuatro personajes
    # caminando en el mismo mapa, o sea las poses en caliente en su caso real.
    # Es la misma corrida que `cinematica`, así que un tick que ya mira aquélla
    # acá sería la misma golden dos veces.
    ("apertura", (770, 830, 1210, 1980, 2910),
     TOQUES_APERTURA, (), "release"),
    # El recuerdo de CORE y MANTA, que lo destraba el switch 16: lo prende una
    # página de un mapa que no está en el cartucho del caso. Son 3900 ticks y
    # 34 toques de A, del mapa 5 al 6. Lo que sigue —el 6 salta al 3 y el 3 al
    # 4— no lo mira nadie todavía.
    ("manta", (300, 600, 1200, 1600, 2500, 2800, 3300, 3900),
     (212, 243, 394, 515, 727, 758, 789, 820, 971, 1517, 1548, 1699, 1790,
      1911, 1942, 2033, 2125, 2156, 2247, 2338, 2399, 2460, 2570, 2674, 2987,
      3018, 3079, 3110, 3141, 3214, 3510, 3541, 3723, 3826), "manta", None),
    # El cartel de "One year previously", que es lo único que este port dibuja
    # de `ShowPicture`. Arranca con el switch 21 —el que prende el final del
    # recuerdo— así que la página 3 del evento 1 del mapa 4 corre sola, y los
    # cinco ticks agarran el fundido entero: recién puesto y casi negro (470),
    # a mitad de la rampa de subida (550), a pleno (660), a mitad de la de
    # bajada (800) y ya borrado (880). El de la mitad no es adorno: es el único
    # que cobra la interpolación cuadro a cuadro.
    ("cartel", (470, 550, 660, 800, 880), (), (21,), "release"),
    # Delcentric Factory con ventana, el único mapa que toma el tercer reparto
    # de VRAM —`LAYOUT_VENTANA_SPRITE`, 512 tiles de sprite y 384 de fondo—. Va
    # con el mapa 1 al lado **a propósito**: es el que pone lluvia, y sin las
    # 19 gotas el 17 entra en el reparto de siempre y el caso no miraría el
    # camino nuevo. Verificado que da rojo —33% de los pixeles— moviéndole el
    # tilemap de la ventana encima de los tiles de fondo.
    ("factoria", (120, 150), (), "en-17", None),
)


@pytest.mark.parametrize(
    "nombre,cuadros,apretar,caso,en",
    CINEMATICAS, ids=[caso[0] for caso in CINEMATICAS])
def test_cinematica(nombre, cuadros, apretar, caso, en):
    """`cinematica`: la cinemática de apertura, entera.

    El mapa 4 prende dos switches, tiñe y teletransporta al 1; ahí arranca la
    lluvia, se salta dos veces **adentro del mismo mapa**, se manda a caminar
    al evento 8, cambia el grupo —sale DummyHero y entra Kersh— y el héroe sube
    tres celdas por una ruta forzada.

    Los dos primeros ticks de `cinematica` caen adentro de la rampa de vuelta
    del primer fundido y son lo único de la tanda que compara la rampa misma.
    Aguantan que la ROM pierda cuadros porque el fundido se cuenta en cuadros
    de hardware y no en vueltas del lazo; lo que sí los rompería es que
    perdiera un cuadro **antes** del salto. Cada teletransporte corre los ticks
    lo que dura su fundido, y la cinemática lleva uno por salto, porque RM2k
    funde también los que no cambian de mapa.

    Del arnés, dos que sólo tiene este caso:

    * **el grupo es el 10 y no el 11**, que es el único lugar de la tanda donde
      eso pasa: la cinemática *es* la que cambia el grupo, así que tiene que
      arrancar con el que el juego trae —DummyHero— y no con Kersh ya adentro;
    * **lo que no se compara**: nada en movimiento en un tick en que la ROM
      venga atrasada. El atraso lo producen los picos del lazo, y el toque de A
      lo resincroniza. Viene de cuando se comparaba contra una referencia que
      no perdía cuadros, y los ticks de entonces son los de las goldens.
    """
    for cuadro in cuadros:
        if en == RELEASE:
            # "Begin the Story", que es por donde se entra a `release`, la
            # ROM que se juega. Las goldens de `cinematica`, `apertura` y
            # `cartel` se congelaron en un cartucho
            # sin pantalla de título y salen byte por byte iguales a través
            # de ella: el título no cambia lo que se dibuja adentro del mapa.
            # Medido al fundir el título con el cartucho del juego, el
            # 2026-09-20, y otra vez al pasarlas de ése a `release`, el
            # 2026-09-24.
            p = partida(None, en=en, switches=caso, titulo=EMPEZAR)
        else:
            p = partida(caso, en=en)
        p.correr(cuadro, apretar_a=apretar)
        golden("%s-%d" % (nombre, cuadro), p.imagen())
