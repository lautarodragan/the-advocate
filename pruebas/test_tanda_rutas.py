"""Las rutas forzadas de `rom/hitos.txt`: `MoveEvent` sobre el héroe y sobre un
evento, y lo que cuelga de ellas.

Todo lo de acá corre en el **mapa 6** salvo donde se diga, y eso es una decisión
y no una costumbre: es grande y está abierto, así que una ruta camina en
cualquier dirección sin chocar, y **es mudo**, que es lo que hace usable el
desfasaje de arranque —la ROM no empieza a interpretar en el cuadro 0 y la
referencia no modelaba nada de eso—. Si algún día los cuadros intermedios dan
rojo a la vez y el asentado no, es eso.

Del arnés hay una sola cosa que valga para todos: **ninguno de estos casos
aprieta el pad**, salvo `pisar`. El que camina es la ruta, y un pad sostenido
sería una segunda fuente de movimiento.

Y una advertencia que no es del arnés pero decide los cuadros de varios: en el
mapa 6, del tick 47 en adelante, una ruta que baja cuatro celdas desde (22,12)
diverge en **diez pixeles** de dos tiles animados del chipset, con la orden 34
puesta y sin ella. Está anotado en ESTADO.md y es anterior a estos casos; por
eso varios miran hasta el 40 y no más lejos.
"""

import pytest

from tanda import cartucho, golden, partida

# Ruta forzada sobre el héroe: nombre, la ruta, los ticks, la celda de arranque
# —vacía es la del mapa— y la frecuencia de la página.
RUTAS = (
    ("ruta", "1 1 1 1 23 23 2 2 2 2 23 23 0 0 0 0", (18, 60, 120, 400), "", 8),
    ("salto", "1 1 24 1 1 25 2 2", (10, 14, 20, 26, 60), "", 8),
    ("through", "36 0 0 0 0 0 0", (20, 40, 60), "10 8", 8),
    ("anim", "38 2 2 2 39 2 2 2", (4, 10, 16, 28, 34, 44), "10 8", 8),
    ("ruta-lenta", "1 1 12 2 23 2", (20, 44, 88, 100, 150, 400), "", 4),
    ("ruta-frec", "2 2 31 2 2 30 2 2", (20, 30, 40, 52), "", 8),
    ("ruta-vel", "28 2 2 2 29 2 2", (10, 20, 30, 44, 60, 80), "", 8),
    ("ruta-vel-lenta", "29 29 2 2 28 28 28 2 2",
     (5, 33, 64, 70, 90, 120, 200), "", 8),
)


@pytest.mark.parametrize("nombre,ruta,cuadros,inicio,frecuencia", RUTAS,
                         ids=[caso[0] for caso in RUTAS])
