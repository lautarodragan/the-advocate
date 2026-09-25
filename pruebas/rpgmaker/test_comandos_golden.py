"""Los comandos sueltos de la tanda, disparados desde la página de prueba.

Todo lo de este archivo es lo mismo con otra página: un mapa, una página
inventada que emite **un** comando —su archivo en `pruebas/casos/`, con el
nombre del caso—, y unos ticks donde mirar lo que hizo. La
página es inventada por la razón de siempre —ninguna del juego que compile
ejercita el comando sola, o la que lo hace termina teletransportando y no queda
dónde mirar—, y lo inventado es la entrada y no la comparación: los dos lados
corren el mismo bytecode.

Del arnés hay tres cosas que valen para casi todos:

* **nadie aprieta el pad**, salvo `cerrar-right`, que existe justamente para
  probar que el pad **no** mueva al héroe mientras hay un mensaje;
* **el tinte de la página es lo que hace visible que la página siguió.** Muchos
  casos llevan una espera y un `TintScreen` detrás del comando: el
  tick de después del comando se ve teñido y el de antes no, así que un comando
  que no termina se nota.

De las quince recetas que esto reemplaza sólo sobrevive `cerrar`, porque la
llama `bsnes`; el nombre que abre cada docstring es el del caso, que es también
el de su golden.
"""

import pytest

from tanda import cartucho, cuadro_de_texto, golden, partida

# `KeyInputProc`: nombre —que es también el de su caso en `pruebas/casos/`,
# con el `Teleport` a la celda del héroe—, los ticks, los toques de A y los
# toques de dirección por tick.
TECLAS = (
    ("tecla-espera", (20, 60), (40,), ()),
    # La cruceta, que es lo que le faltaba al minijuego de las piedras del mapa
    # 11. El héroe arranca en **(22,8), donde abajo está cerrado**, y el toque
    # es hacia abajo, que es hacia donde ya mira: así el flanco lo lee el
    # comando y no mueve ni gira a nadie, que es lo único que la referencia no
    # modela de un toque de dirección. La celda no es decoración: en otra, el
    # mismo toque camina.
    ("tecla-dir", (41, 60), (), ("down:40",)),
)


@pytest.mark.parametrize(
    "nombre,cuadros,apretar,tocar", TECLAS,
    ids=[caso[0] for caso in TECLAS])
def test_tecla(nombre, cuadros, apretar, tocar):
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
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro, apretar_a=apretar, tocar=tocar)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# Los dos cuadros de la página automática del mapa 255, por un renglón que
# sea sólo suyo: el primero ni el segundo se distinguen por el de arriba, que
# en los dos es el nombre del lugar.
PRIMER_CUADRO = "The undercarriage of the bridge isn't"
SEGUNDO_CUADRO = "Make as little noise as possible!"

# El texto del juego pasando por el bloque de la ROM: nombre —que es el de su
# golden—, el caso, el cartucho, el tick, el renglón que identifica al cuadro
# que se está mirando y qué tiene que pasarle a ese cuadro en el cartucho.
TEXTOS = (
    # Sin pedir nada: el cuadro donde caiga. Es el único que mira los dos
    # ticks, porque es el que prueba el encadenado.
    ("texto", "grupo-11-en-255", None, (60, 400), None, None),
    # El mismo texto en `test-special`, donde el caso `empujon` lo deja
    # **encima** del borde de banco: la cabecera y el primer largo quedan en un
    # banco y el texto sigue en el otro. El compositor avanzaba `msg_ptr` con un `inc` de
    # dieciséis bits, así que a partir del borde leía el $0000 del mismo
    # banco, que en LoROM no es ROM. Verificado en rojo con ese `inc`:
    # **3414 pixeles**.
    ("texto-cruza", "grupo-11-en-255", "test-special", (60,), PRIMER_CUADRO,
     "cruza"),
    # Y el cuadro que sigue, que en el mismo cartucho cae entero del otro lado
    # del borde: ahí `msg_empezar` sumaba el desplazamiento de dieciséis bits
    # al puntero y perdía el acarreo. Verificado en rojo con esa suma: 3404
    # pixeles. Son las dos posiciones de un solo empujón, y por eso un cartucho
    # solo donde antes hacían falta dos rellenos que no convivían.
    ("texto-lejos", "grupo-11-en-255", "test-special", (400,), SEGUNDO_CUADRO,
     "lejos"),
)


