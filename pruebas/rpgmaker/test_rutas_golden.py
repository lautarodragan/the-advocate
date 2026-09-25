"""Las rutas forzadas de la tanda: `MoveEvent` sobre el héroe y sobre un
evento, y lo que cuelga de ellas.

Todo lo de acá corre en el **mapa 6** salvo donde se diga, y eso es una decisión
y no una costumbre: es grande y está abierto, así que una ruta camina en
cualquier dirección sin chocar, y **es mudo**, que es lo que hace usable el
desfasaje de arranque —la ROM no empieza a interpretar en el cuadro 0—. Si
algún día los cuadros intermedios dan
rojo a la vez y el asentado no, es eso.

Del arnés hay una sola cosa que valga para todos: **ninguno de estos casos
aprieta el pad**, salvo `pisar`. El que camina es la ruta, y un pad sostenido
sería una segunda fuente de movimiento.

Y una advertencia que no es del arnés pero decide los cuadros de varios: en el
mapa 6, del tick 47 en adelante, una ruta que baja cuatro celdas desde (22,12)
diverge en **diez pixeles** de dos tiles animados del chipset, con la orden 34
puesta y sin ella. Está anotado en
`divergencias/fase-de-los-tiles-animados.md` y es anterior a estos casos; por
eso varios miran hasta el 40 y no más lejos.

El nombre que abre cada docstring es el del caso, que es también el de su
golden.
"""

import pytest

from tanda import golden, partida

# Ruta forzada sobre el héroe: nombre —el de su caso, que lleva la ruta, la
# frecuencia de la página y, si no arranca donde arranca el mapa, el
# `Teleport` a su celda— y los ticks.
RUTAS = (
    ("ruta", (18, 60, 120, 400)),
    ("salto", (10, 14, 20, 26, 60)),
    ("through", (20, 40, 60)),
    ("anim", (4, 10, 16, 28, 34, 44)),
    ("ruta-lenta", (20, 44, 88, 100, 150, 400)),
    ("ruta-frec", (20, 30, 40, 52)),
    ("ruta-vel", (10, 20, 30, 44, 60, 80)),
    ("ruta-vel-lenta", (5, 33, 64, 70, 90, 120, 200)),
)


@pytest.mark.parametrize("nombre,cuadros", RUTAS,
                         ids=[caso[0] for caso in RUTAS])
def test_ruta(nombre, cuadros):
    """`ruta`: una ruta forzada sobre el héroe, en varios ticks.

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

    """
    for cuadro in cuadros:
        p = partida(nombre)
        x, y = p.heroe()
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())
        if (nombre, cuadro) in BAJO_EN_EL_TICK:
            abajo, velocidad = BAJO_EN_EL_TICK[nombre, cuadro]
            assert (p.heroe(), p.velocidad_del_heroe()) == (
                (x, y + abajo), velocidad), (
                "%s en el tick %d: el héroe tiene que haber bajado %d celdas "
                "desde %s y tener velocidad %d, y está en %s con %d"
                % (nombre, cuadro, abajo, (x, y), velocidad, p.heroe(),
                   p.velocidad_del_heroe()))


# Dónde está el héroe, y a qué velocidad, en los ticks de `ruta-vel` y
# `ruta-vel-lenta` que la foto no distingue: el mapa 6 es una grilla que se
# repite y la cámara sigue al héroe, así que parado entre dos pasos se ve
# **igual que sin ruta** —esos ticks son byte por byte `6-none`—. Las celdas
# son las de la ruta (5 y 4 para abajo) y la velocidad la que deja: RM2k repone
# la frecuencia al terminar y no la velocidad, así que `ruta-vel` vuelve a 4
# con su 29 y `ruta-vel-lenta` queda en 5.
BAJO_EN_EL_TICK = {
    ("ruta-vel", 30): (5, 4), ("ruta-vel", 44): (5, 4),
    ("ruta-vel", 60): (5, 4), ("ruta-vel", 80): (5, 4),
    ("ruta-vel-lenta", 64): (2, 2), ("ruta-vel-lenta", 90): (4, 5),
    ("ruta-vel-lenta", 120): (4, 5), ("ruta-vel-lenta", 200): (4, 5),
}


@pytest.mark.parametrize("cuadro", (89, 91))
def test_ruta_evento(cuadro):
    """`ruta-evento`: un evento **sin gráfico** caminando su ruta.

    Es lo que `MoveEvent` agrega sobre otro evento. Como el evento no se ve,
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
    p = partida("ruta-evento")
    p.correr(cuadro)
    golden("ruta-evento-%d" % cuadro, p.imagen())


# Un evento con gráfico caminando: nombre —el de su caso, que lleva el
# `Teleport` al mapa y a la celda del héroe, la ruta y la frecuencia de la
# página— y los ticks.
NPCS = (
    ("npc", (10, 27, 40, 60)),
    ("npc-lento", (20, 44, 88, 100, 200)),
    ("npc-encara", (5, 30)),
    ("npc-encara-lado", (5, 30)),
    ("npc-frec", (20, 40, 60, 80)),
    ("salto-npc", (3, 6, 10, 14, 20, 40)),
    ("npc-diagonal", (10, 25, 40, 70)),
    ("npc-diagonal-gira", (20, 40)),
    ("npc-hacia-heroe", (5, 25, 44, 70)),
)


@pytest.mark.parametrize("nombre,cuadros", NPCS,
                         ids=[caso[0] for caso in NPCS])
def test_npc(nombre, cuadros):
    """`npc`: un evento **con gráfico** caminando en pantalla.

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
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# La orden 34 de ruta: nombre, ruta, el gráfico al que cambia y los ticks.
GRAFICOS = (
    ("grafico", "Future1 0", (10, 25, 40, 70)),
    ("invisible", "nobodyhere 0", (10, 25, 40, 70)),
    ("grafico-heroe", "Future1 0", (10, 20, 25, 40)),
    ("heroe-invisible", "nobodyhere 0", (10, 25, 40)),
)


