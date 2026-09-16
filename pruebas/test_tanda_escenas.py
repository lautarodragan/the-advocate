"""Las escenas del juego: `escena`, de `rom/hitos.txt`, mudada a pytest.

Una escena es el héroe plantado en una celda, una ruta forzada que lo lleva a
pisar o a encarar algo, y la página del juego que eso dispara, mirada en varios
ticks. Es la receta más usada de la tanda.

Tres cosas del arnés, que son las que vivían en el comentario de la receta:

* **La dirección no llega a la ROM.** `escena` tomaba un `dir` y se lo pasaba
  sólo a `snes_expect.py`: era hacia dónde mira el héroe **al arrancar**, que
  la referencia necesita que le digan y la ROM ya sabe. Si la página lo gira
  con un `face_*`, gana la página, en los dos lados. Contra una captura de la
  ROM ese argumento no tiene a quién decírselo, así que acá no está.
* **Los toques de A van en ticks y los de `toques` en cuadros de hardware.**
  Los primeros son `--apretar-a`, con su tick de corrimiento por
  `RETRASO_DE_PANTALLA`; los segundos son `--toques-hardware`, que es lo único
  que puede apretar adentro de la pantalla de ranuras del save point, donde
  `vueltas` no avanza. Ver `Partida.correr`.
* **`--toques-hardware` ignoraba `--apretar-a`** hasta el 2026-09-10, así que
  `savepoint-guarda` nunca apretaba el A que abre el save point. Pasaba en
  verde igual porque guardar no cambia un pixel. Acá los cuatro caminos de
  `Partida.correr` valen a la vez, que es lo que evita que se repita.

Los cuadros de cada caso —por qué el 380 y no el 400— son del caso y no del
arnés, y están en el docstring de cada uno.
"""

import pytest

from tanda import cartucho, golden, partida

