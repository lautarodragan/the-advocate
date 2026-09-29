"""Perder una pelea sin manejador de derrota es la pantalla de Game Over.

En RM2k un `EnemyEncounter` con `defeat_mode` 0 no trae bloque de manejadores:
perder no es una rama de la página sino `Scene_Gameover`, o sea la imagen de
Game Over y, al apretar, la pantalla de título. Son **15 páginas del juego**,
y entre ellas las tres del `EV0006` del mapa 26, que es el jefe de los Rat
Tracks.

Compilan con el destino de la derrota puesto en `eventos.BATALLA_PERDER`
—$FFFF, un destino imposible adentro de una página—; la ROM lo anota antes de
pelear y, si se pierde, muestra la pantalla y al apretar A se va con un `jml
reset`. Ver runtime/game_over.s.

Lo que se ve se mira contra una golden, `game-over`, que es la misma para los
tres caminos —la pelea de página, el encuentro al azar y el comando—; lo
demás es estado: que la ROM espere la tecla, se reinicie y vuelva a correr.
Sin estas pruebas, el `jml reset` sería exactamente lo que AGENTS.md llama "un
camino que ninguna prueba ejecuta".

**Cómo se pierde sin pelear**: con todo el grupo en cero HP, `batalla_correr`
contesta derrota antes de abrir la pantalla —el `ba_actor_siguiente` que
devuelve $FF, "nadie en pie: se pierde sin pelear"—. Así la prueba no depende
de ningún tiro de dado.

El control es el mismo caso con la derrota apuntando al final del bloque, que
es lo que emiten las peleas con manejadores: ahí la ROM **no** se reinicia y la
página sigue. Sin él, un reinicio por cualquier otra causa —una pelea que
cuelgue, una pila que se desborde— pasaría por verde.
"""

from port import eventos

from batalla import (TITULO_QUIETO, VOLVER_TOPE, con_encuentros,
                     cuadros_hasta_el_game_over, cuadros_hasta_volver,
                     pasar_el_titulo,
                     cuadros_hasta_reiniciar, en_el_game_over,
                     pasar_el_game_over, sin_hp)
from datos import pagina_de
from tanda import golden

# Las páginas de prueba `pelea-82` y `pelea-82-game-over` pelean contra la
# tropa del droide del mapa 2, que es la que ya viaja en los cartuchos de
# prueba: cuál sea da lo mismo, porque nadie llega a pelearla. Esperan 18
# ticks antes de abrir la pelea, que son los que la prueba usa para poner los
# HP en cero; con menos, la pelea se abre antes de que la escritura llegue.

# El jefe de los Rat Tracks, que es lo que todo esto destraba.
RAT_TRACKS_B2, JEFE = 26, 6
# Y el cofre trampa de los Rat Tracks B1, que es la otra de las 15 páginas que
# taro se encontró jugando: el `RatTrackChest6c`, que en vez de un ítem trae
# tres GiantRat y no deja huir. Ver `test_el_cofre_trampa_compila`.
RAT_TRACKS_B1, COFRE_TRAMPA = 21, 20
# Los cuadros de hardware que se le dan a la pantalla de Game Over para llegar
# a esperar la tecla: el fundido de la pelea o del mapa, subir su tema y su
# imagen, y los 80 del fundido de entrada. Desde la pelea es lo más largo, y
# con esto sobra más del doble.
GAME_OVER_TOPE = 600


def la_pantalla(una):
    """La pantalla de Game Over esperando la tecla, contra su golden. Es la
    misma para los tres caminos que llegan a ella."""
    assert cuadros_hasta_el_game_over(una, GAME_OVER_TOPE) is not None, (
        "la pantalla de Game Over no llegó a esperar la tecla en %d cuadros"
        % GAME_OVER_TOPE)
    una.consola.correr(2)
    golden("game-over", una.imagen())


def pasar_el_arranque(una):
    """Del otro lado de un reinicio de la ROM, los cuadros del arranque: los
    mismos que corre `Partida` al encender, `BOOT_CUADROS` y tres, con la
    pantalla de título en el medio si el cartucho la tiene."""
    pasar_el_titulo(una)
    una.consola.correr(3)


# --- lo que se emite -------------------------------------------------------

