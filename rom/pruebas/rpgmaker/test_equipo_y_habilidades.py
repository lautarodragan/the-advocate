"""`ChangeEquipment` y `ChangeSkills` desde un evento, y que lo que cambian
viaje en la partida.

Los dos traban páginas del juego que la tanda no corre —el `Craftsman` del
mapa 30 y la cinemática del techo del mapa 32— y los dos cambian estado que no
se ve en ningún pixel del cuadro en que pasa, así que esto le pregunta a la RAM.

**Las habilidades son un bit por par (actor, habilidad)** en `FAR_HAB`, con la
ranura que les da `events.SKILL_SLOT`: el juego entero **más los pares
que nombren las páginas de prueba del cartucho**, así que la prueba rearma el
índice con los mismos casos. La página `habilidades-cambiar` le enseña a Arden
la 152 —se la enseña el mapa 48— y le hace olvidar la 147, que el LDB le da.
"""

from port import events

import datos
from datos import pagina_de
from batalla import sabe

ARDEN, KERSH, CORE, MANTA = 15, 11, 12, 13
APRENDE, OLVIDA = 152, 147
# Los switches que prende la página de prueba según lo que conteste la rama
# "sabe la habilidad": ninguna página del juego los nombra.
SABE_LA_NUEVA, SABE_LA_VIEJA = 136, 138
# Cuántos ticks se le dan a la página: espera 18 antes de tocar nada, que son
# los que la prueba usa para escribir la RAM de partida.
DESPUES = 60


def ranura(actor, habilidad):
    return datos.ranuras_de_habilidad()[(actor, habilidad)]


def poner(una, actor, habilidad, valor):
    r = ranura(actor, habilidad)
    donde = una.simbolos["FAR_HAB"] + (r >> 3)
    octeto = una.consola.ram(donde, 1)[0]
    octeto = octeto | (1 << (r & 7)) if valor else octeto & ~(1 << (r & 7))
    una.consola.write_ram(donde, [octeto])


# --- las habilidades --------------------------------------------------------

def test_los_bits_arrancan_con_lo_que_dice_el_ldb(partida):
    """`initial_skills_set`: el control de las dos de abajo. Sin él, una ROM
    que no copiara nada y dejara `FAR_HAB` en cero daría "no la sabe" para la
    147 por el motivo equivocado."""
    una = partida(caso="habilidades-cambiar")
    pares = len(datos.ranuras_de_habilidad())
    assert una.simbolos["HAB_BYTES"] == (pares + 7) // 8, (
        "el cartucho tiene otro índice de pares que el que arma la prueba: "
        "sus ranuras no valen")
    assert sabe(una, ARDEN, OLVIDA), "Arden arranca sin la 147 del LDB"
    assert not sabe(una, ARDEN, APRENDE), "Arden arranca sabiendo la 152"
    assert sabe(una, KERSH, 131) and sabe(una, MANTA, 150)


def test_change_skills_ensena_y_hace_olvidar(partida):
    una = partida(caso="habilidades-cambiar")
    una.correr(DESPUES)
    assert sabe(una, ARDEN, APRENDE), "ChangeSkills no le enseñó la 152"
    assert not sabe(una, ARDEN, OLVIDA), "ChangeSkills no le hizo olvidar la 147"
    # Y los vecinos de byte siguen como estaban: la escritura es de un bit.
    assert sabe(una, ARDEN, 148) is False and sabe(una, KERSH, 131)


def test_la_rama_contesta_lo_que_sabe_ahora(partida):
    """La rama 4 de `ConditionalBranch` lee el mismo bit: después de
    enseñarle la 152 contesta que sí, y después de sacarle la 147, que no."""
    una = partida(caso="habilidades-cambiar")
    una.correr(DESPUES)
    assert una.switch(SABE_LA_NUEVA), "la rama no vio la habilidad aprendida"
    assert not una.switch(SABE_LA_VIEJA), "la rama vio la habilidad olvidada"


def test_las_habilidades_viajan_en_la_partida(partida):
    una = partida(caso="guardar-198")
    poner(una, ARDEN, APRENDE, True)
    poner(una, ARDEN, OLVIDA, False)
    una.guardar_en(0)
    una.reiniciar()
    assert sabe(una, ARDEN, APRENDE) and not sabe(una, ARDEN, OLVIDA), (
        "lo que Arden sabe no volvió de la SRAM")


# --- el equipo --------------------------------------------------------------

def test_change_equipment_saca_y_devuelve_al_inventario(partida):
    """El grupo —Kersh y Core— sin arma, y Manta sin casco. Lo que tenían puesto
    vuelve al inventario, que es `Game_Actor::ChangeEquipment(ranura, 0)`."""
    una = partida(caso="equipo-quitar")
    base = datos.base()
    arma_k = base.actors[KERSH].initial_equipment[0]
    arma_c = base.actors[CORE].initial_equipment[0]
    casco_m = base.actors[MANTA].initial_equipment[3]
    assert arma_k and arma_c and casco_m, "el caso no saca nada: no mide nada"
    # Uno de los ítems ya estaba en el tope: tiene que quedarse ahí.
    una.consola.write_ram(una.simbolos["FAR_ITEMS"] + arma_c,
                          [events.ITEM_MAX])
    una.correr(DESPUES)
    assert una.equipo(KERSH)[0] == 0 and una.equipo(CORE)[0] == 0, (
        "el grupo sigue armado: %s, %s" % (una.equipo(KERSH), una.equipo(CORE)))
    assert una.equipo(MANTA)[3] == 0, "Manta sigue con el casco"
    assert una.item(arma_k) == 1, "el arma de Kersh no volvió al inventario"
    assert una.item(arma_c) == events.ITEM_MAX, "el inventario pasó del tope"
    assert una.item(casco_m) == 1, "el casco de Manta no volvió al inventario"


def test_change_equipment_no_toca_lo_demas(partida):
    """El control: Manta no está en el grupo, así que su arma sigue; y de Kersh
    sólo se va el arma."""
    una = partida(caso="equipo-quitar")
    base = datos.base()
    una.correr(DESPUES)
    assert una.equipo(MANTA)[0] == base.actors[MANTA].initial_equipment[0]
    assert una.equipo(KERSH)[1:] == base.actors[KERSH].initial_equipment[1:]


# --- y las páginas que esto destraba ---------------------------------------

def test_el_craftsman_y_el_techo_compilan():
    """El `Craftsman` del mapa 30 —`ChangeEquipment [0, 0, 1, 0, 0]`— y la
    cinemática del techo del mapa 32, `EV0005`, con `ChangeSkills`, la
    `ChangeEquipment` de su evento común y el `GameOver` de la derrota. Y los
    eventos 23 y 25 del 32, que hacen olvidar y enseñar."""
    for mapa, evento, pagina in ((30, 1, 0), (32, 5, 0), (32, 5, 1),
                                 (32, 23, 2), (32, 25, 0)):
        assert pagina_de(mapa, evento, pagina) is not None, (
            "la página %d del evento %d del mapa %d no compila"
            % (pagina, evento, mapa))
