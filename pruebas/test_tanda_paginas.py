"""Los comandos sueltos de la tanda, disparados desde la página de prueba.

Todo lo de este archivo es lo mismo con un flag distinto: un mapa, una página
inventada que emite **un** comando, y unos ticks donde mirar lo que hizo. La
página es inventada por la razón de siempre —ninguna del juego que compile
ejercita el comando sola, o la que lo hace termina teletransportando y no queda
dónde mirar—, y lo inventado es la entrada y no la comparación: los dos lados
corren el mismo bytecode.

Del arnés hay tres cosas que valen para casi todos:

* **nadie aprieta el pad**, salvo `cerrar-right`, que existe justamente para
  probar que el pad **no** mueva al héroe mientras hay un mensaje;
* **el tinte de la página es lo que hace visible que la página siguió.** Muchos
  casos llevan un `--pagina-de-prueba` con espera y tinte detrás del comando: el
  tick de después del comando se ve teñido y el de antes no, así que un comando
  que no termina se nota;
* **los ticks de un caso salen de una sola conversión.** Convertir el mapa es lo
  caro; correr el emulador una vez por tick no lo es.

De las quince recetas que esto reemplaza sólo sobrevive `cerrar`, porque la
llama `bsnes`; el nombre que abre cada docstring es el del caso, que es también
el de su golden.
"""

import pytest

from tanda import cartucho, golden, partida

MENSAJE = ("SEWELL",
           "There you are, Talan. Ready for",
           "the big night?")


# `KeyInputProc`: nombre, la declaración del comando, la celda del héroe, los
# ticks, el tinte de la página, los toques de A, las variables y el cronómetro
# de la página, y los toques de dirección por tick.
TECLAS = (
    ("tecla-espera", "88 1 0 1 0", "22 12", (20, 60), "0 100 0 0", (40,), "",
     "", ()),
    # La cruceta, que es lo que le faltaba al minijuego de las piedras del mapa
    # 11. El héroe arranca en **(22,8), donde abajo está cerrado**, y el toque
    # es hacia abajo, que es hacia donde ya mira: así el flanco lo lee el
    # comando y no mueve ni gira a nadie, que es lo único que la referencia no
    # modela de un toque de dirección. La celda no es decoración: en otra, el
    # mismo toque camina.
    ("tecla-dir", "88 1 1 0 0", "22 8", (41, 60), "12 0 0 50", (), "88 9 0 0 0",
     "60 1", ("down:40",)),
)


@pytest.mark.parametrize(
    "nombre,tecla,celda,cuadros,tinte,apretar,variables,timer,tocar", TECLAS,
    ids=[caso[0] for caso in TECLAS])
def test_tecla(nombre, tecla, celda, cuadros, tinte, apretar, variables, timer,
               tocar):
    """`tecla`: `KeyInputProc`, la tecla leída desde una página.

    Del arnés: **los dos toques van por caminos distintos y los dos tienen que
    llegar.** El de A es `apretar_a`, y el de dirección es `tocar` —el
    `--tocar` del corredor—, que existe porque la forma de `KeyInputProc` que
    espera la cruceta necesita un **flanco** de dirección a mitad de una
    escena, y sostener con el pad no produce ninguno. Los dos cuentan sus ticks
    igual, con el tick de corrimiento de `RETRASO_DE_PANTALLA`.

    Que uno de los dos se ignorara calladito es exactamente cómo la receta
    dejó una vez un caso en verde que no apretaba A y por lo tanto no probaba
    nada.
    """
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6", "--inicio", *celda.split(),
        "--tecla-de-prueba", *tecla.split(),
        *(("--vars-de-prueba",) + tuple(variables.split()) if variables
          else ()),
        *(("--timer-de-prueba",) + tuple(timer.split()) if timer else ()),
        "--pagina-de-prueba", *tinte.split())
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro, apretar_a=apretar, tocar=tocar)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


