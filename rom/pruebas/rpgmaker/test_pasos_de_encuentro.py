"""`ChangeEncounterSteps`: cada cuántos pasos hay un encuentro al azar.

Es `Game_Map::SetEncounterSteps`: cambia el `encounter_steps` del mapa hasta
que se cargue otro. En la ROM son dos cosas que salen del mismo número —la
chance del paso, `ENC_BASE`, y en qué paso se cruza cada fila de la tabla,
`ENC_THR`— y el conversor las calcula las dos: ver `encounter_steps` en
runtime/encounters.s y `Encounters.set_steps`, que es el modelo.

Lo pidió el viaje de Dalia a Tasgarde (la automática 14 del mundo, el 66), que
los pone en cero antes de forzarle una ruta al héroe. Los tres casos van en el
66, que tiene encuentros por zona, y en el 5, que no tiene ninguno.

Los del 66 cambian al actor 10 por Talan apenas llegan: con `DummyHero` en el
grupo corre esa misma automática del viaje, que también los apaga, y la
prueba del cero pasaría por ella.
"""

from batalla import grupo_de
from consola import en_la_wram
from tanda import partida

import events

EL_MUNDO = 66
LA_LLEGADA = (71, 29)
# Los pasos del 66 en el árbol del juego (`RPG_RT.lmt`).
PASOS_DEL_MUNDO = 65
# Lo que tarda la página del caso después de llegar: el `Wait` de tres
# décimas y el comando, con margen.
TICKS = 20


def leer(p):
    """(ENC_BASE, los ocho bytes de ENC_THR, ENC_REG)."""
    s = p.simbolos
    base = p.consola.ram(en_la_wram(s["ENC_BASE"]), 2)
    umbrales = list(p.consola.ram(en_la_wram(s["ENC_THR"]), 8))
    registro = p.consola.ram(en_la_wram(s["ENC_REG"]), 1)[0]
    return base[0] | (base[1] << 8), umbrales, registro


def esperado(pasos):
    return (events.enc_base(pasos),
            events.enc_step_thresholds(pasos) + [0xFF])


def test_cambiar_los_pasos_cambia_la_chance_y_las_filas():
    p = partida("encuentros-pasos")
    p.correr(TICKS)
    assert p.mapa() == EL_MUNDO, p.mapa()
    base, umbrales, _ = leer(p)
    assert (base, umbrales) == esperado(10), (
        "ChangeEncounterSteps de 10 en el 66 dejó ENC_BASE en %d y los "
        "umbrales en %s; con 10 pasos son %s" % (base, umbrales, esperado(10)))


def test_cargar_otro_mapa_vuelve_a_los_pasos_del_mapa():
    """RM2k lee `encounter_steps` del árbol en cada carga: lo que puso el
    comando no sobrevive a un `Teleport`, ni siquiera al mismo mapa."""
    p = partida("encuentros-pasos")
    p.correr(TICKS)
    p.ir_al_mapa(EL_MUNDO, *LA_LLEGADA)
    p.correr(TICKS)
    base, umbrales, _ = leer(p)
    assert (base, umbrales) == esperado(PASOS_DEL_MUNDO), (
        "al volver a cargar el 66, ENC_BASE vale %d y los umbrales %s; los "
        "del mapa son %s" % (base, umbrales, esperado(PASOS_DEL_MUNDO)))


def test_cero_los_apaga():
    p = partida("encuentros-apagados")
    p.correr(TICKS)
    assert grupo_de(p) == [14], (
        "el caso deja a Talan solo, y el grupo es %s: ¿corrió el viaje de "
        "Dalia?" % grupo_de(p))
    base, _, _ = leer(p)
    assert base == 0, (
        "ChangeEncounterSteps de 0 dejó ENC_BASE en %d, y cero es apagados"
        % base)


def test_en_un_mapa_sin_encuentros_no_prende_nada():
    """Sin tropas ni áreas no hay encuentro que prender: `set_steps` deja la
    base en cero, y la ROM no escribe nada."""
    p = partida("encuentros-sin-zonas")
    p.correr(TICKS)
    assert p.mapa() == 5, p.mapa()
    base, _, registro = leer(p)
    assert registro == p.simbolos["ENC_NONE"] and base == 0, (
        "en el 5, sin encuentros, ChangeEncounterSteps de 10 dejó ENC_REG en "
        "$%02X y ENC_BASE en %d" % (registro, base))