@pytest.mark.parametrize("nombre,grafico,cuadros", GRAFICOS,
                         ids=[caso[0] for caso in GRAFICOS])
def test_grafico(nombre, grafico, cuadros):
    """`grafico`: un personaje que cambia de gráfico a mitad de una ruta.

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
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


LUGARES = (("lugar", (14, 15, 20, 60)),
           ("lugar-quieto", (10, 60)))


@pytest.mark.parametrize("nombre,cuadros", LUGARES,
                         ids=[caso[0] for caso in LUGARES])
def test_lugar(nombre, cuadros):
    """`lugar`: plantar a un evento en una celda, `ChangeEventLocation`.

    Es `MoveTo`, y la vuelta que tiene está en lo que **no** hace: no toca la
    ruta ni hacia dónde mira, y corta el paso en curso —`SetRemainingStep(0)`—.
    Los dos casos son plantarlo a mitad de su ruta, donde tiene que seguir con
    los pasos que le quedaban desde la celda nueva, y plantarlo sin ruta
    ninguna.

    **Las celdas son del piso marrón a la vista y no da lo mismo**: plantado
    donde lo tapa la capa de encima se dibuja escondido, y la prueba daba
    cero con el corte del paso sacado. Los ticks tampoco son los de
    la espera: `OP_DELAY n` suelta la página en el cuadro n+2, y elegidos a ojo
    caían antes del corte.
    """
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


@pytest.mark.parametrize("cuadro", (20, 26, 34, 40))
def test_parar_rutas(cuadro):
    """`parar`: `HaltAllMovement`, todas las rutas abandonadas de golpe.

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
    —o sea el comando aceptado y no hecho—: 59,89% en el
    cuadro 34.

    **Los ticks llegan hasta el 40 y no más lejos a propósito**: ver el aviso
    de los tiles animados en la cabecera de este archivo.
    """
    p = partida("parar-rutas")
    p.correr(cuadro)
    golden("parar-rutas-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("cuadro", (10, 30))
def test_sprite_actor(cuadro):
    """`sprite-actor`: el CharSet de un **actor**, cambiado en caliente.

    Es `ChangeSpriteAssociation`, y es lo que traba la persecución en auto,
    donde el héroe *es* el auto: los mapas de la carrera sacan a todo el grupo
    y meten a `CarRED` o `CarBLUE`. La página de prueba le cambia el CharSet al
    líder **después de la espera**, así que el tick de antes lo mira con el
    gráfico del LDB y el de después con el nuevo.

    `--grafico-de-prueba` va junto y no es redundante: el comando de la página
    reserva la ranura de la tabla de gráficos en **todos** los mapas —es lo que
    hace que el índice signifique lo mismo después de un salto— y el flag es el
    que le mete las poses al banco de sprites del mapa.

    Lo que este caso **no** mira: que el cambio sobreviva al teletransporte.
    Eso lo cobra `pruebas/rpgmaker/test_sprite_actor.py`.
    """
    p = partida("sprite-actor")
    p.correr(cuadro)
    golden("sprite-actor-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("cuadro", (21, 23, 50, 130))
def test_anclada(cuadro):
    """`anclada`: la ventana de mensaje quieta con el mapa scrolleando.

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
    p = partida("anclada")
    p.correr(cuadro)
    golden("anclada-%d" % cuadro, p.imagen())


PISADAS = (("ruta-pisa", (16, 24, 200)),
           ("ruta-pasa", (100, 200)),
           ("ruta-pisa-cola", (50, 200)))


@pytest.mark.parametrize("nombre,cuadros", PISADAS,
                         ids=[caso[0] for caso in PISADAS])
def test_ruta_pisa(nombre, cuadros):
    """`ruta-pisa`: una ruta forzada que termina sobre un evento de
    contacto, y otra que le pasa por encima.

    Es el disparo que le faltaba a la cinemática de apertura. La regla es la de
    `Game_Player::UpdateMovement`: al terminar un paso se mira la celda **salvo
    que el héroe tenga una ruta forzada puesta**, y un movimiento que es la
    última orden de la ruta la cancela entera antes de ese chequeo. O sea: los
    pasos del medio no pisan nada, el último sí.

    Los tres son en el mapa 70: una ruta que termina sobre el evento y abre el
    mensaje, una que **pasa** por encima y no abre nada, y una que termina con
    la página todavía corriendo —RM2k no pierde el contacto: lo deja esperando
    y lo corre cuando la página termina—.
    """
    for cuadro in cuadros:
        p = partida(nombre)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())


# Nombre —el de su caso, con el `Teleport` al mapa y a la celda— y hacia
# dónde camina.
PISAR = (("pisar", "up"),
         ("atravesar-cofre", "left"),
         ("atravesar-savept", "left"))


@pytest.mark.parametrize("nombre,direccion", PISAR,
                         ids=[caso[0] for caso in PISAR])
def test_pisar(nombre, direccion):
    """`pisar`: el héroe camina con el pad y pisa un evento de contacto.

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
    p = partida(nombre)
    p.correr(200, sosteniendo=(direccion,))
    golden(nombre, p.imagen())