TEXTOS = (
    ("texto", ""),
    # El mismo caso con el bloque de textos corrido más allá del primer banco.
    # Verificado en rojo con el `msg_empezar` de antes: 3116 pixeles en el
    # cuadro 60 y 3404 en el 400, todos en la ventana, que ahí dibuja el texto
    # que le tocó leer de otro lado.
    ("texto-lejos", "33000"),
    # Y el mismo con el cuadro **encima** del borde de banco, que es lo que
    # `texto-lejos` no cubría: allá el cuadro entero cae del otro lado y
    # `msg_empezar` ya lo ubicaba bien, acá la cabecera y el primer largo
    # quedan en el banco de antes y el texto sigue en el de después. El
    # compositor avanzaba `msg_ptr` con un `inc` de dieciséis bits, así que a
    # partir del borde leía el $0000 del mismo banco, que en LoROM no es ROM.
    #
    # El relleno son 32766 y no un número redondo: el bloque queda alineado al
    # banco —lo hace el `.bloque`— así que el cuadro de dos bytes antes del
    # borde es el que lo cruza. Verificado en rojo con el `inc msg_ptr` de
    # antes: **3414 pixeles en el cuadro 60**. El 400 da cero también con el
    # defecto puesto, porque el segundo cuadro arranca entero del otro lado.
    ("texto-cruza", "32766"),
)


@pytest.mark.parametrize("nombre,relleno", TEXTOS,
                         ids=[caso[0] for caso in TEXTOS])
def test_texto(nombre, relleno):
    """`texto`: el texto **del juego**, no el que le dictamos a la ROM.

    Todo lo demás usa `--mensaje-de-prueba`, o sea líneas inventadas: eso
    prueba el dibujo, el bloqueo y el cierre, pero no que un `ShowMessage` de
    RM2k compile, que su texto entre en el bloque de la ROM y que el operando
    de `OP_MESSAGE` lo vuelva a encontrar.

    El mapa 255 se eligió midiendo: su página automática **sin condición de
    switch** son dos cuadros de texto seguidos y un switch, y de ahí salen tres
    cosas que ningún otro caso mira. Los **desplazamientos**: el segundo
    mensaje no empieza en cero, así que si el operando se ignorara se vería el
    primero dos veces. Los **cuatro renglones**, que ejercitan `msg_lineas`
    entero. Y el **encadenado**: al apretar A el primero se cierra y el segundo
    se abre en el mismo tick.

    `relleno` son bytes muertos delante del bloque de textos, que es lo que
    corre los desplazamientos más allá de los 32 KB que mide la ventana de un
    banco de LoROM. Reproducirlo de verdad pide un cartucho de muchos mapas
    hablados; con el relleno lo hace uno de un mapa.
    """
    sfc, simbolos, mapas = cartucho(
        "texto-%s" % (relleno or "sin-relleno"), "--map-id", "255",
        *(("--relleno-de-mensajes", relleno) if relleno else ()),
        "--con-ventana")
    for cuadro in (60, 400):
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro, apretar_a=(200,))
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# `ControlVars` visto por el cronómetro: nombre, mapa, el cronómetro de la
# página, la declaración de variables, la celda del héroe, los ticks, el tinte,
# el inventario y la ruta forzada del evento.
VARIABLES = (
    # 60 segundos a la variable 17, menos 25, y el cronómetro desde ella. Sin
    # las variables mostraría 60.
    ("vars", 6, "60 1", "17 0 7 1 0 17 2 0 25 0 17 9 0 0 0", "2 10",
     (2, 31, 61, 90), "12 0 0 50", "", ""),
    # El mismo `MoveTo` de `lugar` pero con la celda en **dos variables**, que
    # es la otra rama de `CommandChangeEventLocation` y lo que le faltaba al
    # minijuego de las piedras del mapa 11. La página pone 21 y 13 en dos
    # variables y recién después planta al evento 3, así que el cuadro tiene
    # que salir igual que el de `lugar`, que lo planta con los números
    # escritos. Verificado en rojo: sumándole uno a la y en `op_place_var` da
    # 392 pixeles, y leyendo la variable de la y también para la x, 246.
    ("lugar-var", 6, "60 1", "31 0 0 21 0 32 0 0 13 0 31 10 0 4 32", "22 12",
     (20, 60), "12 0 0 50", "", ""),
    # El cofre del mapa 133 y su llave: la rama por variable con y sin el ítem.
    ("cofre", 133, "0 0", "123 0 0 8 0", "4 7", (2, 30), "12 100 100 100", "",
     ""),
    ("cofre-no", 133, "0 0", "123 0 0 7 0", "4 7", (2, 30), "12 100 100 100",
     "", ""),
    ("cofre-llave", 133, "0 0", "123 0 0 8 0", "4 7", (2, 30),
     "12 100 100 100", "151 1", ""),
    # La clase 6 de `ControlVars` —las coordenadas de un personaje—, que es lo
    # que leen los mapas 49, 52 y 54 para seguir al auto de Lashe City. Los dos
    # ponen la coordenada en la variable 17 y el cronómetro desde ella, así que
    # el número se ve en los dígitos: si la ROM lee otra cosa, se nota.
    #
    # `var-heroe-x` lee la x del héroe, que está en (22,12): muestra 22 y no
    # 12. Verificado en rojo con el `cmp #PERSONAJE_X` de
    # `var_personaje_heroe` cambiado por PERSONAJE_Y: 48 pixeles en el cuadro
    # 30.
    ("var-heroe-x", 6, "60 1", "17 0 6 10001 1 17 9 0 0 0", "22 12", (2, 30),
     "12 0 0 50", "", ""),
    # `var-evento-y` lee la y de Kersh —el evento 3, blanco 4— **después** de
    # caminarle cuatro celdas para abajo con una ruta forzada, así que sólo da
    # si los dos lados leen la celda viva y no la que trae el mapa: son 13 y no
    # 9, y contra la misma página sin la ruta hay 571 pixeles de diferencia. En
    # rojo con el `+ 2` de `ev_pos_buf` cambiado por `+ 0` —o sea leyendo la
    # x—: 96 pixeles en el cuadro 80. **El tick es el 80 y no el 30** porque la
    # página espera a que la ruta termine antes de leer.
    ("var-evento-y", 6, "60 1", "17 0 6 4 2 17 9 0 0 0", "22 12", (2, 80),
     "12 0 0 50", "", "4 2 2 2 2"),
)