def test_ruta(nombre, ruta, cuadros, inicio, frecuencia):
    """`just ruta`: una ruta forzada sobre el héroe, en varios ticks.

    Lo que cada caso ejercita, que es lo que decidió su ruta:

        ruta             los pasos que entran, con esperas en el medio
        salto            las órdenes 24 y 25, el salto
        through          atravesar paredes: el `if (self.GetThrough())` de
                         `CheckOrMakeWayEx`, con la fila de pared delante
        anim             parar y soltar la animación: el ciclo se congela en la
                         pose del medio y el personaje sigue caminando
        ruta-lenta       la frecuencia distinta de 8: se queda quieto entre
                         orden y orden, `1 << (9 - f)` cuadros después de un
                         paso y `1 << (8 - f)` después de un giro
        ruta-frec        las órdenes 30 y 31, la frecuencia desde la ruta
        ruta-vel         las 28 y 29, la velocidad, que **queda puesta** al
                         terminar la ruta: RM2k repone la frecuencia y no la
                         velocidad
        ruta-vel-lenta   las dos cosas a la vez

    **Ni la ruta ni los ticks son cualquiera**: los que se comparan tienen que
    caer donde el ciclo de la caminata **no** queda en la columna parada,
    porque ahí un error de contador no se ve. Por eso las rutas van en patas
    cortas con esperas en el medio y no de corrido.

    Y los ticks de un caso salen de una sola conversión, que es lo caro.
    """
    sfc, simbolos, mapas = cartucho(
        "ruta-%s" % nombre, "--map-id", "6",
        *(("--inicio",) + tuple(inicio.split()) if inicio else ()),
        "--ruta-de-prueba", *ruta.split(), "--frecuencia", frecuencia)
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("cuadro", (89, 91))
def test_ruta_evento(cuadro):
    """`just ruta-evento`: un evento **sin gráfico** caminando su ruta.

    Es lo que `MoveEvent` agrega sobre otro evento: hasta ese día la única ruta
    forzada que la ROM sabía caminar era la del héroe. Como el evento no se ve,
    lo único comparable es **cuánto tarda**, y eso es exactamente lo que espera
    el `ProceedWithMovement` que va detrás; lo que se mira en pantalla es el
    tinte de la página, que llega cuando la ruta terminó.

    La ruta prueba los pasos que entran, uno que da contra una pared y se
    saltea **sin gastar un cuadro**, una espera que sí gasta uno, y un giro que
    es instantáneo.

    Del arnés: **el cuadro del medio se saltea a propósito y no por
    comodidad.** Son el 89 y el 91 porque el 90 sale partido: la ROM sube CGRAM
    en el vblank **siguiente**, así que el tinte entra a mitad de pantalla.
    """
    sfc, simbolos, mapas = cartucho(
        "ruta-evento", "--map-id", "6",
        "--ruta-de-evento", *"3 0 0 0 0 0 0 3 3 3 23 2 2 1 13".split(),
        "--pagina-de-prueba", "0", "0", "0", "50")
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro)
    golden("ruta-evento-%d" % cuadro, p.imagen())


# Un evento con gráfico caminando: nombre, mapa, ruta, celda del héroe, ticks y
# frecuencia de la página.
NPCS = (
    ("npc", 6, "4 2 2 2 2 1 1 12", "22 12", (10, 27, 40, 60), 8),
    ("npc-lento", 6, "4 2 2 12 1", "22 12", (20, 44, 88, 100, 200), 4),
    ("npc-encara", 6, "4 21", "22 12", (5, 30), 8),
    ("npc-encara-lado", 6, "4 21", "25 10", (5, 30), 8),
    ("npc-frec", 6, "4 2 31 2 1 1 30 12", "22 12", (20, 40, 60, 80), 8),
    ("salto-npc", 6, "4 24 2 2 25 1 1", "22 12", (3, 6, 10, 14, 20, 40), 8),
    ("npc-diagonal", 10, "1 4 6 7 6", "6 10", (10, 25, 40, 70), 8),
    ("npc-diagonal-gira", 6, "4 15 5 5 5", "22 12", (20, 40), 8),
    ("npc-hacia-heroe", 6, "4 9 9 9 9", "25 10", (5, 25, 44, 70), 8),
)


@pytest.mark.parametrize("nombre,mapa,ruta,celda,cuadros,frecuencia", NPCS,
                         ids=[caso[0] for caso in NPCS])
def test_npc(nombre, mapa, ruta, celda, cuadros, frecuencia):
    """`just npc`: un evento **con gráfico** caminando en pantalla.

    Es la otra mitad de `MoveEvent`: en `ruta-evento` el evento es invisible y
    de él sólo se ve cuánto tarda; acá se comparan además la posición a mitad
    de paso, la pose del ciclo y el orden de dibujado cuando el evento le cruza
    por encima al héroe.

    Uno por cosa: la frecuencia distinta de 8 —`npc-lento`—, `face_hero`
    —`npc-encara` y `npc-encara-lado`, que es `GetDirectionToCharacter`: manda
    el eje con más distancia y en empate el vertical—, las diagonales
    —`npc-diagonal`, **que va en el mapa 10 y no en el 6** porque el 6 está
    abierto por los cuatro lados y ahí la regla de paso no se ejercita, y
    `npc-diagonal-gira`, hacia dónde queda mirando, que no es hacia el rincón—,
    y `move_towards_hero` —`npc-hacia-heroe`, que mira la costura: que la
    dirección se recalcule en cada orden y que girar pase antes de mirar si se
    puede—.
    """
    sfc, simbolos, orden = cartucho(
        "npc-%s" % nombre, "--map-id", mapa, "--inicio", *celda.split(),
        "--ruta-de-evento", *ruta.split(), "--frecuencia", frecuencia)
    for cuadro in cuadros:
        p = partida(sfc, simbolos, orden)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# La orden 34 de ruta: nombre, ruta, el gráfico al que cambia y los ticks.
