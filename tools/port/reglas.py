"""Reglas de RM2k que usan varios módulos del port: qué sabe un actor, qué
parámetros tiene a su nivel y cómo se llaman los términos de la pelea.

Son de `Game_Actor` y del LDB, no de ninguna pantalla.
"""


def aprendidas_de(db, numero, nivel=None):
    """Las habilidades que este actor **sabe**, usables o no, ordenadas.

    Es `Game_Actor::LearnLevelSkills` a secas: las de nivel menor o igual al
    suyo. Va aparte de `habilidades_de` porque son dos preguntas distintas y
    confundirlas se paga de un solo lado: el menú de la pelea sólo puede
    ofrecer las que este port sabe ejecutar —ése es el filtro de
    `habilidad_usable`— pero `IsSkillLearned`, que es lo que pregunta la rama
    de `ConditionalBranch`, no filtra nada.

    Las dos salen de acá para que no puedan separarse: la rama y el menú tienen
    que estar de acuerdo en qué sabe cada uno.
    """
    actor = db.actors[numero]
    if nivel is None:
        nivel = actor.initial_level
    return sorted({s for aprende, s in actor.skills
                   if s and aprende <= nivel})


# El nivel de cada actor sale del LDB desde el 2026-09-13: es su
# `initial_level`, que en el ABL no es 1 —Kersh arranca en 20, Core y Manta en
# 15— y de él salen los HP, los SP y los cuatro parámetros.
#
# Hasta ese día acá había un `NIVEL = 1` mockeado, y **no era sólo cosmético**:
# con él Kersh mostraba 40 HP en vez de 168 y peleaba con ataque 17 en vez de
# 80, así que el balance entero de la pelea era otro. Y de ahí salió además la
# conclusión equivocada de que nadie sabía ninguna habilidad: todas se aprenden
# en el nivel 3 o más arriba, y con el nivel inicial de verdad los tres las
# saben desde la primera pelea.
#
# Subir de nivel sigue sin existir, y eso sí es una decisión: no hay
# experiencia. El nivel es un dato estático del LDB.


def nivel_de(actor):
    """El nivel con el que arranca un actor: `Game_Actor::Setup`, que llama a
    `ChangeLevel(initial_level)` cuando el campo está."""
    return actor.initial_level


def parametro_de(actor, cual, nivel=None):
    """Un parámetro del actor a su nivel: `maxhp`, `maxsp`, `attack`,
    `defense`, `spirit` o `agility`.

    La tabla del LDB va desde el nivel 1, así que el índice es el nivel menos
    uno. Un actor sin la tabla —o con una más corta que su nivel, que no pasa
    en este juego— da cero, que es lo que hacía el código de antes.

    Sin `nivel` es el de arranque; con él, el que haya subido peleando: ver
    `port.experiencia`.
    """
    valores = actor.params.get(cual) or []
    if nivel is None:
        nivel = nivel_de(actor)
    return valores[nivel - 1] if nivel - 1 < len(valores) else 0


PARAM_MAX = 999


def parametros(db, actor, equipo, nivel=None):
    """Ataque, defensa, espíritu y agilidad: los del nivel más lo que suma el
    equipo, topados en [1, 999] como `Game_Actor::GetAtk` y sus hermanas. Sin
    `nivel`, el de arranque."""
    base = [parametro_de(db.actors[actor], k, nivel)
            for k in ("attack", "defense", "spirit", "agility")]
    for item in equipo:
        if item:
            base = [b + p for b, p in zip(base, db.items[item].puntos)]
    return [max(1, min(PARAM_MAX, b)) for b in base]


# Los términos del LDB que la pantalla usa, en el orden en que el conversor los
# emite. Los nombres son los de liblcf —`fields.csv`, struct `Terms`— y no de
# memoria: ver data/README.md. Hasta el 2026-09-20 eran los números de chunk
# de `ldb/chunks.h`, con el nombre al lado en un comentario; hoy el nombre es
# el dato y el comentario es lo que dice el término en el juego.
BA_TERMINOS = (
    ("atacar", "command_attack"),        # "Attack"
    ("defender", "command_defend"),      # "Defend"
    ("huir", "battle_escape"),           # "Escape"
    ("hp", "hp_short"),                  # "HP"
    ("ataca", "attacking"),              # " attacks the enemy"
    ("defiende", "defending"),
    ("critico", "actor_critical"),
    ("dano_enemigo", "enemy_damaged"),   # " health lost."
    ("sin_dano_enemigo", "enemy_undamaged"),
    ("dano_actor", "actor_damaged"),
    ("sin_dano_actor", "actor_undamaged"),
    ("victoria", "victory"),
    ("derrota", "defeat"),
    ("huyo", "escape_success"),
    ("no_huyo", "escape_failure"),
    # Los cuatro del 2026-09-13: las dos órdenes que faltaban y los dos
    # renglones del mensaje de usar un ítem.
    ("usar", "command_item"),            # "Use Item"
    ("habilidad", "command_skill"),      # "Tech Skill"
    ("uso", "use_item"),                 # " used."
    ("recupero", "hp_recovery"),         # " Recovered"
    # Los cuatro de lo que la victoria cuenta, desde el 2026-09-26: ver
    # `ba_vic_mensaje` en batalla_victoria.s.
    ("exp_recibida", "exp_received"),    # " EXP"
    ("nivel", "level"),                  # "LEVEL"
    ("subio", "level_up"),               # " achieved!"
    ("aprendio", "skill_learned"),       # " acquired!"
    # Y los del oro y los ítems que se ganan, desde el 2026-09-27.
    ("oro_a", "gold_recieved_a"),        # " You found"
    ("moneda", "gold"),                  # "Cr"
    ("oro_b", "gold_recieved_b"),        # " credits!"
    ("obtenido", "item_recieved"),       # " obtained!"
)


def terminos_batalla(db):
    from rpgmaker import lcf
    return {n: lcf.to_string(db.terminos[t]) for n, t in BA_TERMINOS}