@pytest.mark.parametrize(
    "nombre,mapa,timer,variables,celda,cuadros,tinte,items,ruta", VARIABLES,
    ids=[caso[0] for caso in VARIABLES])
def test_vars(nombre, mapa, timer, variables, celda, cuadros, tinte, items,
              ruta):
    """`vars`: las variables, leídas con los dígitos del cronómetro.

    El cronómetro es el único número que este port dibuja en pantalla, así que
    es el único lugar donde el valor de una variable se puede comparar en
    pixeles: la página pone el número en la variable y después arranca el
    cronómetro **desde** ella.
    """
    sfc, simbolos, orden = cartucho(
        nombre, "--map-id", mapa, "--inicio", *celda.split(),
        "--timer-de-prueba", *timer.split(),
        "--vars-de-prueba", *variables.split(),
        *(("--items-de-prueba",) + tuple(items.split()) if items else ()),
        *(("--ruta-de-evento",) + tuple(ruta.split()) if ruta else ()),
        "--pagina-de-prueba", *tinte.split())
    for cuadro in cuadros:
        p = partida(sfc, simbolos, orden)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


DESTELLOS = (("destello", "1 31 0 0 31 24", "2 10"),
             ("destello-compartido", "4 31 0 0 31 24", "22 10"))


@pytest.mark.parametrize("nombre,flash,celda", DESTELLOS,
                         ids=[caso[0] for caso in DESTELLOS])
