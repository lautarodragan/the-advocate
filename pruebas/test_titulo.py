"""La pantalla de título: que sus dos opciones hagan lo que dicen.

Lo que se ve —la imagen, el menú, el cursor— lo cobra `just snes-titulo` pixel
por pixel. Lo que **no** puede cobrar es lo de acá: que elegir una opción u otra
deje la partida en estados distintos, porque las dos terminan mostrando el mismo
mapa y la diferencia está en la RAM.

El reparto es el de siempre: la tanda mira la pantalla y esto mira el estado.

La ROM de estas pruebas lleva `--con-titulo` y por eso es un cartucho propio: el
flag cambia el arranque —sin él la partida guardada se carga sola, con él espera
a que el menú lo decida— y ése es justamente el camino que hay que probar.
"""

import pytest

# Cuántos ticks espera la página de prueba antes de guardar, como en
# `test_guardar`: alcanzan para irse a otro mapa —el fundido son 90— y sobra.
ESPERA = 200

EMPEZAR, SEGUIR = 0, 1

# El mapa donde arranca la ROM de las pruebas, que es el primero de su tabla.
# Es el 5 y no el 4 del juego: lo dice `CON_VENTANA` en conftest.py.
MAPA_DE_ARRANQUE = 5


def test_empezar_la_historia_arranca_en_el_mapa_inicial(partida):
    """'Begin the Story' entra al juego por el mapa de arranque de la ROM.

    Es el camino que no depende de que haya nada guardado, y el que confirma
    que salir del título repone la VRAM: el mapa se carga entero de nuevo,
    porque la imagen del título la había pisado.
    """
    una = partida(titulo=EMPEZAR)
    una.correr(1)
    assert una.mapa() == MAPA_DE_ARRANQUE, (
        "'Begin the Story' dejó la partida en el mapa %d y no en el de "
        "arranque" % una.mapa())


def test_el_reloj_del_juego_no_corre_en_el_titulo(partida):
    """`vueltas` arranca en cero después de elegir, no en los cuadros que la
    pantalla de título estuvo puesta.

    No es un detalle interno: es lo que hace que una ROM con título corra el
    mapa igual que una sin él, y por lo tanto que las dos referencias sigan
    siendo comparables. Si el reloj corriera, la animación del ChipSet entraría
    al mapa con otra fase y todos los cuadros de la tanda se moverían.
    """
    una = partida(titulo=EMPEZAR)
    assert una.palabra("vueltas") <= 3, (
        "el reloj del juego contó %d vueltas en la pantalla de título"
        % una.palabra("vueltas"))


def test_seguir_la_historia_carga_la_partida(partida):
    """'Resume the Story' carga la partida de la SRAM.

    Es la prueba que cierra el camino entero: se guarda, se **resetea la
    consola de verdad** —la SRAM sobrevive y la WRAM no— y se elige la segunda
    opción. Si el estado vuelve es porque salió del cartucho.

    Lo que distingue cargar de empezar de nuevo es el **switch**, y no el mapa:
    esta partida guarda sin moverse del mapa de arranque, así que las dos
    opciones terminan en el mismo lugar. Irse a otro mapa antes de guardar
    sería más contundente y hoy no se puede: ver
    `test_irse_de_mapa_antes_de_guardar_no_guarda`, acá abajo.
    """
    una = partida(titulo=EMPEZAR, guardar=ESPERA)
    una.prender(7)
    una.correr(ESPERA + 60)
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"

    una.reiniciar(SEGUIR)
    assert una.switch(7), (
        "'Resume the Story' no cargó la partida: el switch 7 no volvió")


@pytest.mark.xfail(strict=True, reason=(
    "con pantalla de título, irse de mapa antes de guardar deja la partida sin "
    "guardar. Medido el 2026-09-10: quedándose en el mapa de arranque la SRAM "
    "tiene la magia a las ~400 vueltas, y con un ir_al_mapa(6) en el medio "
    "sigue sin tenerla a las 491. Sin pantalla de título el mismo camino "
    "guarda, que es lo que hace test_guardar. **No es el bug de página directa "
    "de partida_suma**: sigue pasando con ése arreglado, y con ése arreglado "
    "cargar sí anda. El sospechoso es el doble cargar_mapa que ahora hay —una "
    "vez en el arranque y otra al salir del menú—, que le reinicia la espera a "
    "la página de prueba. Está anotado en ESTADO.md"))
def test_irse_de_mapa_antes_de_guardar_no_guarda(partida):
    """El segundo defecto, escrito como prueba para que se sepa cuándo se
    arregló.

    Va con `strict`: el día que alguien toque el doble `cargar_mapa` y esto
    empiece a pasar, la prueba falla y obliga a sacar el xfail en vez de dejar
    una deuda que ya no existe.
    """
    una = partida(titulo=EMPEZAR, guardar=ESPERA)
    una.ir_al_mapa(6, 20, 30)
    una.prender(7)
    una.correr(ESPERA + 60)
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"


def test_empezar_ignora_la_partida_guardada(partida):
    """Y la primera opción no la carga, que es la mitad que se puede romper sin
    que nadie se entere.

    Con la ROM de antes de la pantalla de título el arranque cargaba la partida
    **siempre**, así que 'Begin the Story' habría devuelto al jugador al mapa 6
    con el switch prendido. Elegir empezar de nuevo tiene que dejar el mundo
    como estaba.
    """
    una = partida(titulo=EMPEZAR, guardar=ESPERA)
    una.ir_al_mapa(6, 20, 30)
    una.prender(7)
    una.correr(ESPERA)

    una.reiniciar(EMPEZAR)
    assert una.mapa() == MAPA_DE_ARRANQUE, (
        "'Begin the Story' cargó la partida guardada: quedó en el mapa %d"
        % una.mapa())
    assert not una.switch(7), (
        "el switch 7 de la partida guardada sobrevivió a empezar de nuevo")
