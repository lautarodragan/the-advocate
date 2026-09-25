"""El minijuego de las piedras del `Lazer Teeth HQ`, jugado de punta a punta.

Es la única prueba que dice que **el minijuego anda**, y por eso existe: la
tanda de pixeles cubre las piezas —`tecla-dir` el `KeyInputProc` que espera la
cruceta, `lugar-var` el `ChangeEventLocation` por variables— pero ninguna de
las dos las junta, y era la suma la que taro reportó rota ("no puedo lanzar las
piedras").

Lo que hace la página, `EV0017` del mapa 11, y lo que se comprueba acá:

    var 4       cuántas piedras quedan. `Grate1` la pone en 3 y la página le
                resta una en cada vuelta
    var 5       la tecla de acción, del primer `KeyInputProc`
    vars 6 y 7  la celda del héroe, que es donde la piedra aparece
    var 8       la dirección, del segundo `KeyInputProc` — la que no compilaba
    `Stone`     el evento 18, que se planta en (var 6, var 7) y después camina

O sea que esto ejercita las tres cosas que trababan la página: la ranura de la
variable 5, la espera de la cruceta y `OP_PLACE_VAR`. **Con cualquiera de las
tres sacada la página no compila**, y entonces `test_con_a_y_una_direccion_la_
piedra_sale_volando` se cae en el primer `assert` con la variable 5 en cero.
Verificado así el 2026-09-13, volviendo a poner el corte de `KEY_INPUT_PROC`.
Las otras dos no se caen, y está bien que no se caigan: la reja no depende de
la página, y "una dirección sola no tira nada" es verdad de más cuando el
minijuego no corre. Son el control, no la medición.

El orden de los toques importa y es el del juego: A primero, y la dirección
**algunos ticks después**. Un toque de dirección sin la A antes no tira nada
—lo mueve al héroe y nada más—, que es lo que dice el cartel del original
("I'll have to be careful about pressing the OK button...").
"""

from port import eventos

from piedras import (DEBAJO_DE_LA_REJA, MAPAS, STONE, celda_de,
                     eventos_del_11, hablarle_a_la_reja, ranura)


def test_la_reja_da_tres_piedras(partida):
    """La mitad que ya andaba, y que taro confirmó jugando. Está acá porque es
    lo que la otra prueba da por sentado."""
    p = hablarle_a_la_reja(partida(caso=MAPAS))
    assert p.switch(43), (
        "hablarle a la reja tiene que prender el switch 43, que es lo que "
        "activa el motor del minijuego")
    # Tres, o dos: el motor arranca en el mismo cuadro y su primer comando le
    # resta una. Lo que importa es que las tenga, no el borde de un tick.
    assert p.variable(ranura(4)) in (2, 3), (
        "la variable 4 tendría que traer las tres piedras y quedó en %d"
        % p.variable(ranura(4)))


def test_con_a_y_una_direccion_la_piedra_sale_volando(partida):
    """Lo que taro reportó roto.

    Los ticks entre la A y la dirección no son a ojo: entre las dos el
    intérprete corre trece comandos —el `MoveEvent`, las seis `ControlVars` de
    coordenadas y los cinco `ChangeEventLocation`— y después el
    `KeyInputProc` de la dirección se emite **dos veces**, así que la primera
    vuelta se come el flanco. Cuatro ticks sobran y no llegan a la vuelta
    siguiente de la página.
    """
    p = hablarle_a_la_reja(partida(caso=MAPAS))
    p.correr(4)
    assert p.variable(ranura(8)) == 0, (
        "antes de apretar nada la dirección tendría que estar en cero")
    lejos = celda_de(p, STONE)
    assert lejos != DEBAJO_DE_LA_REJA

    p.tocar("a")
    assert p.variable(ranura(5)) == eventos.TECLA_VALOR_DECISION, (
        "el primer KeyInputProc tendría que haber leído la tecla de acción, y "
        "la variable 5 quedó en %d" % p.variable(ranura(5)))
    # El héroe sigue mirando a la reja, que es un evento de acción. La A es
    # del motor y de nadie más: el `KeyInputProc` de la dirección, que el
    # motor ejecuta en ese mismo tick, hace `Input::ResetTriggerKeys()` y el
    # héroe ya no ve el flanco. Si lo viera, la reja volvería a hablar.
    assert not p.byte("ev_activo") and not p.byte("msg_estado"), (
        "la A que prepara la piedra le habló también a la reja")
    assert (p.variable(ranura(6)), p.variable(ranura(7))) == DEBAJO_DE_LA_REJA, (
        "las variables 6 y 7 tendrían que traer la celda del héroe")
    assert celda_de(p, STONE) == DEBAJO_DE_LA_REJA, (
        "la piedra tendría que estar plantada encima del héroe y está en %s. "
        "Es el `ChangeEventLocation` por variables, o sea OP_PLACE_VAR"
        % (celda_de(p, STONE),))

    p.correr(4)
    p.tocar("left")
    assert p.variable(ranura(8)) == eventos.TECLA_VALOR_DIR[3], (
        "el segundo KeyInputProc tendría que haber leído izquierda —2 en "
        "`CheckInput`— y la variable 8 quedó en %d" % p.variable(ranura(8)))
    p.correr(20)
    x, y = celda_de(p, STONE)
    assert y == DEBAJO_DE_LA_REJA[1] and x < DEBAJO_DE_LA_REJA[0] - 2, (
        "la piedra tendría que haberse ido para la izquierda y está en %s"
        % ((x, y),))
    assert (p.palabra("tile_x"), p.palabra("tile_y")) == DEBAJO_DE_LA_REJA, (
        "el héroe no se mueve mientras la piedra vuela: la página le fuerza "
        "la ruta")