def test_destello(nombre, flash, celda):
    """`destello`: `FlashSprite`, el destello de un personaje.

    En la consola es un tinte de CGRAM —`pintar_flash` sube la paleta entera
    del personaje— y en RM2k es sobre la **imagen** del sprite. Son dos cosas
    distintas, y la única razón por la que no se ven distintas es que ningún
    caso tiene un segundo sprite visible compartiendo la paleta del que
    destella. Lo cuida `pruebas/test_destello_paleta.py`.
    """
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6", "--inicio", *celda.split(),
        "--flash-de-prueba", *flash.split(),
        "--pagina-de-prueba", "12", "0", "0", "50")
    for cuadro in (2, 12, 15, 23, 25):
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


SATURADOS = (("saturar", "60 0 0 0 0"),
             ("saturar-gris", "60 100 100 100 0"),
             ("saturar-brillo", "60 0 120 120 200"))


@pytest.mark.parametrize("nombre,tinte", SATURADOS,
                         ids=[caso[0] for caso in SATURADOS])
def test_saturar(nombre, tinte):
    """`saturar`: el tinte de pantalla en sus tres esquinas.

    Los tres son el mismo mapa con otro tinte: el negro, el gris —saturación en
    cero, que es el camino que promedia los tres canales— y uno con los canales
    **pasados de 100**, que es donde la cuenta puede desbordar. Un tick antes
    del tinte y uno después.
    """
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "73",
        "--pagina-de-prueba", *tinte.split())
    for cuadro in (30, 120):
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


TIMERS = (("timer", "600 1", (2, 31, 61, 90)),
          # El cronómetro llegando a cero. Mira el 2, el 40, el 59 y el 61 y
          # **se saltea justo el 60**, que es el único que difiere: es una
          # divergencia de un tick en el cuadro en que el cronómetro se apaga,
          # 252 pixeles en los dígitos, y está anotada en ESTADO.md como
          # cosmética.
          ("timer-cero", "1 1", (2, 40, 59, 61)))


@pytest.mark.parametrize("nombre,timer,cuadros", TIMERS,
                         ids=[caso[0] for caso in TIMERS])
def test_timer(nombre, timer, cuadros):
    """`timer`: el cronómetro corriendo, con sus dígitos en pantalla."""
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6", "--inicio", "2", "10",
        "--timer-de-prueba", *timer.split(),
        "--pagina-de-prueba", "12", "0", "0", "50")
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("nombre,items", (("rama-item", "90 1"),
                                          ("rama-item-no", "")))
def test_rama_item(nombre, items):
    """`rama-item`: la rama de `ConditionalBranch` por objeto.

    Los dos casos son la misma página con y sin el `ChangeItems` que le da el
    Idol al grupo, así que **la diferencia entre ellos es la respuesta de la
    rama**: 40012 pixeles, el 69,78%. Verificado en rojo con el
    `beq si_item_no` de la ROM cambiado por `bra`, o sea contestando siempre
    que no lo tiene: el caso con el ítem da esos mismos 40012.
    """
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6", "--inicio", "22", "12",
        *(("--items-de-prueba",) + tuple(items.split()) if items else ()),
        "--rama-item-de-prueba", *"90 12 0 0 100".split())
    for cuadro in (2, 30):
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


RAMAS_DE_ACTOR = (("rama-equipo", "5 11 82 12 0 0 100"),
                  ("rama-equipo-no", "5 11 84 12 0 0 100"),
                  ("rama-hab", "4 11 131 12 0 0 100"),
                  ("rama-hab-no", "4 11 152 12 0 0 100"))


@pytest.mark.parametrize("nombre,rama", RAMAS_DE_ACTOR,
                         ids=[caso[0] for caso in RAMAS_DE_ACTOR])
