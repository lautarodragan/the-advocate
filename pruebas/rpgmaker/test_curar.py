"""`FullHeal` después de perder una pelea: el grupo vuelve con todo lleno.

Es el bug que taro encontró jugando el 2026-09-19. La pelea obligatoria del
mapa 9 —`EV0004`, tropa 86: cuatro GangMember contra Talan en nivel 1— se
pierde por diseño, y su manejador de derrota llama a `FullHeal`. Ése
**compilaba a nada** desde `ced9464`, de cuando los HP no bajaban nunca fuera
de pelea; al día siguiente `9527063` los hizo estado y nadie volvió a mirarlo.
Así que Talan seguía en cero, el primer encuentro al azar se daba por perdido
sin abrirse —"nadie en pie", `batalla_correr`— y `move_hero` volvía al título.
La demo no pasaba de ahí.

Ninguna prueba corría un `FullHeal` después de perder, que es exactamente lo
que AGENTS.md llama un camino que ninguna prueba ejecuta.

**Cómo se pierde sin pelear**: igual que en `test_game_over.py`, con los HP de
todos en cero antes de que la página abra la pelea. La página `pelea-82-curar`
espera 18 ticks para eso, y su manejador de derrota es un `FullHeal [0, 0]`.
Corre en el mapa 20 porque tiene encuentros al azar en la celda de llegada y
ningún evento que toque el grupo, y el control necesita las dos cosas.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))

from test_game_over import cuadros_hasta_reiniciar, sin_hp    # noqa: E402

# Cuántos ticks se le dan a la página para perder la pelea y correr el
# manejador. La pelea sale a los 18 y, perdida sin pelear, no abre pantalla.
DESPUES_DE_PERDER = 60


def maximos():
    """Los HP y SP máximos de cada actor, sacados del LDB y no de la ROM.

    Es la misma cuenta que emite `actor_hpmax`, pero leída del otro lado: si
    la ROM copiara de una tabla equivocada, comparar contra esa misma tabla
    daría verde.
    """
    from port import titulo
    from rpgmaker import lcf
    from render.render_map import GAME_DIR
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    return {a: (titulo.parametro_de(actor, "maxhp"),
                titulo.parametro_de(actor, "maxsp"))
            for a, actor in db.actors.items()}


def palabra_de(una, simbolo, actor):
    bajo, alto = una.consola.ram(una.simbolos[simbolo] + 2 * actor, 2)
    return bajo | (alto << 8)


def grupo_de(una):
    """Hasta `grupo_n`: las ranuras de más no se limpian y traen basura."""
    return list(una.consola.ram(una.simbolos["grupo"], una.palabra("grupo_n")))


def perdida_y_curada(partida):
    una = partida(caso="pelea-82-curar")
    sin_hp(una)
    largo = una.simbolos["FAR_SP"] - una.simbolos["FAR_HP"]
    una.consola.escribir_ram(una.simbolos["FAR_SP"], [0] * largo)
    una.correr(DESPUES_DE_PERDER)
    return una


def test_full_heal_despues_de_perder_llena_hp_y_sp_del_grupo(partida):
    una = perdida_y_curada(partida)
    grupo = grupo_de(una)
    assert grupo, "el grupo quedó vacío: la prueba no mide nada"
    tope = maximos()
    for actor in grupo:
        hp, sp = tope[actor]
        assert palabra_de(una, "FAR_HP", actor) == hp, (
            "el actor %d quedó con %d HP después del FullHeal y el máximo es "
            "%d" % (actor, palabra_de(una, "FAR_HP", actor), hp))
        assert palabra_de(una, "FAR_SP", actor) == sp, (
            "el actor %d quedó con %d SP después del FullHeal y el máximo es "
            "%d" % (actor, palabra_de(una, "FAR_SP", actor), sp))


def test_full_heal_del_grupo_no_cura_a_los_de_afuera(partida):
    """`GetActors(0, …)` es el grupo y nadie más: uno de afuera sigue en cero.

    Sin esto, una ROM que llenara a los 61 actores —que es lo que hace
    `hp_inicial_poner`, y reusarla era la tentación— pasaría la de arriba.
    """
    una = perdida_y_curada(partida)
    afuera = [a for a in range(1, 13) if a not in grupo_de(una)]
    for actor in afuera:
        assert palabra_de(una, "FAR_HP", actor) == 0, (
            "el actor %d no está en el grupo y el FullHeal [0, 0] le llenó "
            "los HP" % actor)


def test_el_encuentro_de_despues_no_reinicia(partida):
    """El control del bug entero: con el grupo curado, un encuentro al azar se
    abre y se pelea en vez de darse por perdido y volver al título.

    `ENC_PIDE` es lo que `encuentro_paso` prende cuando sale uno; se lo prende
    a mano para no depender de caminar ni de un tiro de dado. Visto en rojo
    antes del arreglo: la ROM se reiniciaba a los pocos cuadros.
    """
    una = perdida_y_curada(partida)
    una.consola.escribir_ram(una.simbolos["ENC_PIDE"], [1])
    assert cuadros_hasta_reiniciar(una, tope=300) is None, (
        "el grupo perdió una pelea, el manejador llamó a FullHeal, y el "
        "encuentro siguiente igual volvió al título: los HP no se curaron")
    assert una.byte("menu_abierto"), (
        "el encuentro no abrió la pelea: sin eso, que no se reinicie no dice "
        "nada")


# --- `ChangeHP` que suma -----------------------------------------------------
#
# Comparte OP_HEAL con `FullHeal`, con la cantidad puesta, y hasta el
# 2026-09-19 compilaba a nada por el mismo motivo. Es `Game_Battler::ChangeHp`:
# al caído no lo levanta, topa en el máximo y no toca los SP. La página
# `curar-sumar` espera 18 ticks —los que la prueba usa para poner los HP de
# partida— y suma 5 al grupo, 3 al actor 11, y 999 al 12 y al 13.

def sumada(partida, hp):
    una = partida(caso="curar-sumar")
    for actor, valor in hp.items():
        una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * actor,
                                 [valor & 0xFF, valor >> 8])
    una.consola.escribir_ram(una.simbolos["FAR_SP"] + 2 * 10, [0, 0])
    una.correr(DESPUES_DE_PERDER)
    return una


def test_change_hp_suma_al_grupo_y_a_un_actor(partida):
    una = sumada(partida, {10: 10, 11: 50})
    assert grupo_de(una) == [10], (
        "el caso cuenta con el grupo de arranque del cartucho, que es el "
        "actor 10 solo, y es %s" % grupo_de(una))
    assert palabra_de(una, "FAR_HP", 10) == 15, (
        "ChangeHP de 5 al grupo dejó al actor 10 en %d, desde 10"
        % palabra_de(una, "FAR_HP", 10))
    assert palabra_de(una, "FAR_HP", 11) == 53, (
        "ChangeHP de 3 al actor 11 lo dejó en %d, desde 50"
        % palabra_de(una, "FAR_HP", 11))
    assert palabra_de(una, "FAR_SP", 10) == 0, (
        "ChangeHP le tocó los SP al actor 10: los dejó en %d"
        % palabra_de(una, "FAR_SP", 10))


def test_change_hp_topa_en_el_maximo_y_no_levanta_a_un_caido(partida):
    una = sumada(partida, {12: 1, 13: 0})
    assert palabra_de(una, "FAR_HP", 12) == maximos()[12][0], (
        "ChangeHP de 999 al actor 12 lo dejó en %d, y el máximo es %d"
        % (palabra_de(una, "FAR_HP", 12), maximos()[12][0]))
    assert palabra_de(una, "FAR_HP", 13) == 0, (
        "ChangeHP levantó al actor 13, que estaba caído: quedó en %d"
        % palabra_de(una, "FAR_HP", 13))


# --- y el `FullHeal` que el jugador usa a propósito --------------------------

def test_el_balde_del_mapa_23_deja_los_hp_llenos(partida):
    """El Life Bucket, que es el otro `FullHeal` que taro no veía curar.

    El caso `curar-balde` deja al héroe dos celdas debajo del balde; desde ahí
    la prueba camina hasta chocarlo —así queda mirándolo, que es lo que el
    trigger de acción pide— y le da A. Visto en rojo con el conversor
    emitiendo nada para `FullHeal`: el actor 10 se quedaba en 7 HP mientras el
    cartel decía "HP and SP completely recovered!".
    """
    una = partida(caso="curar-balde")
    una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * 10, [7, 0])
    for _ in range(240):
        una.consola.apretar("up")
        una.consola.correr(1)
    una.consola.apretar()
    for n in range(120):
        una.consola.apretar(*(("a",) if n % 8 < 2 else ()))
        una.consola.correr(1)
    una.consola.apretar()
    assert palabra_de(una, "FAR_HP", 10) == maximos()[10][0], (
        "el balde dejó al actor 10 en %d y su máximo es %d"
        % (palabra_de(una, "FAR_HP", 10), maximos()[10][0]))
