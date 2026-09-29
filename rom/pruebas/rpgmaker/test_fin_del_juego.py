"""End Game, la última orden del menú de pausa: `Scene_End`.

Que la pantalla se vea como `fin_del_juego.render` pixel por pixel, con el
cursor en cada orden; que "No" y B vuelvan al menú como estaba, con el cursor
en End Game; y que "Yes" funda el tema y la pantalla y termine en la
pantalla de título, igual que al encender —la golden `titulo`—, con el juego
que arranca de nuevo al elegir "Begin the Story".

Lo que se ve sin comparar contra Python lo cobran las goldens `fin` y
`fin-no` de `test_menu_golden.py`.
"""

from port import fin_del_juego

from consola import TITULO_AIRE
import datos
from dibujo import comparar_pantalla
from menu import abrir, con_grupo
from tanda import golden
from test_game_over import TITULO_QUIETO, cuadros_hasta_volver
from test_menu_dibujo import comparar as comparar_menu
from batalla import cuadros_hasta_reiniciar

MENU_FIN = 4


def entrar(una):
    """Del mapa a End Game: B, arriba —desde la primera da la vuelta a la
    última— y A."""
    abrir(una)
    una.tocar_cuadros("up")
    una.tocar_cuadros("a", TITULO_AIRE)
    assert una.menu_abierto()
    return una


def comparar(una, elegida, nombre):
    db, skin = datos.base(), datos.skin()
    esperada = fin_del_juego.render(skin, db, elegida, db.font_id)
    comparar_pantalla(una, esperada, nombre,
                      "End Game con el cursor en %d" % elegida)


def test_la_pantalla_se_ve_como_la_referencia(partida):
    """Entra con el cursor en "Yes", como el RPG_RT, y abajo lo pasa a "No"
    —que es subir la otra paleta—; abajo otra vez da la vuelta."""
    una = entrar(con_grupo(partida()))
    comparar(una, fin_del_juego.SI, "fin")
    una.tocar_cuadros("down")
    comparar(una, fin_del_juego.NO, "fin-no")
    una.tocar_cuadros("down")
    comparar(una, fin_del_juego.SI, "fin-vuelta")


def test_no_vuelve_al_menu_como_estaba(partida):
    """"No" vuelve al menú con el cursor en End Game, y el menú se cierra
    después como siempre."""
    una = entrar(con_grupo(partida()))
    antes = una.palabra("vueltas")
    una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)
    assert una.menu_abierto(), "\"No\" cerró el menú"
    comparar_menu(una, MENU_FIN, nombre="menu-fin-no")
    assert una.palabra("vueltas") == antes, "el reloj corrió en End Game"
    una.tocar_cuadros("b", 10)
    assert not una.menu_abierto()


def test_b_cancela(partida):
    """B, con el cursor en "Yes", vuelve al menú igual que "No"."""
    una = entrar(con_grupo(partida()))
    una.tocar_cuadros("b", TITULO_AIRE)
    assert una.menu_abierto(), "B en End Game cerró el menú"
    comparar_menu(una, MENU_FIN, nombre="menu-fin-b")


# Un mapa con su tema sonando: los Rat Tracks, con `KSSMKEND`. Ver
# `test_tema_del_mapa.py`.
CON_TEMA = "tema-del-mapa-21"


def test_si_vuelve_al_titulo(partida):
    """"Yes": el tema empieza a fundirse, la ROM se reinicia, y lo que se ve es
    la pantalla de título de siempre. Elegir "Begin the Story" arranca el
    juego de nuevo, en el mapa de arranque."""
    una = partida(caso=CON_TEMA)
    una.correr(30)
    assert not una.byte("music_apagada"), (
        "el caso no tiene tema sonando: no mira el fundido")
    entrar(una)
    una.tocar_cuadros("a", 2)
    assert una.byte("bgm_fundido"), "\"Yes\" no fundió el tema"
    assert cuadros_hasta_reiniciar(una, 120) is not None, (
        "\"Yes\" no reinició la ROM")
    una.consola.correr(TITULO_QUIETO)
    golden("titulo", una.imagen())
    assert cuadros_hasta_volver(una) is not None, (
        "después de End Game el arranque no volvió a correr")
    assert una.palabra("mapa_actual") == 0