def test_rama_actor(nombre, rama):
    """`rama-actor`: las dos ramas de actor con dos operandos,
    `OP_IF_ACTOR`.

    Cada par es la misma página preguntando por algo que se cumple y por algo
    que no, así que **la diferencia entre uno y otro es la respuesta de la
    rama**: 40012 pixeles, el 69,78%. Kersh es el actor 11: lleva puesto el
    ítem 82 y no el 84, y a su nivel del LDB sabe la habilidad 131 y no la 152.

    Verificado en rojo de las dos maneras, con el `beq sia_si` de cada camino
    cambiado por un `bra`: contestando siempre que sí, `rama-equipo-no` y
    `rama-hab-no` dan 40012 pixeles; contestando siempre que no, los dan
    `rama-equipo` y `rama-hab`.
    """
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6", "--inicio", "22", "12",
        "--rama-actor-de-prueba", *rama.split())
    for cuadro in (2, 30):
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("cuadro", (2, 5, 9))
def test_relampago(cuadro):
    """`relampago`: el destello de pantalla, que hasta el 2026-09-08 no lo
    corría nadie.

    Verificado que da rojo con el `lda #0` de antes: 387 pixeles en los tres.
    """
    sfc, simbolos, mapas = cartucho(
        "relampago", "--map-id", "1", "--inicio", "22", "56",
        "--destello-de-prueba", *"31 31 31 31 12".split())
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro)
    golden("relampago-%d" % cuadro, p.imagen())


# `PanScreen`: nombre, la declaración del comando, los ticks, la celda del
# héroe y la lluvia.
PANEOS = (
    ("pan", "2 0 2 2 1", (16, 32, 48, 64, 65, 66), "", ""),
    ("pan-vuelve", "2 0 2 2 1 3 0 0 4 1", (16, 48, 65, 70, 82, 83), "", ""),
    # Un "volver" con espera y la cámara ya en su lugar: cero cuadros, y la
    # página sigue en el mismo. Verificado que da rojo con el `rts` de antes:
    # 13710 pixeles en el cuadro 1, el tinte un tick tarde.
    ("pan-cero", "3 0 0 4 1", (1, 2, 3, 4), "", ""),
    # La lluvia pegada al mapa: la cámara se corre dos celdas y las gotas con
    # ella. La apertura es el único lugar donde llueve y ahí la cámara no se
    # mueve, así que sin esto nada miraría el scroll de las gotas. `pan-lluvia`
    # encontró además que la referencia pintaba encimadas al revés que el PPU.
    ("pan-lluvia", "2 0 2 2 1", (16, 32, 48, 64, 65, 66), "", "2"),
)


@pytest.mark.parametrize("nombre,pan,cuadros,celda,lluvia", PANEOS,
                         ids=[caso[0] for caso in PANEOS])
def test_pan(nombre, pan, cuadros, celda, lluvia):
    """`pan`: `PanScreen`, la cámara corrida sin que el héroe se mueva."""
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6",
        *(("--inicio",) + tuple(celda.split()) if celda else ()),
        "--pan-de-prueba", *pan.split(),
        "--pagina-de-prueba", "0", "0", "0", "50",
        *(("--lluvia-de-prueba", lluvia) if lluvia else ()))
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


SACUDIDAS = (
    ("sacudir", 7, "3 3 2 1", (3, 6, 9, 11, 13, 60), "", ""),
    ("sacudir-fuerte", 6, "9 8 3 1", (2, 5, 9, 14, 17, 60), "", ""),
    # Contra el borde del mapa, que es donde la sacudida no puede correr la
    # cámara para los dos lados.
    ("sacudir-borde", 2, "3 3 2 1", (3, 6, 9, 11, 13, 60), "4 54", ""),
    ("sacudir-lluvia", 6, "9 8 3 1", (2, 5, 9, 14, 17, 60), "", "2"),
)


@pytest.mark.parametrize("nombre,mapa,sacudida,cuadros,celda,lluvia",
                         SACUDIDAS, ids=[caso[0] for caso in SACUDIDAS])
def test_sacudir(nombre, mapa, sacudida, cuadros, celda, lluvia):
    """`sacudir`: `ShakeScreen`, la pantalla temblando."""
    sfc, simbolos, orden = cartucho(
        nombre, "--map-id", mapa,
        *(("--inicio",) + tuple(celda.split()) if celda else ()),
        "--sacudida-de-prueba", *sacudida.split(),
        "--pagina-de-prueba", "0", "0", "0", "50",
        *(("--lluvia-de-prueba", lluvia) if lluvia else ()))
    for cuadro in cuadros:
        p = partida(sfc, simbolos, orden)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