def pagina_del_jefe(numero):
    """La página `numero` del evento del jefe de los Rat Tracks, compilada."""
    return pagina_de(RAT_TRACKS_B2, JEFE, numero)


def test_las_tres_paginas_del_jefe_compilan():
    """Las tres del `EV0006` del mapa 26, que son las que taro no podía ver.

    Su `EnemyEncounter` viene con `escape_mode` 0 y `defeat_mode` 0, o sea sin
    bloque de manejadores: son las dos cosas que hasta el 2026-09-13 la cortaban
    —una el `raise` del Game Over y la otra "una batalla sin cerrar"— y por eso
    destrabar una sola daba cero páginas.
    """
    for numero in (0, 1, 2):
        assert pagina_del_jefe(numero) is not None, (
            "la página %d del jefe de los Rat Tracks no compila" % numero)


def test_la_derrota_del_jefe_apunta_al_game_over():
    """Y el destino que se emite es `BATALLA_PERDER`, no el comando siguiente.

    Es lo que separa "el jefe aparece" de "el jefe aparece y perder no pasa
    nada": sin esto la página seguiría como si hubiera ganado, que es
    exactamente la clase de mentira que el `raise` estaba evitando.
    """
    codigo = pagina_del_jefe(0)
    peleas = [i for i, b in enumerate(codigo) if b == eventos.OP_BATTLE]
    # El opcode puede aparecer como operando de otro comando, así que se busca
    # el que además lleva la tropa que el LDB dice.
    for i in peleas:
        if codigo[i + 1] | (codigo[i + 2] << 8) != 97:
            continue
        derrota = codigo[i + 7] | (codigo[i + 8] << 8)
        assert derrota == eventos.BATALLA_PERDER, (
            "la derrota de la pelea del jefe va a %d y tendría que ser el "
            "Game Over" % derrota)
        return
    raise AssertionError("la página del jefe no emite ninguna pelea")


# --- y lo que la consola hace con eso --------------------------------------

def test_perder_sin_manejador_muestra_el_game_over(partida):
    """`game-over`: la pantalla, y hasta que no se aprieta no pasa nada."""
    una = partida(caso="pelea-82-game-over")
    sin_hp(una)
    la_pantalla(una)
    # Y su tema, por el SPC700 —la tanda corre sin MSU-1—, con las muestras
    # arriba: el paquete de la pantalla, que se sube desde el de la pelea.
    tema = una.simbolos["TEMA_GAME_OVER"]
    assert una.byte("tema_actual") == tema and not una.byte("music_apagada"), (
        "la pantalla de Game Over no prendió su tema")
    faltan = set(una.muestras_del_tema(tema)) - una.muestras_en_la_aram()
    assert not faltan, (
        "el tema de Game Over suena sin las muestras %s en la ARAM"
        % sorted(faltan))
    assert cuadros_hasta_reiniciar(una, tope=300) is None, (
        "la pantalla de Game Over se fue sola, sin que nadie apretara")
    assert en_el_game_over(una)


def test_perder_sin_manejador_vuelve_al_arranque(partida):
    una = partida(caso="pelea-82-game-over")
    sin_hp(una)
    cuando = pasar_el_game_over(una, GAME_OVER_TOPE)
    assert cuando is not None, (
        "la ROM mostró el Game Over, se apretó A, y no se reinició: el "
        "fundido de salida no llega a `reset`")
    # Y lo que hay del otro lado del reinicio es el arranque de siempre: la
    # cuenta de cuadros vuelve a empezar y el mapa es el primero de la tabla.
    pasar_el_arranque(una)
    assert una.palabra("mapa_actual") == 0


def test_perder_con_manejador_no_es_game_over(partida):
    """El control. Misma pelea perdida, con la derrota apuntando a la página."""
    una = partida(caso="pelea-82")
    sin_hp(una)
    assert cuadros_hasta_el_game_over(una, tope=300) is None, (
        "la ROM mostró el Game Over con una pelea que sí tiene a dónde "
        "volver: entonces el del otro caso no lo causa BATALLA_PERDER")
    assert cuadros_hasta_reiniciar(una, tope=60) is None