GRAFICOS = (
    ("grafico", "4 2 2 34 0 2 2", "Future1 0", (10, 25, 40, 70)),
    ("invisible", "4 2 2 34 0 2 2", "nobodyhere 0", (10, 25, 40, 70)),
    ("grafico-heroe", "0 2 2 34 0 2 2", "Future1 0", (10, 20, 25, 40)),
    ("heroe-invisible", "0 2 2 34 0 2 2", "nobodyhere 0", (10, 25, 40)),
)


@pytest.mark.parametrize("nombre,ruta,grafico,cuadros", GRAFICOS,
                         ids=[caso[0] for caso in GRAFICOS])
def test_grafico(nombre, ruta, grafico, cuadros):
    """`just grafico`: un personaje que cambia de gráfico a mitad de una ruta.

    Es la orden 34, la última de `MoveCommand` de las que este juego usa y la
    única con **operando**. Dos cosas que no son la misma: que cambie —sigue
    caminando con otro gráfico, con la pose del ciclo donde estaba— y que
    desaparezca, que es lo que pasa al cambiar a `nobodyhere`, un CharSet sin
    un solo pixel opaco.

    Los dos primeros son sobre un evento y los dos últimos **sobre el héroe**,
    que es el otro camino: su gráfico sale de la tabla de actores, y la ROM le
    mueve el puntero a `hero_poses` porque las doce poses del actor están
    escritas con la misma forma que una entrada de `npc_poses`.

    Los ticks no llegan más lejos por algo **anterior a esto**: ver el aviso de
    los tiles animados en la cabecera de este archivo.
    """
    sfc, simbolos, mapas = cartucho(
        "grafico-%s" % nombre, "--map-id", "6", "--inicio", "22", "12",
        "--ruta-de-evento", *ruta.split(),
        "--grafico-de-prueba", *grafico.split())
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


LUGARES = (("lugar", "4 21 13 12", "4 2 2 2 2", (14, 15, 20, 60)),
           ("lugar-quieto", "4 21 10", "", (10, 60)))


@pytest.mark.parametrize("nombre,lugar,ruta,cuadros", LUGARES,
                         ids=[caso[0] for caso in LUGARES])