def test_una_direccion_sola_no_tira_nada(partida):
    """La otra mitad, y la que hace significar a la de arriba: sin la A antes,
    la dirección camina al héroe y la piedra se queda donde está.

    Sin esto, un caso que apretara A y dirección juntos daría verde con un
    `KeyInputProc` que contestara cualquier cosa."""
    p = hablarle_a_la_reja(partida(caso=MAPAS))
    p.correr(4)
    lejos = celda_de(p, STONE)
    p.tocar("left")
    p.correr(20)
    assert p.variable(ranura(8)) == 0, (
        "sin apretar A antes, la dirección no la tiene que leer nadie: la "
        "variable 8 quedó en %d" % p.variable(ranura(8)))
    assert celda_de(p, STONE) == lejos, (
        "la piedra se movió sin que nadie la tirara: está en %s"
        % (celda_de(p, STONE),))
    assert p.palabra("tile_x") == DEBAJO_DE_LA_REJA[0] - 1, (
        "el héroe sí tiene que haber caminado una celda para la izquierda")


# Desde acá, tirando hacia arriba, la piedra le pega a la PC de (19,44) —el
# `LTComputer`, EV35— y su página paralela abre el mensaje del guardia.
FRENTE_A_LA_PC = (19, 52)
# Cuántos ticks puede tardar la piedra en llegar y el mensaje en abrirse.
# Medido: unos noventa.
TOPE_HASTA_EL_MENSAJE = 300


def tirarle_a_la_pc(p):
    """Tira una piedra hacia arriba desde `FRENTE_A_LA_PC` y vuelve con el
    mensaje del guardia abierto y el motor de nuevo esperando la A."""
    p.ir_al_mapa(11, *FRENTE_A_LA_PC)
    p.correr(10)
    p.tocar("a")
    p.correr(4)
    p.tocar("up")
    for _ in range(TOPE_HASTA_EL_MENSAJE):
        if p.byte("msg_abierto"):
            break
        p.correr(1)
    else:
        raise AssertionError(
            "la piedra tirada hacia arriba tendría que haber roto la PC y "
            "abierto el mensaje del guardia")
    # Que el motor termine su vuelta —la piedra vuela y vuelve a su lugar— y
    # quede otra vez parado en el `KeyInputProc` de la A, que es donde el
    # toque que cierra el mensaje lo encontraba.
    p.correr(90)
    assert p.byte("msg_abierto"), "el mensaje se cerró sin que nadie tocara A"
    return p


def test_la_a_que_cierra_el_mensaje_no_saca_una_piedra(partida):
    """Lo que taro reportó: el A que cierra el mensaje de la PC rota también
    preparaba la piedra siguiente, así que siempre se perdía una.

    El motor es paralelo y sigue corriendo con el mensaje abierto, como en
    RM2k; lo que RM2k no hace es dejarle a un `KeyInputProc` que espera leer
    el pad mientras haya un mensaje activo, de quien sea
    (`game_interpreter.cpp:470-473` de easyrpg)."""
    p = tirarle_a_la_pc(hablarle_a_la_reja(partida(caso=MAPAS)))
    lejos = celda_de(p, STONE)
    assert lejos != FRENTE_A_LA_PC

    p.tocar("a")
    assert not p.byte("msg_abierto"), "el toque de A tendría que cerrarlo"
    p.correr(30)
    assert p.variable(ranura(5)) == 0, (
        "el A que cerró el mensaje lo leyó también el motor de las piedras: "
        "la variable 5 quedó en %d" % p.variable(ranura(5)))
    assert celda_de(p, STONE) != FRENTE_A_LA_PC, (
        "el A que cerró el mensaje preparó una piedra sobre el héroe")

    # El control: sin mensaje, la A siguiente sí es del motor. Sin esto, un
    # motor que dejara de leer la A para siempre daría verde arriba.
    p.tocar("a")
    assert p.variable(ranura(5)) == eventos.TECLA_VALOR_DECISION, (
        "con el mensaje cerrado, la A siguiente tendría que preparar la "
        "piedra, y la variable 5 quedó en %d" % p.variable(ranura(5)))
    assert celda_de(p, STONE) == FRENTE_A_LA_PC