def test_el_cofre_trampa_compila():
    """El `RatTrackChest6c` del mapa 21, que es por donde taro se cayó.

    Es la otra cara del jefe: mismo `defeat_mode` 0, y además
    `ChangeEscapeAccess` con la huida prohibida, así que perder es la única
    salida que la página tiene. Está acá para que se sepa **cuál** es el cofre
    del que habla `test_el_game_over_vuelve_al_juego`: sin esto, el día que
    alguien toque `tropa_de_encuentro` el cuelgue vuelve por un camino que
    ninguna prueba nombra.
    """
    assert pagina_de(RAT_TRACKS_B1, COFRE_TRAMPA, 0) is not None


def test_el_game_over_vuelve_al_juego(partida):
    """Y del otro lado del reinicio **el juego corre**, que es lo que faltaba.

    `test_perder_sin_manejador_vuelve_al_arranque` mira que `vueltas` se vaya
    para atrás, o sea que el `jml reset` haya salido; con eso alcanzaba para
    creer que el Game Over andaba, y no andaba. El arranque se quedaba clavado
    en `spc_upload`, esperando el $AA/$BB de una ROM de IPL que ya no corría:
    el botón de reset de la consola resetea al SPC700 —la línea les llega a los
    dos— y un `jml` de adentro del juego no. La pantalla quedaba encendida con
    el mapa dibujado y el juego muerto, que es lo que taro reportó del cofre
    trampa de los Rat Tracks como "pantalla en negro, softlock o crash".

    `mapa_actual` no lo ve: `cargar_mapa` corre **antes** de la subida al
    SPC700. Lo único que dice que el arranque terminó es que el lazo vuelva a
    contar vueltas.
    """
    una = partida(caso="pelea-82-game-over")
    sin_hp(una)
    assert pasar_el_game_over(una, GAME_OVER_TOPE) is not None, (
        "la ROM no se reinició: sin Game Over esto no prueba nada")
    assert cuadros_hasta_volver(una) is not None, (
        "la ROM se reinició y no volvió a correr en %d cuadros: el arranque "
        "se colgó, y el sospechoso es la subida al SPC700 esperando un IPL "
        "que ya no está" % VOLVER_TOPE)


# --- y el otro camino a una pelea: el encuentro al azar ---------------------
#
# En una página, `op_battle` anota el destino de la derrota y `BATALLA_PERDER`
# la manda a la pantalla de Game Over. El encuentro al azar arranca la pelea
# **sin bytecode** —`pelea_arrancar` desde `move_hero`—, así que no hay
# `op_battle` que anote nada: si nadie más lo hace, perder devuelve el control
# al mapa.
#
# Lo que eso deja puesto es lo que taro reportó jugando: el grupo vuelve al
# mapa con todos en cero HP, `modo_fin` los guarda así en `FAR_HP`, y de ahí en
# más **cada pelea se pierde sola antes de abrirse**, porque `batalla_correr`
# contesta derrota con nadie en pie. O sea que los tres síntomas —no hay Game
# Over, el grupo queda en cero, y toda pelea siguiente se pierde— son este solo
# defecto.
#
# Un encuentro al azar no puede traer manejador de derrota: no hay página que
# lo emita. Así que la derrota es siempre Game Over, como en RM2k.

# Los encuentros salen cada ocho pasos, en vez de los 80 que dice el árbol:
# con los de verdad la prueba caminaría minutos. Es el `--encuentros-de-prueba`
# de `test-special`, el mismo que usa el caso `encuentro` de la tanda.
#
# El grupo lo arma la página de prueba `grupo-11-12-13`: el de la intro, que
# **gana** las peleas de ese mapa en un turno, y es lo que hace que el control
# no dependa de ningún tiro de dado. Medido el 2026-09-13: contra las tropas
# 94, 95 y 96 el enemigo cae siempre en el primer turno y el grupo no pierde
# un solo HP.
DIRECCIONES = ("up", "down", "left", "right")


