"""El modelo de la pelea contra el que se compara la consola: la pelea de RM2k
jugada con las mismas reglas y el mismo azar que la ROM, que es
`rm2k-snes-battle simulate`. Así una prueba puede decir **el número exacto**
que la consola tiene que dejar en cada HP, turno por turno.

Hasta el 2026-09-30 era `port/battle.py`, en Python; se fue cuando la pelea
pasó a Rust, y lo que quedó acá es cómo se le pide. Los nombres —`Battle`,
`play_turn`, `actor_of`— son los del modelo de antes y los de la respuesta de
la etapa, para que las pruebas no cambien de forma.

**La etapa no guarda estado entre llamados**: una `Battle` guarda los pasos
—empezar, cada turno, huir, poner HP— y vuelve a jugar la pelea entera cada
vez que hay que mirarla. Es determinista, así que da lo mismo, y cada
llamado cuesta lo que leer el volcado.

Las constantes —`COMMAND_ATTACK`, `VICTORY` y compañía— y la geometría de la
pantalla (`disposicion()`) salen de la etapa también: `rm2k-snes-battle
layout`.
"""

import json
import types

import screen_stage
import stage
from resources import GAME_DIR

BINARIO = "rm2k-snes-battle"
PROYECTO = "battle"


def _pedir(comando, archivo, pedido, *flags):
    escrito = stage.run(BINARIO, PROYECTO, comando, pedido, *flags)
    return json.loads(escrito[archivo])


def _al_volcado(comando, archivo, pedido):
    return _pedir(comando, archivo, pedido,
                  "--data", screen_stage.dump_of(GAME_DIR))


_DISPOSICION = []


def disposicion():
    """La geometría de la pantalla de la pelea y las constantes del modelo,
    por nombre: `disposicion().BA_MSG_ROW1`, `disposicion().VICTORY`."""
    if not _DISPOSICION:
        _DISPOSICION.append(types.SimpleNamespace(
            **_pedir("layout", "layout.json", {})))
    return _DISPOSICION[0]


def __getattr__(nombre):
    """`modelo.COMMAND_ATTACK`, `modelo.VICTORY`: los de la etapa."""
    if nombre.isupper() and hasattr(disposicion(), nombre):
        return getattr(disposicion(), nombre)
    raise AttributeError(nombre)


# --- los que pelean -----------------------------------------------------------

class _Suelto:
    """Un actor o un enemigo antes de entrar a una pelea: lo que se le pide a
    la etapa para armarlo. Sus números —`hp_max`, `skills`— se leen armando
    una pelea con él solo; `skills` se puede cambiar, que es lo que hace un
    `ChangeSkills`."""

    def __init__(self, pedido, enemigo=False):
        object.__setattr__(self, "_pedido", pedido)
        object.__setattr__(self, "_enemigo", enemigo)
        object.__setattr__(self, "_datos", None)

    def __getattr__(self, nombre):
        if self._datos is None:
            lado = "enemies" if self._enemigo else "actors"
            pedido = {lado: [self._pedido], "steps": []}
            object.__setattr__(self, "_datos", _al_volcado(
                "simulate", "simulate.json", pedido)["battle"][lado][0])
        try:
            return self._datos[nombre]
        except KeyError:
            raise AttributeError(nombre) from None

    def __setattr__(self, nombre, valor):
        if nombre != "skills" or self._enemigo:
            raise AttributeError("de uno que todavía no pelea sólo se "
                                 "cambian las habilidades de un actor")
        self._pedido["skills"] = list(valor)
        object.__setattr__(self, "_datos", None)


def actor_of(numero, equipment=None, level=None):
    """El actor `numero` del LDB con `equipment` puesto —sin él, el de
    arranque— y en `level` —sin él, el de arranque—."""
    return _Suelto({"id": numero, "level": level,
                    "equipment": None if equipment is None
                    else list(equipment)})


def enemy_of(numero, puesto, hidden=False):
    """El enemigo `numero` del LDB en el lugar `puesto` de la tropa."""
    return _Suelto({"id": numero, "place": puesto, "hidden": hidden},
                   enemigo=True)


class Combatiente:
    """Uno de los que pelean, como lo dejó el último paso: los campos de la
    respuesta de la etapa, como atributos —`hp`, `sp_max`, `hidden`,
    `alive`, `skills`, `weapon_sp`—. Poner `hp` o `sp` es un paso más de la
    pelea."""

    def __init__(self, pelea, lado, puesto):
        object.__setattr__(self, "_pelea", pelea)
        object.__setattr__(self, "_lado", lado)
        object.__setattr__(self, "_puesto", puesto)

    def __getattr__(self, nombre):
        try:
            return self._pelea._estado()[self._lado][self._puesto][nombre]
        except KeyError:
            raise AttributeError(nombre) from None

    def __setattr__(self, nombre, valor):
        if nombre not in ("hp", "sp"):
            raise AttributeError("de uno que pelea sólo se ponen hp y sp")
        self._pelea._paso({"set": {"side": self._lado,
                                   "place": self._puesto, nombre: valor}})