@pytest.mark.parametrize("nombre,caso,en,cuadros,renglon,donde", TEXTOS,
                         ids=[caso[0] for caso in TEXTOS])
def test_texto(nombre, caso, en, cuadros, renglon, donde):
    """`texto`: el texto **del juego**, no el que le dictamos a la ROM.

    Todo lo demás usa el `ShowMessage` de una página de prueba, o sea líneas
    inventadas: eso prueba el dibujo, el bloqueo y el cierre, pero no el texto
    de un mapa del juego entrando en el bloque de la ROM detrás del de los
    otros, ni que el operando de `OP_MESSAGE` lo vuelva a encontrar.

    El mapa 255 se eligió midiendo: su página automática **sin condición de
    switch** son dos cuadros de texto seguidos y un switch, y de ahí salen tres
    cosas que ningún otro caso mira. Los **desplazamientos**: el segundo
    mensaje no empieza en cero, así que si el operando se ignorara se vería el
    primero dos veces. Los **cuatro renglones**, que ejercitan `msg_lineas`
    entero. Y el **encadenado**: al apretar A el primero se cierra y el segundo
    se abre en el mismo tick.

    **Las tres goldens son la misma imagen**, y eso es justamente lo que se
    prueba: lo que cambia entre los cartuchos no es lo que se dibuja sino
    dónde quedaron esos bytes. Por eso los dos corridos no alcanzan con la
    golden: si mañana el bloque se acomoda distinto y el cuadro deja de cruzar
    el borde, la imagen sale igual y la prueba dejaría de probar lo que dice.
    De ahí el `assert`, que va antes de correr nada y mira el cartucho.
    """
    if donde:
        desplazamiento, byte, largo = cuadro_de_texto(cartucho(en), renglon)
        # Un cuadro cruza si sus bytes no caen todos en el mismo banco, y los
        # 32 KB del archivo que arrancan en `banco * $8000` **son** el banco.
        cruza = byte >> 15 != (byte + largo - 1) >> 15
        # Y "del otro lado" es que el operando de 16 bits sumado a la
        # dirección del bloque se pase de $FFFF, que es la cuenta que hace
        # `msg_empezar`.
        lejos = (cartucho(en).simbolos["mensajes"] & 0xFFFF) \
            + desplazamiento > 0xFFFF
        porque = (
            "el cuadro %r del cartucho %r cae en el byte $%06X del archivo, "
            "mide %d y su desplazamiento es %d: cruza=%s, del otro lado=%s. "
            "Esta prueba lo quiere %r y lo que lo pone ahí es el tamaño del "
            "caso `empujon` —ver pruebas/casos/empujon.json y el cartucho "
            "`test-special` en tools/ensamblado/cartuchos.py—, así que si el "
            "bloque de textos se movió, el empujón hay que volver a medirlo."
            % (renglon, en, byte, largo, desplazamiento, cruza, lejos, donde))
        assert (cruza if donde == "cruza" else lejos and not cruza), porque
    for cuadro in cuadros:
        p = partida(caso, en=en)
        p.correr(cuadro, apretar_a=(200,))
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# `ControlVars` visto por el cronómetro: nombre —el de su caso, que lleva el
# `Teleport` al mapa y a la celda del héroe— y los ticks.
VARIABLES = (
    # 60 segundos a la variable 17, menos 25, y el cronómetro desde ella. Sin
    # las variables mostraría 60.
    ("vars", (2, 31, 61, 90)),
    # El mismo `MoveTo` de `lugar` pero con la celda en **dos variables**, que
    # es la otra rama de `CommandChangeEventLocation` y lo que le faltaba al
    # minijuego de las piedras del mapa 11. La página pone 21 y 13 en dos
    # variables y recién después planta al evento 3, así que el cuadro tiene
    # que salir igual que el de `lugar`, que lo planta con los números
    # escritos. Verificado en rojo: sumándole uno a la y en `op_place_var` da
    # 392 pixeles, y leyendo la variable de la y también para la x, 246.
    ("lugar-var", (20, 60)),
    # El cofre del mapa 133 y su llave: la rama por variable con y sin el ítem.
    ("cofre", (2, 30)),
    ("cofre-no", (2, 30)),
    ("cofre-llave", (2, 30)),
    # La clase 6 de `ControlVars` —las coordenadas de un personaje—, que es lo
    # que leen los mapas 49, 52 y 54 para seguir al auto de Lashe City. Los dos
    # ponen la coordenada en la variable 17 y el cronómetro desde ella, así que
    # el número se ve en los dígitos: si la ROM lee otra cosa, se nota.
    #
    # `var-heroe-x` lee la x del héroe, que está en (22,12): muestra 22 y no
    # 12. Verificado en rojo con el `cmp #PERSONAJE_X` de
    # `var_personaje_heroe` cambiado por PERSONAJE_Y: 48 pixeles en el cuadro
    # 30.
    ("var-heroe-x", (2, 30)),
    # `var-evento-y` lee la y de Kersh —el evento 3, blanco 4— **después** de
    # caminarle cuatro celdas para abajo con una ruta forzada, así que sólo da
    # si los dos lados leen la celda viva y no la que trae el mapa: son 13 y no
    # 9, y contra la misma página sin la ruta hay 571 pixeles de diferencia. En
    # rojo con el `+ 2` de `ev_pos_buf` cambiado por `+ 0` —o sea leyendo la
    # x—: 96 pixeles en el cuadro 80. **El tick es el 80 y no el 30** porque la
    # página espera a que la ruta termine antes de leer.
    ("var-evento-y", (2, 80)),
)