# Cada caso es: nombre, mapa, celda de arranque, ruta forzada, los ticks que se
# capturan, los toques de A por tick, el switch que arranca prendido, los mapas
# de más que entran al cartucho, y los toques por cuadro de hardware. Es la
# línea de `rom/hitos.txt` sin el `dir` y sin el `115` del arranque, que es el
# de siempre.
ESCENAS = (
    # Las dos del Sector 32: la puerta de la izquierda y la pantalla que se
    # lee. La segunda es la más larga de las dos y la que más mensajes encadena.
    ("puerta-izq", 2, "4 54", "12", (100, 230, 600, 950),
     (20, 202, 323, 444, 565), "", (), ()),
    ("pantalla", 2, "36 74", "3", (60, 200, 450, 930, 1300, 1800),
     (161, 282, 342, 584, 735, 857, 948, 1008, 1099, 1159, 1219, 1430, 1490,
      1732), "", (), ()),
    # El save point de Lashe City, mirado sin abrirlo: los cuatro ticks son la
    # animación del brillo.
    ("savepoint", 8, "9 55", "0", (20, 30, 40, 50), (), "", (), ()),
    # La tienda del mapa 10, y la B que la cierra. La B va por cuadro de
    # hardware porque adentro del menú de la tienda el reloj del juego no corre.
    ("tienda", 10, "42 6", "12", (20, 60, 120, 200), (25, 90, 150), "", (),
     ("b:110",)),
    # El save point de verdad: parado encima del evento 67, A, la pantalla de
    # ranuras, y B por cuadros de hardware. Arranca **encima** del evento y no
    # enfrente a propósito: a un evento de la capa de abajo se le habla desde
    # su celda —`CheckEventTriggerHere`— y no desde la de al lado, y de frente
    # la página no corre y el caso pasa en vacío.
    ("savepoint-guarda", 8, "9 56", "14", (60, 200), (10,), "", (), ("b:40",)),
    # Las puertas entre Lashe City y sus dos vecinos, Interiors (10) y 33,36
    # (9), pisadas con un paso de ruta, y la vuelta. El cruce 8→9 es el que
    # encontró el `PanScreen` de espera cero: la puerta EV0009 vuelve la cámara
    # antes del Teleport, y el auto rojo del 9 delataba el tick.
    ("puerta-8-10", 8, "48 21", "0", (40, 120, 220), (), "", ("10",), ()),
    ("puerta-10-8", 10, "42 16", "0", (40, 120, 220), (), "", ("8",), ()),
    ("puerta-8-9", 8, "73 56", "1", (40, 120, 220), (), "", ("9",), ()),
    ("puerta-9-8", 9, "73 47", "1", (40, 120, 220), (), "", ("8",), ()),
    # EV0041 del mapa 8, que hasta el 2026-09-10 se caía entero por la
    # condición de ítem de su tercera página: con el switch 24 corre la primera
    # —"Well, it's worth a try"— y el héroe salta la reja y se va para arriba.
    # Verificado que sin hablarle la referencia difiere en miles de pixeles en
    # el cuadro 200.
    ("ev41", 8, "52 24", "12", (60, 120, 200), (10, 40), "24", ("10",), ()),
    # El droide del Sector 32 y sus cuatro variantes: bloqueado, roto —con el
    # switch 22—, frenado, en cuadrado, y tapado por la capa de encima.
    ("bloqueo", 2, "7 76", "0 0 0 0", (40, 60, 100), (), "", (), ()),
    ("droide", 2, "7 74", "14", (3, 8, 25, 60, 106, 200), (), "", (), ()),
    ("droide-roto", 2, "7 74", "14", (10, 20, 30, 45, 100), (), "22", (), ()),
    ("droide-frenado", 2, "7 71", "14", (20, 60, 120, 300), (), "", (), ()),
    ("droide-cuadrado", 2, "32 58", "14", (50, 120, 300, 600), (), "", (), ()),
    # `ShowChoice`, del que la tanda sólo ve la ventana dibujada: acá sólo se
    # aprieta A, así que arriba, abajo y B no los toca nadie. El cursor lo
    # cubre `pruebas/test_elegir.py`.
    #
    # **Lo que este caso pierde al mudarse**: la receta además imprimía el
    # texto de la ventana —el cuadro 140 tiene que decir `('> Yes', '  No')`—
    # porque cuatro cuadros en cero también sería el resultado si la página no
    # compilara de los dos lados. Contra una captura congelada eso no se puede
    # preguntar, y taro lo aceptó: lo que queda son los pixeles de esa misma
    # ventana, que si la página no corriera no estarían dibujados.
    ("elegir", 7, "6 5", "12", (55, 90, 140, 210), (25, 60, 95, 150), "24",
     (), ()),
    ("droide-tapado", 2, "7 73", "23 0 23 23 23 2", (25, 50, 80, 95, 130), (),
     "", (), ()),
    # Core rompiendo la puerta, con el switch 7: los seis ticks caen alrededor
    # del golpe.
    ("core-puerta", 2, "87 76", "0", (380, 407, 410, 425, 470, 600),
     (242, 311, 362, 457, 568, 588), "7", (), ()),
    # Los escombros del Sector 32, abiertos con el switch 10 y cerrados sin él.
    ("escombros", 2, "85 71", "3 3 3", (20, 40, 60, 90), (), "10", (), ()),
    ("escombros-cerrados", 2, "85 71", "3 3 3", (20, 60), (), "", (), ()),
    ("ascensor", 2, "71 72", "12", (10, 30), (), "11", (), ()),
    ("puerta-emisor", 3, "38 69", "12", (10, 40), (20,), "", (), ()),
    # El más largo de la tanda: mil doscientos ticks de la escena entera del
    # Emitter Room. Un cero largo no prueba nada por sí solo —este caso estuvo
    # una vez en verde sin ejercitar nada, con la página sin compilar de los
    # dos lados—, así que lo que lo sostiene es que la página compile.
    ("talan", 3, "38 69", "23 0", (40, 90, 120, 200, 400, 700, 1200), (), "13",
     ("1", "2", "4", "5"), ()),
    # El Tram Officer del mapa 9 entero: cuatro mensajes, la elección
    # "1 minute", la caminata de espera, el cronómetro leído a una variable y
    # restado, la rama que dice "it's official, I'm late", y el azar que decide
    # "It's here!". Los ticks van después de que cada ventana esté compuesta de
    # los dos lados: la ROM tarda unos doce en componerla. El `CallEvent` al
    # Hover-Tram se acepta sin hacer.
    ("tram", 9, "24 8", "12",
     (26, 50, 70, 88, 108, 150, 190, 220, 243, 256, 320),
     (10, 30, 54, 74, 91, 115, 224, 246, 260), "24", ("8",), ()),
)


@pytest.mark.parametrize(
    "nombre,mapa,celda,ruta,cuadros,apretar,switch,mapas,toques",
    ESCENAS, ids=[caso[0] for caso in ESCENAS])
def test_escena(nombre, mapa, celda, ruta, cuadros, apretar, switch, mapas,
                toques):
    """`just escena`: una página del juego disparada desde una celda y una ruta.

    Los cuadros de un mismo caso salen de **una sola** conversión, que es lo
    caro; correr el emulador una vez por cuadro no lo es. Y cada uno corre
    desde cero: arrancar de nuevo es parte de lo que se compara.
    """
    sfc, simbolos, orden = cartucho(
        "escena-%s" % nombre, "--map-id", mapa, "--inicio", *celda.split(),
        "--con-ventana", "--ruta-de-prueba", *ruta.split(),
        *(("--switch", switch) if switch else ()),
        *(("--mapas",) + tuple(mapas) if mapas else ()))
    for cuadro in cuadros:
        p = partida(sfc, simbolos, orden)
        p.correr(cuadro, apretar_a=apretar, toques_hardware=toques)
        golden("%s-%d" % (nombre, cuadro), p.imagen())