ANIMACIONES = (
    # La 82 es de alcance "pantalla" y achicada al 11%: lo que se mira son sus
    # **destellos**. Encontró que un destello de pantalla con cuadros impares
    # arranca por la fase que ninguna página toma.
    ("animacion", "82 10001 1", (1, 3, 35, 37, 43, 60), ""),
    # Y el **dibujo**, que es lo que `animacion` no miraba: la 78 —"Single
    # Magic Flame B", 144x176 achicada al 36%— sobre el héroe. Los ticks miran
    # el primero, uno de los tres que la animación tiene **vacíos**, y los tres
    # más cargados.
    ("animacion-dibujo", "78 10001 1", (1, 15, 33, 37, 41, 47), ""),
    # La misma sobre un **evento**, que en la ROM es otro camino: el héroe sale
    # de `hero_x` y el evento de su fila de NPC, por `npc_de_evento`. Es sobre
    # Manta, que está pegada al borde izquierdo: la caja arranca en -18 y
    # `emit_object` la recorta. El objetivo es ella y no Kersh a propósito:
    # Kersh es el líder, comparte paleta con el héroe, y el destello del
    # objetivo se la teñiría a los dos.
    ("animacion-evento", "78 1 1", (1, 25, 33, 41, 47), "3 10"),
)


@pytest.mark.parametrize("nombre,animacion,cuadros,celda", ANIMACIONES,
                         ids=[caso[0] for caso in ANIMACIONES])
def test_animacion(nombre, animacion, cuadros, celda):
    """`animacion`: una animación de batalla sobre el mapa, `OP_ANIMATION`.

    Va por la página de prueba porque la escena del Emitter Room, que es la que
    las usa, no se puede disparar desde una prueba.
    """
    sfc, simbolos, mapas = cartucho(
        nombre, "--map-id", "6",
        *(("--inicio",) + tuple(celda.split()) if celda else ()),
        "--animacion-de-prueba", *animacion.split(),
        "--pagina-de-prueba", "0", "0", "0", "50")
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("cuadro", (60, 400))
@pytest.mark.parametrize("direccion", ("none", "right"))
def test_cerrar(direccion, cuadro):
    """`just cerrar`: la ventana de mensaje abierta, y cerrada con A.

    Dos ticks, y el segundo es el único que ejercita el cierre: `flush_video`
    apaga el HDMA de la ventana cuando `msg_abierto` vuelve a cero.

        60    la ventana en pantalla y la página frenada: el tinte que viene
              después del mensaje todavía no se aplicó
        400   la ventana borrada y el tinte puesto, o sea que A la cerró y la
              página siguió

    Con una dirección sostenida en vez de `none` prueba además que **el pad no
    mueva al héroe mientras hay un mensaje**, que es el guard de
    `Game_Player::UpdateNextMovementAction`. La ruta forzada es otra cosa y sí
    camina, porque allá `UpdateMoveRoute` corre antes del guard; eso lo mira
    `anclada`.

    Tres trampas del arnés:

    * **el toque de A cae un tick antes del número**, que es
      `RETRASO_DE_PANTALLA`: la ROM dibuja lo que armó la vuelta anterior, así
      que para que su tick N salga cerrado el flanco tiene que caer en la
      vuelta N-1. `Partida.correr` lo resta con la misma convención que el
      corredor;
    * **los ticks se miran con margen y no en el borde.** A los 60 el mensaje
      está abierto hace rato y a los 400 hace rato que se cerró. Pegado al
      borde no se puede mirar: la ROM compone la ventana tick a tick y tarda
      entre nueve y diecinueve según el texto;
    * **con dirección el arranque no puede ser cero.** La cruceta se mantiene
      apretada desde que el arranque termina, así que antes de que la página
      abra el mensaje el héroe daría pasos que nadie modeló. Los 115 de
      `Partida` son justamente eso.

    Y una que no se ve en el código: **el mensaje va escrito acá y no sale de
    ningún mapa.** Lo pone `--mensaje-de-prueba`, y el `--pagina-de-prueba
    0 0 0 50` es el tinte de atrás, con espera en cero: es lo que hace visible
    que la página siguió.

    **La receta se fue el 2026-09-16**, con `bsnes`: lo que la llamaba
    ahora es `pruebas/test_cores.py`, que corre esta misma ROM en los
    dos cores y compara las dos pantallas entre sí.
    """
    sfc, simbolos, mapas = cartucho(
        "cerrar", "--map-id", "7", "--mensaje-de-prueba", *MENSAJE,
        "--pagina-de-prueba", "0", "0", "0", "50")
    nombre = "cerrar" if direccion == "none" else "cerrar-right"
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro, apretar_a=(200,),
             sosteniendo=() if direccion == "none" else (direccion,))
    golden("%s-%d" % (nombre, cuadro), p.imagen())