@pytest.mark.parametrize("nombre,cuadros", VARIABLES,
                         ids=[caso[0] for caso in VARIABLES])
def test_vars(nombre, cuadros):
    """`vars`: las variables, leídas con los dígitos del cronómetro.

    El cronómetro es el único número que este port dibuja en pantalla, así que
    es el único lugar donde el valor de una variable se puede comparar en
    pixeles: la página pone el número en la variable y después arranca el
    cronómetro **desde** ella.
    """
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


DESTELLOS = ("destello", "destello-compartido")


@pytest.mark.parametrize("nombre", DESTELLOS)
def test_destello(nombre):
    """`destello`: `FlashSprite`, el destello de un personaje.

    En la consola es un tinte de CGRAM —`pintar_flash` sube la paleta entera
    del personaje— y en RM2k es sobre la **imagen** del sprite. Son dos cosas
    distintas, y la única razón por la que no se ven distintas es que ningún
    caso tiene un segundo sprite visible compartiendo la paleta del que
    destella. Lo cuida `pruebas/herramientas/test_destello_paleta.py`.
    """
    for cuadro in (2, 12, 15, 23, 25):
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


def test_destellos_encimados():
    """`destellos-encimados`: un destello que termina mientras otro sigue.

    El evento 1 —el que asoma por el borde izquierdo— destella azul diez
    décimas, y dos décimas después el 4 destella rojo treinta. En el tick 90
    el del 1 ya terminó y el del 4 no, así que **el 1 tiene que verse igual
    que cuando terminaron los dos**. Con una sola paleta de destello para
    todas las ranuras se quedaba azul: el vblank subía sólo la del 4, y el
    cuadro que apagaba la del 1 no llegaba nunca. Es Kersh en la terraza del
    mapa 32.

    Contra el tick de llegada y no contra uno de después de los dos: con el
    error, el 1 **no vuelve nunca**, así que el final también está azul y la
    comparación daba igual.

    El segundo es el 4 y no el héroe a propósito, aunque fuera de pantalla: un
    destello sobre el héroe en el mapa 6 le cambia al conversor el reparto de
    paletas de sprite de todo el mapa, y mueve las goldens de `grafico` y
    `sprite-actor`. El 4 ya destella en `destello-compartido`.
    """
    evento = (0, 88, 16, 120)
    capturas = {}
    for cuadro in (0, 90):
        p = partida("destellos-encimados")
        p.correr(cuadro)
        capturas[cuadro] = p.imagen().crop(evento).tobytes()
        del p
    assert capturas[90] == capturas[0]


SATURADOS = ("saturar", "saturar-gris", "saturar-brillo")