# Al lado de `EV0060`, que es un evento de acción en (22,44): tirando hacia la
# izquierda la piedra pasa por la PC de (19,44), y el héroe se da vuelta a
# mirar al evento mientras la piedra vuela.
AL_LADO_DE_EV0060 = (21, 44)
EV0060 = 60


def test_la_a_que_cierra_el_mensaje_no_le_habla_al_de_enfrente(partida):
    """El A que cierra un mensaje queda consumido: el héroe no lo ve.

    El mensaje es de un paralelo —el de la PC rota—, así que al cerrarlo no
    queda ninguna página de primer plano corriendo y `eventos_tick` sigue de
    largo hasta `probar_accion` en el mismo cuadro, con el flanco de A
    todavía ahí. En RM2k eso no pasa: el mensaje sigue "activo" unos ocho
    cuadros después de cerrarse, mientras se anima el cierre, y con un
    mensaje activo el héroe no busca eventos de acción (easyrpg
    `game_player.cpp:297`)."""
    p = hablarle_a_la_reja(partida(caso=MAPAS))
    p.ir_al_mapa(11, *AL_LADO_DE_EV0060)
    p.correr(10)
    p.tocar("a")
    p.correr(4)
    p.tocar("left")
    # Mientras vuela, el héroe se da vuelta hacia el evento. No camina: el
    # evento ocupa la celda.
    p.correr(20)
    p.tocar("right")
    assert (p.palabra("tile_x"), p.palabra("tile_y")) == AL_LADO_DE_EV0060
    assert p.byte("hero_dir") == p.simbolos["DIR_RIGHT"], (
        "el héroe tendría que mirar a EV0060")
    assert eventos_del_11().para(1).blanco(EV0060)
    for _ in range(TOPE_HASTA_EL_MENSAJE):
        if p.byte("msg_abierto"):
            break
        p.correr(1)
    else:
        raise AssertionError(
            "la piedra tirada hacia la izquierda tendría que haber roto la PC")
    p.correr(60)
    assert p.byte("msg_abierto")
    assert not p.byte("ev_activo"), (
        "el mensaje es del paralelo: no tendría que haber una página de "
        "primer plano corriendo")

    p.tocar("a")
    assert not p.byte("msg_abierto"), "el toque de A tendría que cerrarlo"
    assert not p.byte("ev_activo") and not p.byte("msg_estado"), (
        "el A que cerró el mensaje le habló también a EV0060, que el héroe "
        "tenía enfrente")


# Los dos switches que prende la pág. 3 de `LTSentry1` —el guardia que viene a
# ver qué pasó— **después** de su propio mensaje: el 46 y el 51.
SWITCHES_DEL_GUARDIA = (46, 51)


def test_un_paralelo_espera_a_su_propio_mensaje(partida):
    """La tercera divergencia de los mensajes, y la que quedó para el final.

    Un intérprete paralelo sigue corriendo con un mensaje en pantalla —para
    eso existe— **salvo que el mensaje sea suyo**: el guard de
    `Game_Interpreter::Update` es `IsMessageActive() && _state.show_message`
    (easyrpg `game_interpreter.cpp:434-441`). Acá el paralelo del guardia
    abría su mensaje y seguía de largo en el mismo cuadro, así que los dos
    switches que van detrás del `ShowMessage` se prendían **un tick después de
    que el mensaje empezara a componerse**, con el texto todavía en pantalla,
    y el guardia arrancaba a caminar mientras hablaba.
    """
    p = tirarle_a_la_pc(hablarle_a_la_reja(partida(caso=MAPAS)))
    for numero in SWITCHES_DEL_GUARDIA:
        assert not p.switch(numero), (
            "el switch %d está prendido con el mensaje del guardia todavía "
            "abierto: su paralelo siguió corriendo detrás de su propio "
            "`ShowMessage`" % numero)

    p.tocar("a")
    assert not p.byte("msg_abierto"), "el toque de A tendría que cerrarlo"
    p.correr(10)
    for numero in SWITCHES_DEL_GUARDIA:
        assert p.switch(numero), (
            "cerrado el mensaje, el paralelo tiene que seguir donde estaba y "
            "prender el switch %d; quedó apagado" % numero)
