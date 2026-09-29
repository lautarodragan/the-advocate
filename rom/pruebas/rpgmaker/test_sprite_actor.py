"""El CharSet que `ChangeSpriteAssociation` le pone a un actor es estado.

El comando destraba la mayoría de las páginas disparables de la persecución en
auto, y lo que las páginas hacen con él es siempre lo mismo: cambiarle el
gráfico a `CarRED` o `CarBLUE` —que son el héroe mientras dura la carrera— y
**teletransportar en el comando siguiente**. O sea que lo único que se ve del
comando está del otro lado del salto.

Por eso vive en `FAR_ACTOR_GFX` y viaja en `save_table`, y por eso hacen
falta estas dos pruebas: la tanda de pixeles cubre que el cambio **se vea**
—`sprite-actor`, verificado en rojo— pero no puede cubrir que sobreviva,
porque un caso suyo es un mapa y un puñado de cuadros.

Lo que se escribe acá es el byte, a mano, en vez de armar una ROM con una
página que lo emita: lo que está en juego es el **guardado**, no el opcode. Es
el mismo camino que usa `test_batalla` con `FAR_HP`.
"""

import pytest

# Un índice de gráfico cualquiera, distinto de `ACTOR_GFX_NONE`. No hace
# falta que exista en la tabla del mapa: lo que se mira es que el byte viaje.
GRAFICO = 3
OTRO = 7            # con el que se ensucia la WRAM antes del reset
# La página de prueba `guardar-198` espera 198 ticks antes de guardar.


def poner(una, actor, valor):
    una.consola.write_ram(
        una.simbolos["FAR_ACTOR_GFX"] + actor, [valor])


def leer(una, actor):
    return una.consola.ram(una.simbolos["FAR_ACTOR_GFX"] + actor, 1)[0]


def test_arranca_sin_ningun_actor_cambiado(partida):
    """El reset deja todos en `ACTOR_GFX_NONE`.

    No es una formalidad: con la RAM lejana en cero —que es como la deja
    `clear_variables` para todo lo que está más abajo— cada actor arrancaría
    con "el gráfico 0 de la tabla del mapa", o sea el primero que a cada mapa
    le haya tocado, y el héroe se dibujaría con cualquier cosa desde el primer
    cuadro. Lo evita `actor_gfx_clear`.
    """
    una = partida()
    ninguno = una.simbolos["ACTOR_GFX_NONE"]
    actores = una.simbolos["ACTORES_N"]
    puestos = [a for a in range(actores) if leer(una, a) != ninguno]
    assert not puestos, (
        "los actores %s arrancaron con un gráfico puesto y nadie se lo puso"
        % puestos)


def test_sobrevive_al_teletransporte(partida):
    """Un mapa nuevo no lo repone, a diferencia de la orden 34 sobre el héroe.

    Es la diferencia que justifica todo esto. La orden 34 la repone
    `pick_hero_graphic` porque el gráfico vive en el banco de sprites del
    mapa; esto vive en el actor, como en RM2k, y el juego lo usa justamente
    para cruzar.
    """
    una = partida()
    lider = una.byte("party")
    poner(una, lider, GRAFICO)
    una.ir_al_mapa(6, 20, 30)
    assert una.mapa() == 6
    assert leer(una, lider) == GRAFICO, (
        "el gráfico del actor %d se perdió al cambiar de mapa" % lider)


def test_viaja_en_la_partida_guardada(partida):
    """Y sobrevive a apagar la consola, que es lo que prueba el reset.

    Sin el renglón en `save_table` esto vuelve en `ACTOR_GFX_NONE` y el
    jugador que guarda en medio de la carrera carga con el auto dibujado como
    una persona —o al revés—.
    """
    una = partida(caso="guardar-198")
    lider = una.byte("party")
    una.ir_al_mapa(6, 20, 30)
    poner(una, lider, GRAFICO)
    una.guardar_en()
    # Y **se ensucia después de guardar**: el reset de snes9x no borra la WRAM,
    # así que sin esto el byte sobreviviría solo y la prueba daría verde con el
    # renglón de `save_table` sacado. Está medido: así pasó la primera vez.
    poner(una, lider, OTRO)
    una.reiniciar()
    assert leer(una, lider) == GRAFICO, (
        "el gráfico del actor %d no sobrevivió al reset: la partida no lo "
        "lleva" % lider)


def test_el_mapa_de_la_ram_lejana_no_se_pisa(partida):
    """`FAR_ACTOR_GFX` termina antes de donde empieza la pelea.

    El mapa de la RAM lejana ya se pisó una vez —el cartel encima del estado
    del MSU-1, y la música quedó muda un día entero— y el único control que
    tiene es que alguien lo mire. Acá se lo mira con los dos números que la ROM
    misma declara, así que un `ACTORES_N` más grande lo dice en vez de
    escribirle encima al primer byte de la batalla.
    """
    una = partida()
    fin = una.simbolos["FAR_ACTOR_GFX"] + una.simbolos["ACTORES_N"]
    assert fin <= una.simbolos["FAR_BATTLE"], (
        "los %d actores llegan hasta $%04X y la pelea empieza en $%04X"
        % (una.simbolos["ACTORES_N"], fin, una.simbolos["FAR_BATTLE"]))