@pytest.mark.parametrize("nombre", SATURADOS)
def test_saturar(nombre):
    """`saturar`: el tinte de pantalla en sus tres esquinas.

    Los tres son el mismo mapa con otro tinte: el negro, el gris —saturación en
    cero, que es el camino que promedia los tres canales— y uno con los canales
    **pasados de 100**, que es donde la cuenta puede desbordar. Un tick antes
    del tinte y uno después.
    """
    for cuadro in (30, 120):
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


TIMERS = (("timer", (2, 31, 61, 90)),
          # El cronómetro llegando a cero. Mira el 2, el 40, el 59 y el 61 y
          # **se saltea justo el 60**, que es el único que difiere: es una
          # divergencia de un tick en el cuadro en que el cronómetro se apaga,
          # 252 pixeles en los dígitos, y está anotada en
          # `divergencias/cronometro-llegando-a-cero.md` como cosmética.
          ("timer-cero", (2, 40, 59, 61)))


@pytest.mark.parametrize("nombre,cuadros", TIMERS,
                         ids=[caso[0] for caso in TIMERS])
def test_timer(nombre, cuadros):
    """`timer`: el cronómetro corriendo, con sus dígitos en pantalla."""
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("nombre", ("rama-item", "rama-item-no"))
def test_rama_item(nombre):
    """`rama-item`: la rama de `ConditionalBranch` por objeto.

    Los dos casos son la misma página con y sin el `ChangeItems` que le da el
    Idol al grupo, así que **la diferencia entre ellos es la respuesta de la
    rama**: 40012 pixeles, el 69,78%. Verificado en rojo con el
    `beq si_item_no` de la ROM cambiado por `bra`, o sea contestando siempre
    que no lo tiene: el caso con el ítem da esos mismos 40012.
    """
    for cuadro in (2, 30):
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


RAMAS_DE_ACTOR = ("rama-equipo", "rama-equipo-no", "rama-hab",
                  "rama-hab-no")


@pytest.mark.parametrize("nombre", RAMAS_DE_ACTOR)
def test_rama_actor(nombre):
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
    for cuadro in (2, 30):
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("cuadro", (2, 5, 9))
def test_relampago(cuadro):
    """`relampago`: el destello de pantalla, que hasta el 2026-09-08 no lo
    corría nadie.

    Verificado que da rojo con el `lda #0` de antes: 387 pixeles en los tres.
    """
    p = partida("relampago")
    p.correr(cuadro)
    golden("relampago-%d" % cuadro, p.imagen())


# `PanScreen`: nombre —el de su caso— y los ticks.
PANEOS = (
    ("pan", (16, 32, 48, 64, 65, 66)),
    ("pan-vuelve", (16, 48, 65, 70, 82, 83)),
    # Un "volver" con espera y la cámara ya en su lugar: cero cuadros, y la
    # página sigue en el mismo. Verificado que da rojo con el `rts` de antes:
    # 13710 pixeles en el cuadro 1, el tinte un tick tarde.
    ("pan-cero", (1, 2, 3, 4)),
    # La lluvia pegada al mapa: la cámara se corre dos celdas y las gotas con
    # ella. La apertura es el único lugar donde llueve y ahí la cámara no se
    # mueve, así que sin esto nada miraría el scroll de las gotas. `pan-lluvia`
    # encontró además que la referencia pintaba encimadas al revés que el PPU.
    ("pan-lluvia", (16, 32, 48, 64, 65, 66)),
)


@pytest.mark.parametrize("nombre,cuadros", PANEOS,
                         ids=[caso[0] for caso in PANEOS])
def test_pan(nombre, cuadros):
    """`pan`: `PanScreen`, la cámara corrida sin que el héroe se mueva."""
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# `ShakeScreen`: nombre —el de su caso— y los ticks.
SACUDIDAS = (
    ("sacudir", (3, 6, 9, 11, 13, 60)),
    ("sacudir-fuerte", (2, 5, 9, 14, 17, 60)),
    # Contra el borde del mapa, que es donde la sacudida no puede correr la
    # cámara para los dos lados.
    ("sacudir-borde", (3, 6, 9, 11, 13, 60)),
    ("sacudir-lluvia", (2, 5, 9, 14, 17, 60)),
)


@pytest.mark.parametrize("nombre,cuadros",
                         SACUDIDAS, ids=[caso[0] for caso in SACUDIDAS])
def test_sacudir(nombre, cuadros):
    """`sacudir`: `ShakeScreen`, la pantalla temblando."""
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