def test_lugar(nombre, lugar, ruta, cuadros):
    """`just lugar`: plantar a un evento en una celda, `ChangeEventLocation`.

    Es `MoveTo`, y la vuelta que tiene está en lo que **no** hace: no toca la
    ruta ni hacia dónde mira, y corta el paso en curso —`SetRemainingStep(0)`—.
    Los dos casos son plantarlo a mitad de su ruta, donde tiene que seguir con
    los pasos que le quedaban desde la celda nueva, y plantarlo sin ruta
    ninguna.

    **Las celdas son del piso marrón a la vista y no da lo mismo**: plantado
    donde lo tapa la capa de encima los dos lados lo dibujan escondido, y la
    prueba daba cero con el corte del paso sacado. Los ticks tampoco son los de
    la espera: `OP_DELAY n` suelta la página en el cuadro n+2, y elegidos a ojo
    caían antes del corte.
    """
    sfc, simbolos, mapas = cartucho(
        "lugar-%s" % nombre, "--map-id", "6", "--inicio", "22", "12",
        *(("--ruta-de-evento",) + tuple(ruta.split()) if ruta else ()),
        "--lugar-de-prueba", *lugar.split())
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("cuadro", (20, 26, 34, 40))
def test_parar_rutas(cuadro):
    """`just parar`: `HaltAllMovement`, todas las rutas abandonadas de golpe.

    El evento 3 y el héroe caminando cuatro celdas cada uno; a los 24 ticks la
    página corta las dos, y recién ahí el `ProceedWithMovement` que va detrás la
    suelta y el tinte se aplica.

    Existe porque **el único `HaltAllMovement` del juego** está en una página
    que termina teletransportando: no hay dónde mirar lo que el comando hizo.
    Acá se ve solo, y es filoso por construcción: sin el comando las dos rutas
    siguen hasta el final y el tinte llega decenas de cuadros más tarde. Uno de
    los ticks las mira caminando, otro paradas con el tinte puesto, y dos son
    de control.

    Verificado en rojo con `op_stop_routes` cambiado por un `jmp otro` pelado
    —o sea el comando aceptado y no hecho, sólo en la ROM—: 59,89% en el
    cuadro 34.

    **Los ticks llegan hasta el 40 y no más lejos a propósito**: ver el aviso
    de los tiles animados en la cabecera de este archivo.
    """
    sfc, simbolos, mapas = cartucho(
        "parar-rutas", "--map-id", "6", "--inicio", "22", "12",
        "--ruta-de-evento", *"4 2 2 2 2".split(),
        "--ruta-de-prueba", *"2 2 2 2".split(),
        "--parar-de-prueba", "24", "--pagina-de-prueba", "0", "12", "0", "0")
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro)
    golden("parar-rutas-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("cuadro", (10, 30))
def test_sprite_actor(cuadro):
    """`just sprite-actor`: el CharSet de un **actor**, cambiado en caliente.

    Es `ChangeSpriteAssociation`, y es lo que traba la persecución en auto,
    donde el héroe *es* el auto: los mapas de la carrera sacan a todo el grupo
    y meten a `CarRED` o `CarBLUE`. La página de prueba le cambia el CharSet al
    líder **después de la espera**, así que el tick de antes lo mira con el
    gráfico del LDB y el de después con el nuevo.

    `--grafico-de-prueba` va junto y no es redundante: `--sprite-de-prueba`
    reserva la ranura de la tabla de gráficos en **todos** los mapas —es lo que
    hace que el índice signifique lo mismo después de un salto— y el otro es el
    que le mete las poses al banco de sprites del mapa.

    Lo que este caso **no** mira: que el cambio sobreviva al teletransporte.
    Eso lo cobra `pruebas/test_sprite_actor.py`.
    """
    sfc, simbolos, mapas = cartucho(
        "sprite-actor", "--map-id", "6", "--inicio", "22", "12",
        "--sprite-de-prueba", "11", "Future1", "0",
        "--grafico-de-prueba", "Future1", "0",
        "--pagina-de-prueba", "20", "100", "100", "100")
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro)
    golden("sprite-actor-%d" % cuadro, p.imagen())


MENSAJE = ("SEWELL",
           "There you are, Talan. Ready for",
           "the big night?")


@pytest.mark.parametrize("cuadro", (21, 23, 50, 130))
def test_anclada(cuadro):
    """`just anclada`: la ventana de mensaje quieta con el mapa scrolleando.

    La ventana es un tilemap propio con HDMA y no celdas estampadas en el
    tilemap del mapa, y esto es lo que lo cobra: durante un mensaje lo único
    que mueve la cámara es **una ruta forzada**, que es exactamente el caso de
    RM2k que obligó a esa arquitectura —`UpdateMoveRoute` corre antes del guard
    de `IsMessageActive`—. La página inventada es `ruta, mensaje`, y la ventana
    se queda abierta —nadie aprieta A— con el mapa scrolleando por detrás.

    **Los ticks están elegidos por el resto de la cámara contra 8**, que es lo
    que hundió al intento anterior: estampando la ventana en celdas del tilemap
    del mapa, sólo puede caer bien cuando `camara_x` y `camara_y` son múltiplos
    de 8.
    """
    sfc, simbolos, mapas = cartucho(
        "anclada", "--map-id", "6", "--mensaje-de-prueba", *MENSAJE,
        "--ruta-de-prueba", *"1 1 1 1 1 1 2 2 2 2 2 2".split())
    p = partida(sfc, simbolos, mapas)
    p.correr(cuadro)
    golden("anclada-%d" % cuadro, p.imagen())