class Battle:
    """Una pelea: `actors`, de `actor_of`; los enemigos, de `enemy_of` o los
    de la tropa `troop`; `pages`, la tropa cuyas páginas corren; `switches`,
    `{número: prendido}`, los que miran las páginas.

    Una orden por actor vivo, en el orden del grupo: `(COMMAND_ATTACK,
    lugar del enemigo)`, `(COMMAND_DEFEND, 0)`, `(COMMAND_ITEM, (ítem, lugar
    del actor))` o `(COMMAND_SKILL, (habilidad, lugar))`, con el ítem y la
    habilidad por su número del LDB."""

    def __init__(self, actors, enemies=None, seed=None, troop=None,
                 pages=None, switches=None):
        self._pedido = {
            "seed": seed,
            "actors": [a._pedido for a in actors],
            "enemies": None if enemies is None
            else [e._pedido for e in enemies],
            "troop": troop, "pages": pages,
            "switches": {str(k): bool(v)
                         for k, v in (switches or {}).items()},
            "steps": [],
        }
        self._respuesta = None

    # --- los pasos -----------------------------------------------------------
    def _jugar(self):
        self._respuesta = _al_volcado("simulate", "simulate.json",
                                      self._pedido)

    def _estado(self):
        if self._respuesta is None:
            self._jugar()
        return self._respuesta["battle"]

    def _paso(self, paso, devuelve=False):
        self._pedido["steps"].append(paso)
        self._respuesta = None
        if devuelve:
            self._jugar()
            return self._respuesta["steps"][-1]
        return None

    def start(self):
        """Lo de antes de las primeras órdenes, en el turno 0: las páginas."""
        self._paso({"start": None})

    def play_turn(self, ordenes):
        """Un turno entero. Devuelve el resultado si la pelea terminó, o
        None."""
        turno = []
        for orden, blanco in ordenes:
            if orden in (disposicion().COMMAND_ITEM,
                         disposicion().COMMAND_SKILL):
                cual, lugar = blanco
                turno.append([orden, cual, lugar])
            else:
                turno.append([orden, blanco])
        return self._paso({"turn": turno}, devuelve=True)

    def flee(self):
        """`TryEscape`: si se escapó."""
        return self._paso({"flee": None}, devuelve=True)

    def enemy_action(self, enemigo):
        """Lo que elige hacer `enemigo`: `(rating, habilidad, efectiva)`, con
        la habilidad por número o None para el ataque; None si no le queda
        ninguna. Tira el azar como en la pelea."""
        accion = self._paso({"enemy_action": enemigo._puesto}, devuelve=True)
        return None if accion is None else tuple(accion)

    # --- lo que se mira ------------------------------------------------------
    @property
    def actors(self):
        return [Combatiente(self, "actors", k)
                for k in range(len(self._estado()["actors"]))]

    @property
    def enemies(self):
        return [Combatiente(self, "enemies", k)
                for k in range(len(self._estado()["enemies"]))]

    def living(self, quienes):
        return [c for c in quienes if c.alive]

    def __getattr__(self, nombre):
        """`result`, `turn`, `drops`, `switches`, `escape_chance`, `log`."""
        if nombre.startswith("_"):
            raise AttributeError(nombre)
        try:
            return self._estado()[nombre]
        except KeyError:
            raise AttributeError(nombre) from None

    def experience(self):
        """`Game_EnemyParty::GetExp` al ganar: la de los que no quedaron
        ocultos."""
        return self._estado()["experience"]

    def gold(self):
        return self._estado()["gold"]


# --- lo que el modelo dice del LDB -------------------------------------------

def skills_of(actor, level=None):
    """Las habilidades que el menú de la pelea le ofrece al actor, en el
    orden en que las pone."""
    return actor_of(actor, level=level).skills


def actions_of_enemy(enemigo):
    """Lo que el enemigo sabe hacer: `(rating, habilidad, efectiva)`, con la
    habilidad por número o None para el ataque."""
    return [tuple(a) for a in enemy_of(enemigo, 0).actions]


def _modelo(**pedido):
    base = {"actors": [], "troops": [], "items": [], "skill_pairs": [],
            "item_name_width": screen_stage.layout().ITEM_NAME_WIDTH}
    base.update(pedido)
    return _al_volcado("model", "model.json", base)


def items_usable_in_battle(items):
    """De `items`, los que la pelea ofrece en su lista."""
    items = list(items)
    usables = _modelo(items=items)["item_battle"]
    return [i for i, si in zip(items, usables) if si]


def troop_gold(tropa):
    """El oro de la tropa entera, como lo suma el conversor."""
    return _modelo(troops=[tropa])["troops"][0]["gold"]


# --- los renglones de la victoria --------------------------------------------

def renglones(*pedidos):
    """Los renglones de la victoria como los arma la ROM, uno por pedido:
    `("victory",)` —el término partido, que es más de uno—, `("exp", n)`,
    `("gold", n)`, `("item", ítem)`, `("level", actor, nivel)` y
    `("skill", habilidad)`."""
    return _al_volcado("lines", "lines.json", {
        "item_name_width": screen_stage.layout().ITEM_NAME_WIDTH,
        "lines": [list(p) for p in pedidos]})["lines"]


def renglones_de_victoria():
    return renglones(("victory",))[0]


def renglon_de_exp(exp):
    return renglones(("exp", exp))[0][0]


def renglon_de_oro(oro):
    return renglones(("gold", oro))[0][0]


def renglon_de_item(item):
    return renglones(("item", item))[0][0]


def renglon_de_nivel(actor, nivel):
    return renglones(("level", actor, nivel))[0][0]


def renglon_de_habilidad(habilidad):
    return renglones(("skill", habilidad))[0][0]
