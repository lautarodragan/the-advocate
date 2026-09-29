"""El viaje entero de los HP: se pelea, se vuelve al mapa y se abre el menú.

Es lo que taro hizo jugando y lo que ninguna prueba hacía: *"el hp se reduce en
batalla, pero en el menú siempre se muestra en 40"*. Las dos mitades estaban
cubiertas por separado —`test_batalla.py` exige el HP exacto turno por turno y
`test_menu_dibujo.py` compara el menú contra `menus.render_menu`— y justo la
costura entre las dos no la miraba nadie, porque la referencia del menú
dibujaba el máximo horneado y la ROM también: **los dos lados se equivocaban
igual**.

Lo que se mide acá es la cadena completa:

    la pelea baja los HP  ->  `modo_fin` los guarda en `FAR_HP`
    -> el menú los lee    ->  y dibuja los de ahora, no los del bloque

La pelea es la del droide del mapa 2 contra Kersh y Core, que es determinista:
`batalla_correr` arranca el azar con `BATALLA_SEMILLA` en cada pelea, así que
sale siempre igual. Medido el 2026-09-13: gana el grupo, Kersh no pierde un HP
y Core queda en 79 de 127. Que el número esté escrito acá no es adorno: si
alguna vez cambia, cambió una fórmula de la pelea y hay que saberlo.
"""

from menu import abrir
import datos
from dibujo import comparar_pantalla, pixeles_distintos

# La pelea es la de la página de prueba `pelea-82-grupo-11-12`: la tropa del
# droide del mapa 2, la misma que usan las demás pruebas de pelea, 18 ticks
# después de arrancar, y con Kersh y Core, que la ganan. Con el grupo por
# omisión —DummyHero, nivel 1— el droide lo mata de un golpe y los HP quedan en
# cero, que es un número que no distingue "el menú lo lee" de "el menú dibuja
# cualquier cosa". `GRUPO` tiene que ser el que arma esa página.
GRUPO = (11, 12)
# Lo que la pelea deja, medido.
DESPUES = {11: 168, 12: 79}
MAXIMOS = {11: 168, 12: 127}


def pelear(una, tope=20000):
    """Abre la pelea de la página y la juega a fuerza de A.

    Todo en cuadros de hardware: la pelea corre su propio lazo y `vueltas` no
    avanza mientras dura, así que contar ticks se quedaría esperando. Se sabe
    que empezó y que terminó por `menu_abierto`, que es lo que la ROM prende
    mientras una pantalla propia está a la vista.
    """
    for _ in range(600):
        una.consola.correr(1)
        if una.byte("menu_abierto"):
            break
    else:
        raise AssertionError("la página no abrió la pelea")
    for n in range(tope):
        una.consola.apretar(*(("a",) if n % 6 < 2 else ()))
        una.consola.correr(1)
        if not una.byte("menu_abierto"):
            una.consola.apretar()
            # Y hasta que el lazo del mapa vuelva a correr: la vuelta de la
            # pelea descomprime los tiles del mapa y dura unos cuadros, y un B
            # apretado mientras tanto no lo ve nadie. Eran diez cuadros fijos
            # hasta que la carga creció, el 2026-09-26.
            antes = una.palabra("vueltas")
            for _ in range(240):
                una.consola.correr(1)
                if una.palabra("vueltas") - antes >= 2:
                    break
            una.consola.correr(10)
            return una
    raise AssertionError("la pelea no terminó en %d cuadros" % tope)


def hp_de(una):
    return {a: una.hp(a) for a in GRUPO}


def test_la_pelea_baja_los_hp_y_los_deja_en_la_partida(partida):
    """La primera mitad: `modo_fin` guarda lo que quedó en `FAR_HP`."""
    una = pelear(partida(caso="pelea-82-grupo-11-12"))
    assert hp_de(una) == DESPUES, (
        "la pelea del droide contra Kersh y Core dejó %s y venía dejando %s: "
        "si es a propósito, hay que corregir el número acá" % (hp_de(una),
                                                               DESPUES))