def caminar(una, cuadros, tope_sin_reinicio=False):
    """Camina con el pad en cuadros de hardware y dice en cuál llegó al Game
    Over —o se reinició, que sin la pantalla era lo mismo—.

    No se puede caminar por ticks: la pelea corre su propio lazo y `vueltas`
    no avanza mientras dura, así que `_un_tick` se quedaría esperando. Se
    cambia de dirección cada cuarenta cuadros para no clavarse contra una
    pared del mapa.
    """
    alto = una.palabra("vueltas")
    for n in range(cuadros):
        una.consola.apretar(DIRECCIONES[(n // 40) % 4])
        una.consola.correr(1)
        ahora = una.palabra("vueltas")
        if ahora + 5 < alto or en_el_game_over(una):
            una.consola.apretar()
            return n
        alto = max(alto, ahora)
    una.consola.apretar()
    return None


def test_perder_un_encuentro_al_azar_es_game_over(partida):
    """Con el grupo caído, el primer encuentro tiene que ser la pantalla de
    Game Over, y de ahí el arranque."""
    una = con_encuentros(partida)
    sin_hp(una)
    cuando = caminar(una, 900)
    assert cuando is not None, (
        "se perdió un encuentro al azar y la ROM siguió en el mapa: la "
        "derrota de una pelea que nadie arrancó desde una página también "
        "tiene que ser Game Over")
    la_pantalla(una)
    assert pasar_el_game_over(una, GAME_OVER_TOPE) is not None
    pasar_el_arranque(una)
    assert una.palabra("mapa_actual") == 0


def test_ganar_encuentros_al_azar_no_reinicia(partida):
    """El control: el mismo mapa y el mismo grupo, con los HP que trae.

    Sin él, un reinicio por cualquier otra causa —una pila que se desborde al
    entrar a la pelea, un cuelgue— pasaría por Game Over verificado.
    """
    una = con_encuentros(partida)
    assert caminar(una, 900) is None, (
        "la ROM se reinició ganando encuentros al azar")


# --- y el `GameOver` de una página -----------------------------------------
#
# Compila a OP_GAME_OVER, que lleva a la misma pantalla que el destino
# `BATALLA_PERDER`, fundiendo antes el mapa. La página de prueba `game-over`
# espera 18 ticks y lo llama; el control es `pelea-82`, que tampoco llega —ver
# `test_perder_con_manejador_no_es_game_over`— y el de `curar-sumar`, abajo.

def test_game_over_muestra_la_pantalla(partida):
    """`game-over`, desde el comando: la misma golden que perdiendo."""
    la_pantalla(partida(caso="game-over"))


def test_game_over_vuelve_al_titulo(partida):
    """Y al apretar, la pantalla de título, igual que al encender: la golden
    `titulo`. `release` la lleva, así que del otro lado del reinicio el juego
    no corre hasta que alguien elige."""
    una = partida(caso="game-over")
    assert pasar_el_game_over(una, GAME_OVER_TOPE) is not None, (
        "la página llamó a GameOver, se apretó A, y la ROM no se reinició")
    una.consola.correr(TITULO_QUIETO)
    golden("titulo", una.imagen())
    assert cuadros_hasta_volver(una) is not None, (
        "después del GameOver el arranque no volvió a correr en %d cuadros"
        % VOLVER_TOPE)
    assert una.palabra("mapa_actual") == 0


def test_sin_game_over_no_reinicia(partida):
    """El control: el mismo mapa y la misma espera, sin el comando."""
    una = partida(caso="curar-sumar")
    assert cuadros_hasta_el_game_over(una, tope=300) is None
    assert cuadros_hasta_reiniciar(una, tope=60) is None


# --- `ReturntoTitleScreen` ---------------------------------------------------
#
# Hasta el 2026-09-28 compartía opcode con `GameOver`, cuando ninguno de los
# dos dibujaba nada. Ahora es `OP_RETURN_TO_TITLE`, y tiene que seguir yendo
# derecho al título: sin la pantalla de Game Over.

def test_volver_al_titulo_no_pasa_por_el_game_over(partida):
    una = partida(caso="volver-al-titulo")
    visto = False
    for _ in range(300):
        visto = visto or en_el_game_over(una)
        antes = una.palabra("vueltas")
        una.consola.correr(1)
        if una.palabra("vueltas") < antes:
            break
    else:
        raise AssertionError("la página llamó a ReturntoTitleScreen y la ROM "
                             "siguió en el mapa")
    assert not visto, "ReturntoTitleScreen pasó por la pantalla de Game Over"
    assert cuadros_hasta_volver(una) is not None
