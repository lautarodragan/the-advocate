"""La posada: `ShowInn`, que el compilador no conocía.

Es el tercero de los tres que taro encontró jugando el 2026-09-19: el bum del
mapa 20 —`InnBum`, el evento 4— ofrece un montón de basura por 5 créditos, y
su página no compilaba, así que no se le podía hablar.

**No es un opcode nuevo.** `ShowInn` se expande a comandos que el intérprete
ya hacía —el saludo, la elección, una rama por oro, el cobro y la cura— igual
que `CallEvent` se expande al cuerpo del llamado. El porqué de cada byte está
en `compile_inn`, en el compilador de `rm2k-snes-events`, y ahí están
también las tres deudas declaradas: sin ventana de oro, sin "Yes" en gris
cuando no alcanza y sin el fundido ni la música de `Scene_Map::CallInn`.

Lo que estas pruebas cuidan es lo que sí pasa: que cobre cuando alcanza, que
no cobre cuando no, y que "No" no toque nada.
"""

import os

from batalla import grupo_de, sin_hp
from datos import maximos

# El bum y su precio, del `ShowInn [0, 5, 0]` de la página. La celda es la de
# abajo: desde ahí se le habla mirando hacia arriba.
DEBAJO_DEL_BUM = (91, 28)
PRECIO = 5

# Los dos cuadros que hay que pasar antes de que aparezca la elección: el
# texto del bum y el saludo de la posada.
CUADROS_DEL_SALUDO = 2
# Cuánto se le da a cada mensaje para terminar de componerse. Medido: entre
# nueve y diecinueve ticks, y acá sobra.
TICKS_POR_CUADRO = 60


def frente_al_bum(partida):
    una = partida()
    una.ir_al_mapa(20, *DEBAJO_DEL_BUM)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    return una


def _pasar_un_cuadro(una):
    """Un toque de A cuando el mensaje terminó de componerse.

    Un toque que cae antes no hace nada —la ROM ignora el botón mientras
    `msg_open` esté en cero—, así que se espera a que la ventana esté.
    """
    for _ in range(TICKS_POR_CUADRO):
        if una.byte("msg_open"):
            una.tocar_ticks("a")
            return
        una.correr(1)
    raise AssertionError("el mensaje no llegó a abrirse")


def hasta_la_eleccion(una):
    """Le habla al bum y vuelve con la elección de la posada en pantalla."""
    una.tocar_ticks("a")
    for _ in range(CUADROS_DEL_SALUDO):
        _pasar_un_cuadro(una)
    for _ in range(TICKS_POR_CUADRO):
        if una.byte("pick_active") and una.byte("msg_open"):
            return una
        una.correr(1)
    raise AssertionError("la posada no abrió su elección")


def elegir(una, opcion):
    """La opción `opcion` de la elección abierta: 0 es "Yes" y 1 es "No"."""
    for _ in range(opcion):
        una.tocar_ticks("down")
        una.correr(1)
    una.tocar_ticks("a")
    una.correr(30)


def hp_del_grupo(una):
    return {actor: una.hp(actor) for actor in grupo_de(una)}


def test_con_oro_de_sobra_cobra_y_cura(partida):
    una = frente_al_bum(partida)
    una.poner_oro(3 * PRECIO)
    sin_hp(una)
    hasta_la_eleccion(una)
    elegir(una, 0)
    assert una.oro() == 2 * PRECIO, (
        "la posada tendría que haber cobrado %d y el oro quedó en %d"
        % (PRECIO, una.oro()))
    tope = maximos()
    for actor, hp in hp_del_grupo(una).items():
        assert hp == tope[actor][0], (
            "el actor %d quedó con %d HP después de dormir y el máximo es %d"
            % (actor, hp, tope[actor][0]))


def test_con_el_precio_justo_alcanza(partida):
    """La igualdad, que es donde una rama de oro mal escrita se equivoca: en
    RM2k la condición es `oro >= precio` y el `>=` la incluye."""
    una = frente_al_bum(partida)
    una.poner_oro(PRECIO)
    sin_hp(una)
    hasta_la_eleccion(una)
    elegir(una, 0)
    assert una.oro() == 0
    tope = maximos()
    for actor, hp in hp_del_grupo(una).items():
        assert hp == tope[actor][0]


def test_sin_oro_no_cobra_ni_cura(partida):
    """La deuda declarada: acá "Yes" se puede elegir aunque no alcance, y
    elegirlo equivale a "No". En RM2k el cursor no lo deja seleccionar."""
    una = frente_al_bum(partida)
    una.poner_oro(PRECIO - 1)
    sin_hp(una)
    antes = hp_del_grupo(una)
    assert antes, "el grupo quedó vacío: la prueba no mide nada"
    hasta_la_eleccion(una)
    elegir(una, 0)
    assert una.oro() == PRECIO - 1, (
        "la posada cobró sin que alcanzara: el oro quedó en %d"
        % una.oro())
    assert hp_del_grupo(una) == antes, "curó sin cobrar"


def test_con_no_no_pasa_nada(partida):
    una = frente_al_bum(partida)
    una.poner_oro(3 * PRECIO)
    sin_hp(una)
    antes = hp_del_grupo(una)
    assert antes, "el grupo quedó vacío: la prueba no mide nada"
    hasta_la_eleccion(una)
    elegir(una, 1)
    assert una.oro() == 3 * PRECIO, (
        "decir que no le costó %d créditos"
        % (3 * PRECIO - una.oro()))
    assert hp_del_grupo(una) == antes, "curó al que dijo que no"


# --- lo que el compilador emite -------------------------------------------

def test_la_pagina_del_bum_compila():
    """La página del bum compila, que es lo que no pasaba el 2026-09-19.

    Qué compila, byte por byte —los destinos de la elección y de la rama,
    que son absolutos dentro de la página y por eso los corre el mensaje
    del bum que va delante—, es del compilador desde el 2026-10-02:
    `an_inn_with_a_price_is_its_greeting_a_choice_and_a_gold_branch`, en
    `compile.rs` de `rm2k-snes-events`, con la misma forma que esta página:
    un mensaje y la posada a 5. La posada gratis, que es sólo la cura, es
    `a_free_inn_is_only_the_heal`, al lado. Las de arriba miran que la ROM
    haga lo que esos bytes dicen.
    """
    from datos import pagina_de
    assert pagina_de(20, 4, 0) is not None, "la página del bum no compila"
