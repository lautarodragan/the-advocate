"""La experiencia y el nivel de los actores, como RM2k.

Es el hermano de `batalla.py` para lo que pasa **después** de la pelea: cuánta
experiencia da, cuándo se sube de nivel y qué parámetros quedan. La ROM hace
la misma cuenta, y las pruebas exigen el mismo número de los dos lados.

**Ningún número de acá es nuestro.** Salen de easyrpg-player, clonado en
`/extras/ref`:

    src/game_actor.cpp          CalculateExp, MakeExpList, GetNextExp,
                                GetMaxLevel, ChangeExp, ChangeLevel,
                                GetBaseMaxHp y sus hermanas
    src/game_constants.cpp      MaxExpValue, MaxLevel
    src/game_enemyparty.cpp     GetExp
    src/scene_battle_rpg2k.cpp  ProcessSceneActionVictory

Lo que la ROM **no** hace en punto flotante es calcular la curva: la calcula
el conversor, acá, y viaja en el cartucho como una tabla por nivel. Así el
`double` de easyrpg es el `float` de Python, que es el mismo IEEE 754 de 64
bits, y el truncado del `(int)` de C++ es el `int()` de Python. No hay
aproximación que declarar.
"""

from port.constantes import ENEMIGOS_MAX

# `MaxExpValue()` y `MaxLevel()` de RM2k: `easyrpg_max_exp` y
# `easyrpg_max_level` vienen en -1 en un LDB de RM2k, y con eso valen éstos.
EXP_MAX = 999999
NIVEL_MAX = 50


def nivel_max(actor):
    """`Game_Actor::GetMaxLevel`: el de RM2k topado por el `final_level`."""
    return max(1, min(NIVEL_MAX, actor.final_level))


def exp_para(actor, nivel):
    """`Game_Actor::CalculateExp` con la curva de RM2k (`exp_curve == 1`).

    Es la experiencia **acumulada** que hace falta para pasar del nivel
    `nivel` al siguiente. El lazo va del nivel hacia abajo, y la inflación se
    recalcula con `level + 1` fijo —el del argumento, no el del lazo—: es lo
    que está escrito en easyrpg y no una errata de acá.
    """
    base = float(actor.exp_base)
    inflacion = 1.5 + actor.exp_inflation * 0.01
    correccion = float(actor.exp_correction)
    resultado = 0
    for _ in range(nivel, 0, -1):
        resultado = resultado + int(correccion + base)
        base = base * inflacion
        inflacion = ((nivel + 1) * 0.002 + 0.8) * (inflacion - 1) + 1
    return min(resultado, EXP_MAX)


def lista_de(actor):
    """`Game_Actor::MakeExpList`: `lista[n]` es lo que pide pasar del `n` al
    `n + 1`, y `lista[0]` queda en cero. Mide `GetMaxLevel()`."""
    return [0] + [exp_para(actor, n) for n in range(1, nivel_max(actor))]


def siguiente(actor, nivel):
    """`Game_Actor::GetNextExp(level)`: -1 en el tope."""
    if nivel >= nivel_max(actor) or nivel <= -1:
        return -1
    if nivel == 0:
        return 0
    return lista_de(actor)[nivel]


def exp_inicial(actor):
    """Con cuánta experiencia arranca: el constructor de `Game_Actor` pone el
    nivel en 0 y llama a `ChangeLevel(initial_level)`, que deja la
    experiencia en `GetBaseExp()`, o sea `GetNextExp(nivel - 1)`."""
    return max(0, siguiente(actor, nivel_inicial(actor) - 1))


def nivel_inicial(actor):
    """`SetLevel` topa el `initial_level` entre 1 y el máximo."""
    return max(1, min(nivel_max(actor), actor.initial_level))


def sumar(actor, nivel, exp, cantidad):
    """`Game_Actor::ChangeExp(GetExp() + cantidad)` para una cantidad que no
    resta, que es la única que la pelea da. Devuelve `(nivel, exp)`.

    El lazo de easyrpg sube mientras `GetNextExp(nivel)` no sea -1 y no pase
    de la experiencia nueva; con -1 —el tope— sigue sumando, pero el `for` ya
    no da más vueltas y `SetLevel` lo topa igual. La experiencia de ajuste de
    `ChangeLevel` —`max(GetBaseExp(), GetExp())`— no mueve nada subiendo,
    porque la base del nivel nuevo nunca pasa de lo que se tiene.
    """
    nueva = max(0, min(EXP_MAX, exp + cantidad))
    if nueva > exp:
        for _ in range(nivel + 1, nivel_max(actor) + 1):
            proximo = siguiente(actor, nivel)
            if proximo != -1 and proximo > nueva:
                break
            nivel += 1
    return min(nivel, nivel_max(actor)), nueva


def exp_de_la_tropa(db, tropa):
    """`Game_EnemyParty::GetExp`: la de cada enemigo **muerto**. Una victoria
    los tiene a todos muertos menos los que siguieron ocultos, así que ésta es
    la suma de la tropa entera, hasta `ENEMIGOS_MAX` como la pelea, y la ROM
    le resta la de los ocultos al ganar: ver `ba_sin_ocultos` y
    `batalla.Batalla.experiencia`."""
    return sum(db.enemies[e].exp
               for e in db.troops[tropa].members[:ENEMIGOS_MAX])