def test_el_menu_de_despues_de_la_pelea_muestra_esos_hp(partida):
    """Y la segunda: el menú abierto en el mapa dibuja esos mismos números.

    **Comprobado en rojo con la ROM de antes** —sin el `jsl menu_hp_escribir`
    de `menu_grupo_pintar`—: 111 pixeles de diferencia, los de las cifras que
    nadie escribía.
    """
    from port import menus
    from rpgmaker.resources import GAME_DIR
    from batalla import exp_y_nivel
    una = pelear(partida(caso="pelea-82-grupo-11-12"))
    quedo = hp_de(una)
    # La experiencia también la cambió la pelea, y el menú la muestra.
    ganado = {a: exp_y_nivel(una, a) for a in GRUPO}
    exps = {a: exp for a, (exp, _) in ganado.items()}
    niveles = {a: nivel for a, (_, nivel) in ganado.items()}
    abrir(una)
    db, skin = datos.base(), datos.skin()
    oro = una.oro()
    esperada = menus.render_menu(skin, db, una.simbolos["SRAM_RANURAS"],
                                  GRUPO, oro, 0, True, db.font_id, None,
                                  GAME_DIR, quedo, niveles, exps)
    comparar_pantalla(una, esperada, "menu-tras-pelea",
                      "el menú después de la pelea")
    # Y que la comparación de arriba mida algo: con los HP llenos la referencia
    # dibuja **otra** imagen. Sin esto, una ROM que volviera a hornear el
    # máximo pasaría el caso el día que la referencia se equivocara igual.
    llena = menus.render_menu(skin, db, una.simbolos["SRAM_RANURAS"],
                               GRUPO, oro, 0, True, db.font_id, None,
                               GAME_DIR, MAXIMOS, niveles, exps)
    assert pixeles_distintos(llena, esperada) > 20, (
        "la referencia dibuja lo mismo con Core en 79 que con Core en 127")


# --- y los enemigos, dos peleas seguidas -------------------------------------
#
# El cuarto síntoma del reporte —*"varios enemigos empezaban con HP bajo a
# partir de la segunda batalla aleatoria... se guarda el HP asociado a un
# índice de enemigo y no se reinicia"*— **no era un defecto**, y esto es lo que
# lo deja medido en vez de razonado: `ba_armar` vacía las doce ranuras y
# rellena los HP de cada enemigo desde `enemigo_hp` del cartucho en cada pelea.
#
# Lo que taro vio es de los datos del juego: las tropas de Rat Tracks B1 son
# GiantRat (20 HP), MutantMouse (25) y HairyVermin (40), y la pantalla de la
# pelea muestra el HP de cada enemigo —el máximo no, `BA_CONMAX` en cero—. O
# sea que un GiantRat dice "20" porque tiene 20, y no porque le haya quedado
# eso de la pelea anterior.

from batalla import con_encuentros                    # noqa: E402


def enemigos_de(una):
    """Los enemigos armados: (número, HP de ahora, HP máximo)."""
    sim = una.simbolos
    salida = []
    for ranura in range(sim["BA_COMB_MAX"]):
        base = sim["BA_UNO"] + ranura * sim["BA_BYTES"]
        banderas = una.consola.ram(base + sim["BA_FLAGS"], 1)[0]
        if not banderas & sim["BAF_HAY"] or banderas & sim["BAF_ACTOR"]:
            continue
        hp, hpmax = (una.consola.ram(base + campo, 2)
                     for campo in (sim["BA_HP"], sim["BA_HPMAX"]))
        salida.append((una.consola.ram(base + sim["BA_NUMERO"], 1)[0],
                       hp[0] | (hp[1] << 8), hpmax[0] | (hpmax[1] << 8)))
    return salida


def hasta_que_se_abra(una, cuadros=900):
    """Camina hasta que la pantalla de la pelea esté puesta."""
    for n in range(cuadros):
        una.consola.apretar(("up", "down", "left", "right")[(n // 40) % 4])
        una.consola.correr(1)
        if una.byte("menu_abierto"):
            una.consola.apretar()
            return una
    raise AssertionError("no salió ningún encuentro en %d cuadros" % cuadros)


def ganarla(una, tope=20000):
    for n in range(tope):
        una.consola.apretar(*(("a",) if n % 6 < 2 else ()))
        una.consola.correr(1)
        if not una.byte("menu_abierto"):
            una.consola.apretar()
            return una
    raise AssertionError("la pelea no terminó")


def test_dos_encuentros_seguidos_arman_los_enemigos_enteros(partida):
    """Las dos peleas tienen que empezar con cada enemigo en su máximo."""
    una = con_encuentros(partida)
    vistos = []
    for vuelta in (1, 2):
        hasta_que_se_abra(una)
        tropa = enemigos_de(una)
        assert tropa, "la pelea %d se abrió sin enemigos" % vuelta
        for numero, hp, hpmax in tropa:
            assert hp == hpmax, (
                "en la pelea %d el enemigo %d arrancó con %d de %d: se le "
                "heredaron los HP de una pelea anterior"
                % (vuelta, numero, hp, hpmax))
        vistos.append(tropa)
        ganarla(una)
    # Y que de verdad hayan sido dos peleas: con una sola, un enemigo que
    # heredara los HP de la anterior no tendría de dónde heredarlos.
    assert len(vistos) == 2