AUTOCIERRES = (("autocierre", 1, (62, 63)),
               ("autocierre-3", 3, (184, 185)))


@pytest.mark.parametrize("nombre,pausas,cuadros", AUTOCIERRES,
                         ids=[caso[0] for caso in AUTOCIERRES])
def test_autocierre(nombre, pausas, cuadros):
    """`autocierre`: los dos escapes de texto, `\\|` y `\\^`.

    `\\|` pausa y `\\^` cierra el cuadro sin que nadie apriete nada. **Los
    ticks están pegados al cierre a propósito**, para que 62 y 63 no den lo
    mismo: con una pausa cierra en el 63 y con tres en el 185, así que el
    primero de cada par mira la ventana todavía abierta y el segundo el tinte
    que va detrás del mensaje. Verificado en rojo con la referencia contando
    60: 4122 pixeles en el 62 y los mismos en el 184.

    Del arnés: **la cola del mensaje se arma acá**, con una barra por pausa y
    el `\\^` al final, que es lo que la receta hacía con un `for` de bash.
    """
    linea = MENSAJE[2] + "\\|" * pausas + "\\^"
    sfc, simbolos, mapas = cartucho(
        "autocierre-%d" % pausas, "--map-id", "7",
        "--mensaje-de-prueba", MENSAJE[0], MENSAJE[1], linea,
        "--pagina-de-prueba", "0", "0", "0", "50")
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


VENTANAS = (("ventana", 7, ()),
            ("ventana-1", 1, ()),
            ("ventana-6", 6, ()),
            ("ventana-269", 269, ()),
            ("ventana-348", 348, ()),
            ("ventana-7-y-269", 7, ("269",)))


@pytest.mark.parametrize("nombre,mapa,mapas", VENTANAS,
                         ids=[caso[0] for caso in VENTANAS])
def test_ventana(nombre, mapa, mapas):
    """`ventana`: la ventana de mensaje dibujada por la consola.

    La fuente, el marco, la paleta y dónde caen las celdas en el tilemap. La
    ventana se dibuja al cargar el mapa y se queda, y el texto es sintético,
    así que lo único que se compara es el dibujo; abrirla y cerrarla desde el
    intérprete es `cerrar`.

    Los mapas no son varias veces lo mismo: la ventana se lleva la paleta que
    queda justo debajo de la capa de encima, y quién la paga cambia de mapa en
    mapa —hay uno donde al fondo le sobran paletas, otro que fusiona el máximo
    posible, y otro que no entra en el tilemap de 64x32—. El último caso es
    **dos mapas en la misma ROM**: la paleta de la ventana es una sola para
    todo el cartucho —las celdas se emiten una vez con la paleta adentro— así
    que gana la más baja de las que cada mapa pediría, y el cero mide que la
    ROM y la referencia apretaron igual.
    """
    sfc, simbolos, orden = cartucho(
        nombre, "--map-id", mapa,
        *(("--mapas",) + tuple(mapas) if mapas else ()),
        "--mensaje-de-prueba", *MENSAJE)
    p = partida(sfc, simbolos, orden)
    p.correr(200)
    golden(nombre, p.imagen())