ANIMACIONES = (
    # La 82 es de alcance "pantalla" y achicada al 11%: lo que se mira son sus
    # **destellos**. Encontró que un destello de pantalla con cuadros impares
    # arranca por la fase que ninguna página toma.
    ("animacion", (1, 3, 35, 37, 43, 60)),
    # Y el **dibujo**, que es lo que `animacion` no miraba: la 78 —"Single
    # Magic Flame B", 144x176 achicada al 36%— sobre el héroe. Los ticks miran
    # el primero, uno de los tres que la animación tiene **vacíos**, y los tres
    # más cargados.
    ("animacion-dibujo", (1, 15, 33, 37, 41, 47)),
    # La misma sobre un **evento**, que en la ROM es otro camino: el héroe sale
    # de `hero_x` y el evento de su fila de NPC, por `npc_de_evento`. Es sobre
    # Manta, que está pegada al borde izquierdo: la caja arranca en -18 y
    # `emit_object` la recorta. El objetivo es ella y no Kersh a propósito:
    # Kersh es el líder, comparte paleta con el héroe, y el destello del
    # objetivo se la teñiría a los dos.
    ("animacion-evento", (1, 25, 33, 41, 47)),
)


@pytest.mark.parametrize("nombre,cuadros", ANIMACIONES,
                         ids=[caso[0] for caso in ANIMACIONES])
def test_animacion(nombre, cuadros):
    """`animacion`: una animación de batalla sobre el mapa, `OP_ANIMATION`.

    Va por la página de prueba porque la escena del Emitter Room, que es la que
    las usa, no se puede disparar desde una prueba.
    """
    for cuadro in cuadros:
        p = partida(nombre)
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
    ningún mapa.** Lo pone `pruebas/casos/cerrar.json`, y el `TintScreen` de
    atrás, sin espera, es lo que hace visible que la página siguió.

    **La receta se fue el 2026-09-16**, con `bsnes`: lo que la llamaba
    ahora es `pruebas/rpgmaker/test_cores.py`, que corre esta misma ROM en los
    dos cores y compara las dos pantallas entre sí.
    """
    nombre = "cerrar" if direccion == "none" else "cerrar-right"
    p = partida("cerrar")
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
    for cuadro in cuadros:
        p = partida("autocierre-%d" % pausas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


VENTANAS = ("ventana", "ventana-1", "ventana-6", "ventana-269", "ventana-348")


@pytest.mark.parametrize("nombre", VENTANAS)
def test_ventana(nombre):
    """`ventana`: la ventana de mensaje dibujada por la consola.

    La fuente, el marco, la paleta y dónde caen las celdas en el tilemap. La
    ventana se dibuja al cargar el mapa y se queda, y el texto es sintético,
    así que lo único que se compara es el dibujo; abrirla y cerrarla desde el
    intérprete es `cerrar`.

    Los mapas no son varias veces lo mismo: la ventana se lleva la paleta que
    queda justo debajo de la capa de encima, y quién la paga cambia de mapa en
    mapa —hay uno donde al fondo le sobran paletas, otro que fusiona el máximo
    posible, y otro que no entra en el tilemap de 64x32—. La paleta de la
    ventana es una sola para todo el cartucho —las celdas se emiten una vez
    con la paleta adentro— así que gana la más baja de las que cada mapa
    pediría.
    """
    p = partida(nombre)
    p.correr(200)
    golden(nombre, p.imagen())


@pytest.mark.parametrize("cuadro", (60, 400))
def test_espera(cuadro):
    """`espera`: que una espera espere de verdad, con una página inventada.

    El intérprete corre tick a tick desde que dejó de colapsar el tiempo, pero
    **ninguna página del juego que compile tiene una espera**, así que ese
    camino —el corazón del cambio— no lo ejercitaba nada. Lo sintético es la
    entrada y no la comparación.

    Se mira antes y después, no el tick exacto en que cambia: el arranque de la
    ROM incluye la subida al SPC700 y la referencia no modelaba eso, así que el
    borde caía en cuadros distintos de cada lado. Con margen a los dos lados la
    prueba sigue siendo filosa: si la espera no esperara, el tick de antes ya
    estaría teñido.
    """
    p = partida("espera")
    p.correr(cuadro)
    golden("espera-%d" % cuadro, p.imagen())
