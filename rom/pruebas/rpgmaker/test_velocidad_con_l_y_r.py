"""L y R: R sube la velocidad del héroe y L la baja, de 1 a 6.

No es de RM2k —ver `workflow/divergencias/la-velocidad-del-heroe-con-l-y-r.md`
y `hero_speed_keys.s` en el runtime—. Lo que se mide es lo que se ve: **cuántos
cuadros tarda el héroe en cruzar una celda** con el pad, desde que arranca el
paso hasta que llega. RM2k cruza una celda en 256 unidades a `STEP_PER_SPEED`
por cuadro: 64, 32, 16, 8, 4 y 2 cuadros de la velocidad 1 a la 6.

Las cuentas son en cuadros de hardware y no en ticks: el paso avanza una vez
por vuelta del lazo, y en `en-5`, parado y sin nada enfrente, cada vuelta es un
cuadro.
"""

import tanda
import events

# Lo que tarda una celda a cada velocidad, de RM2k.
CUADROS = {v: events.JUMP_STEP // events.STEP_PER_SPEED[v - 1]
           for v in range(1, 7)}


def tocar(una, boton, veces=1):
    """`veces` toques de `boton`, de a un cuadro apretado y uno suelto: la
    ROM mira el flanco en cada cuadro."""
    for _ in range(veces):
        una.consola.hold(boton)
        una.consola.run(1)
        una.consola.hold()
        una.consola.run(1)


def cuadros_por_celda(una, direccion="up", tope=300):
    """Cuántos cuadros tarda el próximo paso del pad en `direccion`, contando
    el cuadro en que arranca —`begin_step` ya avanza en ése— hasta el que
    llega. Se suelta al arrancar: un paso no se corta a mitad de celda."""
    una.consola.hold(direccion)
    for _ in range(tope):
        una.consola.run(1)
        if una.byte("step_left"):
            break
    else:
        raise AssertionError("el héroe no arrancó a caminar")
    una.consola.hold()
    cuadros = 1
    while una.byte("step_left"):
        una.consola.run(1)
        cuadros += 1
        assert cuadros < tope, "el paso no terminó"
    return cuadros


def test_sin_tocar_camina_a_la_del_juego(partida):
    una = partida()
    una.correr(5)
    assert cuadros_por_celda(una) == CUADROS[4]


def test_r_sube_y_l_baja_hasta_los_topes(partida):
    """Desde la 4 de arranque: R una vez es la 5, dos la 6, y cinco se
    quedan en 6; L una vez es la 3, tres la 1, y cinco se quedan en 1."""
    for boton, veces, velocidad in (("r", 1, 5), ("r", 2, 6), ("r", 5, 6),
                                    ("l", 1, 3), ("l", 3, 1), ("l", 5, 1)):
        una = partida()
        una.correr(5)
        tocar(una, boton, veces)
        cuadros = cuadros_por_celda(una)
        assert cuadros == CUADROS[velocidad], (
            "con %d toques de %s el héroe cruza la celda en %d cuadros, y a "
            "velocidad %d son %d"
            % (veces, boton.upper(), cuadros, velocidad, CUADROS[velocidad]))
        assert una.velocidad_del_heroe() == 4, \
            "L y R tocaron la velocidad del juego, que es la que viaja en la partida"


def test_desde_el_tope_un_toque_ya_cambia(partida):
    """Con el juego en 6 y dos R de antes que no hicieron nada, una L ya
    baja a 5: el agregado se recalcula desde lo que camina, no se acumula."""
    una = partida()
    una.correr(5)
    una.poner_velocidad_del_heroe(6)
    tocar(una, "r", 2)
    tocar(una, "l")
    assert cuadros_por_celda(una) == CUADROS[5]


def test_sigue_despues_de_cambiar_de_mapa(partida):
    una = partida()
    una.correr(5)
    tocar(una, "r")
    una.ir_al_mapa(6, 50, 50)
    assert cuadros_por_celda(una) == CUADROS[5]


def test_la_ruta_camina_a_la_del_juego_y_despues_vuelve(partida):
    """`ruta-vel` sube la velocidad del juego a 5 con la 28, da tres pasos,
    la baja a 4 con la 29 y da dos más. Con un agregado de +2 de antes, la
    ruta camina igual que sin él —4 cuadros por celda a la 5, 8 a la 4— y el
    pad, al terminar, a 4 + 2."""
    una = partida(caso="ruta-vel")
    una.consola.write_ram(una.simbolos["FAR_SPEED_BONUS"], [2])
    pasos = []
    cuadros, antes = 0, 0
    for _ in range(600):
        una.consola.run(1)
        ahora = una.byte("step_left")
        if ahora:
            cuadros += 1
        elif antes:
            pasos.append(cuadros + 1)
            cuadros = 0
        antes = ahora
        if len(pasos) == 5:
            break
    # El primer paso puede arrancar antes de que se empiece a mirar.
    assert pasos[1:] == [CUADROS[5], CUADROS[5], CUADROS[4], CUADROS[4]], (
        "los pasos de la ruta tardaron %s cuadros: con el agregado adentro "
        "serían de la 6 y la 6" % pasos)
    for _ in range(60):
        una.consola.run(1)
    assert una.velocidad_del_heroe() == 4
    assert cuadros_por_celda(una) == CUADROS[6], \
        "al terminar la ruta, el pad no volvió al agregado"


def test_con_un_mensaje_abierto_no_hace_nada(partida):
    """El caso `autofire` abre un mensaje detrás de otro: R con uno en
    pantalla no cambia nada."""
    una = partida(caso="autofire")
    for _ in range(300):
        if una.byte("msg_open"):
            break
        una.consola.run(1)
    else:
        raise AssertionError("no se abrió ningún mensaje")
    tocar(una, "r", 3)
    assert una.consola.ram(una.simbolos["FAR_SPEED_BONUS"], 1)[0] == 0, \
        "R cambió la velocidad con un mensaje abierto"


def test_un_cartucho_los_apaga_con_no_speed_keys():
    """`test-special` arma con `--no-speed-keys`: el lazo no los lee, y el
    héroe camina siempre a la del juego, como en RM2k."""
    una = tanda.partida("parado-tapado", en="test-special")
    assert una.simbolos["HERO_SPEED_KEYS"] == 0, \
        "test-special se armó con L y R: la prueba no mide lo que dice"
    una.correr(5)
    assert not una.byte("msg_open") and not una.byte("ev_active"), \
        "el héroe no está libre: R no haría nada de todas formas"
    tocar(una, "r", 3)
    assert una.consola.ram(una.simbolos["FAR_SPEED_BONUS"], 1)[0] == 0, \
        "R cambió la velocidad en un cartucho armado sin L y R"