PISADAS = (("ruta-pisa", "0 0 0 0", "0", (16, 24, 200)),
           ("ruta-pasa", "0 0 0 0 0", "0", (100, 200)),
           ("ruta-pisa-cola", "0 0 0 0", "60 0 0 50", (50, 200)))


@pytest.mark.parametrize("nombre,ruta,pagina,cuadros", PISADAS,
                         ids=[caso[0] for caso in PISADAS])
def test_ruta_pisa(nombre, ruta, pagina, cuadros):
    """`just ruta-pisa`: una ruta forzada que termina sobre un evento de
    contacto, y otra que le pasa por encima.

    Es el disparo que le faltaba a la cinemática de apertura. La regla es la de
    `Game_Player::UpdateMovement`: al terminar un paso se mira la celda **salvo
    que el héroe tenga una ruta forzada puesta**, y un movimiento que es la
    última orden de la ruta la cancela entera antes de ese chequeo. O sea: los
    pasos del medio no pisan nada, el último sí. La ROM tenía la mitad —miraba
    en todos— y la referencia la otra —no miraba en ninguno—.

    Los tres son en el mapa 70: una ruta que termina sobre el evento y abre el
    mensaje, una que **pasa** por encima y no abre nada, y una que termina con
    la página todavía corriendo —RM2k no pierde el contacto: lo deja esperando
    y lo corre cuando la página termina—.
    """
    sfc, simbolos, mapas = cartucho(
        "ruta-pisa-%s" % nombre, "--map-id", "70", "--inicio", "12", "8",
        "--con-ventana", "--ruta-de-prueba", *ruta.split(),
        "--pagina-de-prueba", *pagina.split())
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


PISAR = (("pisar", 70, "12 8", "up", ""),
         ("atravesar-cofre", 20, "80 19", "left", "36"),
         ("atravesar-savept", 20, "90 27", "left", "36"))


@pytest.mark.parametrize("nombre,mapa,celda,direccion,ruta", PISAR,
                         ids=[caso[0] for caso in PISAR])
def test_pisar(nombre, mapa, celda, direccion, ruta):
    """`just pisar`: el héroe camina con el pad y pisa un evento de contacto.

    La caminata **frena** al pisar: mientras el intérprete tiene una página en
    el frente el pad no mueve, que es el
    `if (Game_Map::IsAnyEventStarting()) return;` de RM2k. Sin eso el héroe
    daba un paso de más mientras el mensaje se componía.

    `ruta` es opcional y sirve para lo contrario: una ruta forzada que corre
    **antes** de que el pad empiece a caminar, para dejar al héroe en un
    estado. La usan los dos de `atravesar`, con la orden 36 puesta y la ruta
    sin un solo paso: lo que se mira es que la bandera que deja no siga
    valiendo para la caminata con el pad.

        atravesar-cofre   el Slum30Chest1c en (78,19), capa "same": tiene que
                          frenarlo. **Verificado en rojo con la ROM de
                          antes**: 5606 pixeles, 9,78%, con el héroe ya del
                          otro lado del cofre. Es el defecto que taro reportó:
                          después de tomar el Hover-Tram se les caminaba por
                          encima a los cofres
        atravesar-savept  el SaveInSector30 en (88,27), capa "below": **no**
                          tiene que frenarlo, y el héroe le camina quince
                          celdas por encima. Es el control del par, y no es de
                          adorno: sacándole el `cmp movil_capa` a
                          `celda_bloqueada` —o sea haciendo que toda capa
                          frene— da 29959 pixeles, 52,24%

    Del arnés: **es el único de este archivo que sostiene el pad**, y los 200
    ticks son un número fijo y no un plan —lo que se mira es dónde frenó, no
    cuánto tardó—.
    """
    sfc, simbolos, orden = cartucho(
        "pisar-%s" % nombre, "--map-id", mapa, "--inicio", *celda.split(),
        "--con-ventana",
        *(("--ruta-de-prueba",) + tuple(ruta.split()) if ruta else ()))
    p = partida(sfc, simbolos, orden)
    p.correr(200, sosteniendo=(direccion,))
    golden(nombre, p.imagen())
