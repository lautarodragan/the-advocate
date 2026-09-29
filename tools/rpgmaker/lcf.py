"""The game, read from the JSON dump in `rom/data/`.

Until 2026-09-14 this parsed the RPG Maker 2000 binaries on every build
—that reader was deleted when it no longer had anyone using it—. Since then
the format is read **only once**, in Ditto, and what is in `rom/data/` is the
result: `maps/MapNNNN.json` with its `.tiles` beside it, `maps.json` with the
tree and `db/*.json` with the database's fifteen sections. The why is in
`DITTO.md`; what is inside `rom/data/`, in `rom/data/README.md`.

**The consumers did not notice.** The classes here —`Map`, `Database`,
`TreeMap` and everything hanging off them— have the same attributes as
before, with the same types, and still receive the path to a `.lmu` or to an
`RPG_RT.ldb`: of that path only **the name** is used, to know which map it
is, and the directory only if it has a dump of its own inside (a
`ditto.json`). The graphics and the audio still come from the real game,
which is what `--game-dir` names.

**And no rule of the format comes out of this file.** What is in `rom/data/`
is the *resolved view* Ditto emits: **every field written**, with its default
already applied, and the enums as the number the binary stores. So reading
is reading: `data["max_hp"]` and that's it. A missing field is a
`KeyError`, and that is what we want —it means `rom/data/` is stale, not that
it is zero—.

Until 2026-09-20 this read the *exact dump* —defaults omitted, enums by
name— and it needed the format's schema to understand it: `ditto_schema.py`
and its JSON, published by `ditto schema`. Both went away with this change.
The exact dump is still generated, in the same run, because it is what Ditto
rebuilds the binary from; what is no longer versioned is that.

What does still belong here is **guessing a text's encoding**: see `text`.
That is not a rule of the format, it is the opposite —the format does not
say which character set a string is in—.
"""

import json
import os

from common import project
from rpgmaker import fork
from rpgmaker.event_codes import EVENT_CODES

MANIFEST = "ditto.json"


def dump_dir(path):
    """Where to read from: the directory's own dump, or the repo's.

    Callers pass a path inside the original game —`--game-dir`—, which is
    where the PNGs and the MIDIs still come from. If that directory has a
    Ditto dump inside, that one is used, which is how a game other than this
    one is read; if not, the one in `rom/data/`, which is the repo's.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if os.path.isfile(os.path.join(directory, MANIFEST)):
        return directory
    return project.data()


def read_json(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return json.load(handle)


# --- Access to a field ------------------------------------------------------
#
# Three lines, and that is the idea: the resolved view brings every field, so
# there is no default to apply and no enum to translate. The only thing left
# is the text, which is not part of the format.

def field(data, name):
    """A field. Its absence is an error, not a default."""
    value = data[name]
    return text(value) if isinstance(value, str) else value


def list_field(data, name):
    return data[name]


def sub(data, name):
    return data[name]


def by_id(elements):
    """An array of structs as `{id: element}`, which is how it is indexed.

    In the binary the id is the tag with which the array names each element;
    in the JSON it is one more field of the object.
    """
    return {element["id"]: element for element in elements}


# The five bytes cp1252 does not define. Ditto writes them as their C1 control
# so the table is a bijection and no byte is lost; here they are the sign that
# the text is not cp1252.
C1 = {"\x81": 0x81, "\x8d": 0x8D, "\x8f": 0x8F, "\x90": 0x90, "\x9d": 0x9D}


def text(value):
    """A text from the game, with the leftovers of the Japanese RTP read as such.

    ABL was made with Don Miguel's RPG Maker 2000, so almost everything is
    cp1252; a couple of messages the author never touched are still in
    Shift-JIS. Ditto stores them as they came —decoding by guessing would
    cost it the exact round trip, which is the only thing that makes it
    useful—, so the one who guesses is this: if the text carries any of the
    five bytes cp1252 does not define, it is reassembled and read as
    Shift-JIS. They are four strings of the LDB.
    """
    if not any(c in value for c in C1):
        return value
    raw = bytearray()
    for ch in value:
        if ch in C1:
            raw.append(C1[ch])
        else:
            try:
                raw.extend(ch.encode("cp1252"))
            except UnicodeEncodeError:
                return value
    try:
        return bytes(raw).decode("shift_jis")
    except UnicodeDecodeError:
        return value


def to_string(payload):
    """What is left of the binary reader: `db.terms` still gives bytes."""
    return text(payload.decode("cp1252", errors="replace"))



# --- Enums, to name them in a dump or in a message --------------------------
#
# The names are liblcf's and the order is that of their numbers. **They are
# not used to read anything**: `rom/data/` brings the enums as numbers, which
# is what the port wants. These are here to name them —a dump, an error
# message— and for the ones that have to be walked by index.

DIRECTIONS = ("up", "right", "down", "left")
PATTERNS = ("left", "middle", "right", "middle2")
MOVE_TYPES = ("stationary", "random", "vertical", "horizontal",
              "toward", "away", "custom")
TRIGGERS = ("action", "touched", "collision", "auto_start", "parallel")
LAYERS = ("below", "same", "above")
ANIM_TYPES = ("non_continuous", "continuous", "fixed_non_continuous",
              "fixed_continuous", "fixed_graphic", "spin", "step_frame_fix")
MOVE_SPEEDS = (None, "eighth", "quarter", "half", "normal", "double", "fourfold")
COMPARISONS = ("equal", "greater_equal", "less_equal",
               "greater", "less", "not_equal")

# A page's conditions, in the order of their bits. `timer2` only exists in
# RPG Maker 2003: in a 2000 file it has no bit and is never on.
CONDITION_NAMES = ("switch_a", "switch_b", "variable", "item",
                   "actor", "timer", "timer2")
# And which field answers each one. `timer`'s is its number of seconds,
# which is what the format stores; `timer2` is from 2003 and is not there.
CONDITION_FIELDS = {"switch_a": "switch_a_id", "switch_b": "switch_b_id",
                    "variable": "variable_id", "item": "item_id",
                    "actor": "actor_id", "timer": "timer_sec"}
# `compare_operator` is chunk 0x0A of `EventPageCondition` and **belongs to
# RPG Maker 2003** (liblcf, `generator/csv/fields.csv`: "Integer - RPG2003").
# Ditto targets 2000 and does not generate it, so in this game it is never
# written and always holds its default, which that same line gives as 1.
CONDITION_OPERATOR_DEFAULT = 1


# --- The game's types -------------------------------------------------------

class EventCommand:
    """One line of a page's script.

    The format is uniform for RM2k's ~130 commands, so all of them can be
    read without knowing what each code does: code, indent, a string and a
    list of integers. Interpreting them is a different matter.
    """

    __slots__ = ("code", "indent", "string", "parameters")

    def __init__(self, code, indent, string, parameters):
        self.code = code
        self.indent = indent
        self.string = string
        self.parameters = parameters


# Text boxes rebuilt for another screen: a function that receives a page's
# commands as they are in the JSON and returns different ones. The port sets
# `texts.refit_commands`; the reader knows nothing about screens, and
# with nobody setting it the game is read as is.
#
# It is a step separate from `rom/parches/`, and runs after it: it reads
# whatever is left, and a box that already fits is left as it is. That way a
# text corrected by hand in a fork under `rom/parches/manual/` always wins.
#
# It applies to the maps' pages and to the common events, and not to the
# troops': the battle window has a different width.
REFIT_TEXTS = None


def commands(data, refit=False):
    """The command list of a page or a common event. With `refit`, run
    through REFIT_TEXTS if someone set it."""
    raw = list_field(data, "event_commands")
    if refit and REFIT_TEXTS:
        raw = REFIT_TEXTS(raw)
    return [EventCommand(field(c, "code"),
                         field(c, "indent"),
                         field(c, "string"),
                         field(c, "parameters") or [])
            for c in raw]


def handwritten_commands(data):
    """The same, but from a list **written by hand**: `rom/pruebas/casos/*.json`.

    Those files do not come from `rom/data/`: we write them, and that is why
    they are in the shorthand that can be written —the command by its name,
    `ShowMessage`, and only the fields that say something—. A case converted
    to the resolved view would be unreadable and nobody would edit it, so the
    shorthand stays and what goes beside it is this reader, which is six
    lines.

    The three missing fields take the obvious values —indent 0, no text, no
    parameters— and there is no schema to consult: the only outside data is
    each name's number, which comes from `event_codes.json`, the liblcf table
    that stays precisely for this and for error messages.
    """
    number = {name: code for code, name in EVENT_CODES.items()}
    return [EventCommand(number[c["code"]] if isinstance(c["code"], str)
                         else c["code"],
                         c.get("indent", 0), text(c.get("string", "")),
                         c.get("parameters") or [])
            for c in data["event_commands"]]


# If not None, the CharSet name of a translucent page goes through here and,
# for whoever reads it, it is a different graphic. The port turns it on —see
# `rm2k.decorate_translucent`— and not the reader: the JSON dump has to keep
# seeing the real name.
#
# It also receives **where the event stands** (map, x, y), because the baking
# needs the real background of that cell; that is why it is decorated not on
# the page, which does not know it, but on the event.
DECORATE_TRANSLUCENT = None


class EventPageCondition:
    """What has to happen for this page to be the active one."""

    def __init__(self, data):
        flags = sub(data, "flags")
        self.active = [n for n in CONDITION_NAMES if flags.get(n)]
        self.ids = {n: field(data, c)
                    for n, c in CONDITION_FIELDS.items()}
        self.ids["timer2"] = 0
        self.variable_value = field(data, "variable_value")
        self.operator = CONDITION_OPERATOR_DEFAULT

    def __bool__(self):
        return bool(self.active)


class MoveRoute:
    """A page's own route: the commands, whether it repeats and whether a
    blocked command is skipped.

    Of each command only the code is kept; none of the four that take
    operands is executed.
    """

    def __init__(self, data):
        self.repeat = field(data, "repeat")
        self.skippable = field(data, "skippable")
        self.commands = [field(c, "command_id")
                         for c in list_field(data, "move_commands")]


class EventPage:
    """One of the versions an event can take."""

    def __init__(self, data):
        self.character_name = field(data, "character_name")
        self.translucent = field(data, "translucent")
        self.character_index = field(data, "character_index")
        self.character_direction = field(data, "character_direction")
        self.character_pattern = field(data, "character_pattern")
        self.move_type = field(data, "move_type")
        self.move_frequency = field(data, "move_frequency")
        self.move_speed = field(data, "move_speed")
        self.trigger = field(data, "trigger")
        self.layer = field(data, "layer")
        self.overlap_forbidden = field(data, "overlap_forbidden")
        self.animation_type = field(data, "animation_type")
        self.commands = commands(data, refit=True)
        self.move_route = MoveRoute(sub(data, "move_route"))
        self.condition = EventPageCondition(sub(data, "condition"))
        self.unconditional = not self.condition


class Event:
    def __init__(self, data, map_id=0):
        self.id = field(data, "id")
        self.name = field(data, "name")
        self.x = field(data, "x")
        self.y = field(data, "y")
        self.pages = [EventPage(p) for _, p
                      in sorted(by_id(list_field(data, "pages")).items())]
        if DECORATE_TRANSLUCENT:
            # See DECORATE_TRANSLUCENT: for the port, a translucent CharSet is
            # a different graphic, and if it is baked it also depends on
            # where it stands.
            for page in self.pages:
                if page.translucent and page.character_name:
                    page.character_name = DECORATE_TRANSLUCENT(
                        page.character_name, map_id, self.x, self.y)

    def active_page(self):
        """The page the engine would show in a freshly started game.

        RM2k uses the highest-numbered page whose conditions are all met.
        With no switches or variables set, that is the last page that has no
        condition at all. There may be none.
        """
        for page in reversed(self.pages):
            if page.unconditional:
                return page
        return None


def layers(path, data, width, height):
    """The two tile layers, from the `.tiles` beside it or from the JSON itself.

    Ditto takes them out of the JSON and writes them as a text grid, one row
    per line, so that a changed tile shows up in the diff where it is on the
    map. A layer that does not fit in a `width * height` grid stays inside the
    JSON, so both sides have to be looked at.
    """
    if not os.path.isfile(path):
        return (field(data, "lower_layer") or [],
                field(data, "upper_layer") or [])

    grids = [[]]
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                if grids[-1]:
                    grids.append([])
                continue
            grids[-1].extend(int(t) for t in line.split())
    expected = width * height
    if len(grids) != 2 or any(len(c) != expected for c in grids):
        raise ValueError("%s: %s tiles for a %dx%d map"
                         % (path, [len(c) for c in grids], width, height))
    return grids[0], grids[1]


class Map:
    def __init__(self, path):
        # The map number is not inside the file: it comes from the name,
        # which is where the whole rest of the port gets it from. The baked
        # translucent events need it, since they carry in their graphic's
        # name where they stand.
        base = os.path.basename(path)
        self.map_id = int(base[3:7]) if base[3:7].isdigit() else 0
        root = dump_dir(path)
        # The fork belongs only to **this** game: another game is read by
        # passing it its own dump, and there `rom/parches/manual/` has no
        # say. And the same for a map the game does not have: see
        # `fork.new_maps`.
        forked = ((fork.map_fork(self.map_id) or fork.new_map(self.map_id))
                  if root == project.data() else None)
        if forked:
            json_path, tiles_path = forked
            data = read_json(json_path)
        else:
            json_path = os.path.join(root, "maps", "Map%04d.json" % self.map_id)
            tiles_path = os.path.join(root, "maps",
                                      "Map%04d.tiles" % self.map_id)
            data = read_json(json_path)

        self.chipset_id = field(data, "chipset_id")
        self.width = field(data, "width")
        self.height = field(data, "height")
        self.scroll_type = field(data, "scroll_type")
        self.parallax_flag = field(data, "parallax_flag")
        self.parallax_name = field(data, "parallax_name")
        self.parallax_loop_x = field(data, "parallax_loop_x")
        self.parallax_loop_y = field(data, "parallax_loop_y")
        self.parallax_auto_loop_x = field(data, "parallax_auto_loop_x")
        self.parallax_auto_loop_y = field(data, "parallax_auto_loop_y")
        self.parallax_sx = field(data, "parallax_sx")
        self.parallax_sy = field(data, "parallax_sy")
        self.lower_layer, self.upper_layer = layers(
            tiles_path, data, self.width, self.height)
        self.events = [Event(e, self.map_id) for _, e
                       in sorted(by_id(list_field(data, "events")).items())]


def passability(data, name):
    """A chipset's passability: one byte per tile.

    A chipset that does not carry it has it anyway —15 is passable from all
    four sides and below the hero, and the 31 of the first upper tile puts it
    above—, and that already comes resolved from `rom/data/`: there is
    nothing to fill in here.
    """
    return bytes(field(data, name))


class Chipset:
    def __init__(self, data):
        self.name = field(data, "name")
        self.filename = field(data, "chipset_name")
        self.passable_lower = passability(data, "passable_data_lower")
        self.passable_upper = passability(data, "passable_data_upper")
        self.terrain = field(data, "terrain_data")
        self.animation_type = field(data, "animation_type")
        self.animation_speed = field(data, "animation_speed")


# The five equipment slots, in the order the port numbers them.
EQUIPMENT_SLOTS = ("weapon_id", "shield_id", "armor_id", "helmet_id",
                   "accessory_id")
# And the six curves of `Parameters`, in the format's order.
CURVES = ("maxhp", "maxsp", "attack", "defense", "spirit", "agility")


class Actor:
    """A character from the database: this is where the graphic it is drawn
    with comes from."""

    def __init__(self, data):
        self.name = field(data, "name")
        self.charset = field(data, "character_name")
        self.charset_index = field(data, "character_index")
        self.face_name = field(data, "face_name")
        self.face_index = field(data, "face_index")
        # The parameters per level, from 1: `maxhp`, `attack`, `defense`,
        # `spirit`, `agility`, each one a list.
        parameters = sub(data, "parameters")
        self.params = {c: field(parameters, c) or []
                       for c in CURVES}
        self.hp_max = self.params.get("maxhp", [])
        self.sp_max = self.params.get("maxsp", [])
        # **The level it starts at**, which in ABL is not 1: Kersh starts at
        # 20 and Core and Manta at 15. Until 2026-09-13 this port had
        # everyone at 1 —a constant `title.NIVEL`— and from that came the
        # HP, the parameters and the conclusion that nobody knew any skill.
        self.initial_level = field(data, "initial_level") or 1
        # How high it goes and with which experience curve: the three
        # numbers of `Game_Actor::CalculateExp`. See `port.experience`.
        self.final_level = field(data, "final_level")
        self.exp_base = field(data, "exp_base")
        self.exp_inflation = field(data, "exp_inflation")
        self.exp_correction = field(data, "exp_correction")
        # Which skill it learns at each level, in the LDB's order:
        # `Game_Actor::LearnLevelSkills` walks them that way.
        # `skill_id` is **1** when the file does not carry it, which is what
        # the format says: it is the only game datum that changed when moving
        # to Ditto. Alex —actor 1, from the RTP, which this game does not
        # use— learns skill 1 at level 1, and before that arrived as skill 0
        # and was dropped. It is one more pair in `events.SKILL_SLOT`;
        # other than that the `mapdata.inc` is identical.
        self.skills = [(field(l, "level"),
                        field(l, "skill_id"))
                       for _, l in sorted(by_id(list_field(data, "skills")).items())]
        # What its skill command is called in the battle menu:
        # `Game_Actor::GetSkillName` returns `skill_name` if `rename_skill`
        # is set and otherwise the LDB's `command_skill`. The four actors of
        # the intro have it set: "AgentTrain", "Telepathy", "Slicing" and
        # "Special".
        self.rename_skill = field(data, "rename_skill")
        self.skill_name = field(data, "skill_name")
        # The equipment it starts with: weapon, shield, armor, helmet and
        # accessory, by item number, 0 if none.
        equipment = sub(data, "initial_equipment")
        self.initial_equipment = [field(equipment, r)
                                  for r in EQUIPMENT_SLOTS]


# The skill types, in the order of `rpg::Skill::Type`. The seven the intro's
# party knows are `normal` or `switch`.
SKILL_TYPE_NORMAL, SKILL_TYPE_TELEPORT, SKILL_TYPE_ESCAPE, \
    SKILL_TYPE_SWITCH, SKILL_TYPE_SUBSKILL = range(5)
# And the scopes, `rpg::Skill::Scope`. `SkillTargetsEnemies` in algo.h is
# "enemy or enemies"; everything else targets one's own side.
SKILL_SCOPE_ENEMY, SKILL_SCOPE_ENEMIES, SKILL_SCOPE_SELF, \
    SKILL_SCOPE_ALLY, SKILL_SCOPE_PARTY = range(5)

SKILL_FIELDS = ("name", "description", "using_message1", "using_message2",
                "type", "sp_cost", "scope", "switch_id", "animation_id",
                "physical_rate", "magical_rate", "variance", "power", "hit",
                "affect_hp", "affect_sp", "affect_attack", "affect_defense",
                "affect_spirit", "affect_agility", "ignore_defense")


class Skill:
    """A skill: what the screen shows and what the calculation needs.

    The defaults are not all zero —`magical_rate` is 3, `variance` 4, `hit`
    100, `switch_id` and `animation_id` 1— and they are no longer written
    here: they come from the schema, which is where they have to come from.
    """

    def __init__(self, data):
        for name in SKILL_FIELDS:
            setattr(self, name, field(data, name))
        # Its number, which an enemy's action list needs to name it: see
        # `batalla.acciones_de_enemigo`.
        self.id = field(data, "id")

    @property
    def targets_enemies(self):
        """`Algo::SkillTargetsEnemies`."""
        return self.scope in (SKILL_SCOPE_ENEMY, SKILL_SCOPE_ENEMIES)


# The item types, in the order of `rpg::Item::Type`.
ITEM_TYPE_NORMAL, ITEM_TYPE_WEAPON, ITEM_TYPE_SHIELD, ITEM_TYPE_ARMOR, \
    ITEM_TYPE_HELMET, ITEM_TYPE_ACCESSORY, ITEM_TYPE_MEDICINE, \
    ITEM_TYPE_BOOK, ITEM_TYPE_MATERIAL, ITEM_TYPE_SPECIAL, \
    ITEM_TYPE_SWITCH = range(11)

ITEM_FIELDS = ("name", "description", "type", "uses", "switch_id",
               "occasion_field2", "price", "two_handed", "recover_hp_rate",
               "recover_hp", "occasion_field1", "ko_only",
               "recover_sp_rate", "recover_sp", "sp_cost")
# What it adds when equipped: attack, defense, spirit, agility.
ITEM_POINTS = ("atk_points1", "def_points1", "spi_points1", "agi_points1")


class Item:
    """An item: what the menu shows of it and the little it does today.

    `recover_hp_rate` is a percentage of the maximum and `recover_hp` is
    absolute, and the same for the SP ones; `occasion_field1` is "only
    outside battle" and `ko_only` "only on a dead one". `state_set` are the
    states it removes, one per LDB state from 1, which is the dead one: it is
    what decides whether it revives a fallen one. See
    `batalla.item_usable_en_batalla` and `medicina_usar` in
    tools/runtime/medicina.s.
    """

    def __init__(self, data):
        for name in ITEM_FIELDS:
            setattr(self, name, field(data, name))
        self.points = [field(data, p) for p in ITEM_POINTS]
        self.actor_set = field(data, "actor_set") or []
        self.state_set = field(data, "state_set") or []

    def equippable_by(self, actor):
        """`actor_set`, with the ones the list itself does not reach: that is
        what RM2k does with an item made before actors were added."""
        return self.actor_set[actor - 1] if actor - 1 < len(self.actor_set) \
            else True


ENEMY_FIELDS = ("name", "battler_name", "battler_hue", "max_hp", "max_sp", "attack",
                "defense", "spirit", "agility", "exp", "gold", "critical_hit",
                "miss", "drop_id", "drop_prob")


class Enemy:
    """An enemy: its parameters and what it hits with.

    `miss` and `critical_hit` come from easyrpg-player's
    `Game_Enemy::GetHitChance` and `Game_Enemy::GetCriticalHitChance`: the
    one that misses hits 70 out of 100 and the one that does not, 90, and the
    critical is once every `critical_hit_chance`.

    The six parameters are **10** when the file does not carry them, which is
    what the format says. Here they were written as 1 and 0, and it was not a
    theoretical difference: taro found on 2026-09-14, playing, that the
    DirtShadow died in one hit. They are 24 enemies out of 175, almost all
    editor separators, but the DirtShadow is a real one. It is the error that
    gave rise to Ditto.
    """

    def __init__(self, data):
        for name in ENEMY_FIELDS:
            setattr(self, name, field(data, name))
        self.critical_hit_chance = field(data, "critical_hit_chance") or 30
        # What it can do on its turn, in the LDB's order: see
        # `batalla.acciones_de_enemigo`.
        self.actions = [EnemyAction(a) for _, a in
                        sorted(by_id(list_field(data, "actions")).items())]

    @property
    def hit(self):
        """`Game_Enemy::GetHitChance`."""
        return 70 if self.miss else 90


ENEMY_ACTION_FIELDS = ("kind", "basic", "skill_id", "rating",
                      "condition_type", "condition_param1",
                      "condition_param2", "switch_on", "switch_off")


class EnemyAction:
    """An action from an enemy's list: `lcf::rpg::EnemyAction`. `kind` 0 is
    basic —`basic` 0 is attack—, 1 a skill and 2 transform; the `rating` is
    the weight `EnemyAi` gives it when choosing."""

    def __init__(self, data):
        for name in ENEMY_ACTION_FIELDS:
            setattr(self, name, field(data, name))


class Troop:
    """A troop: which enemies make it up and where each one goes.

    The positions (x, y) are of the **center** of each battler on RM2k's
    320x240 screen. The troop's event pages go in `pages`, in the LDB's
    order, which is the order in which `ScheduleNextPage` tries them.
    """

    def __init__(self, data):
        members = sorted(by_id(list_field(data, "members")).items())
        self.name = field(data, "name")
        self.members = [field(m, "enemy_id")
                        for _, m in members]
        self.positions = [(field(m, "x"),
                           field(m, "y"))
                          for _, m in members]
        # The ones that start hidden, in the same order: `invisible`, which
        # `Game_Enemy` copies with `SetHidden` and `ShowHiddenMonster`
        # removes.
        self.hidden = [bool(field(m, "invisible")) for _, m in members]
        self.pages = [TroopPage(p) for _, p in
                      sorted(by_id(list_field(data, "pages")).items())]


# The triggers of a troop page, with liblcf's names
# (`TroopPageCondition::Flags`). The 2003 ones —`turn_enemy`, `turn_actor`,
# `command_actor`— are not in the dump of a 2000 game.
TROOP_TRIGGERS = ("switch_a", "switch_b", "variable", "turn", "fatigue",
                  "enemy_hp", "actor_hp")


class TroopPage:
    """A troop event page: when it runs and what it does.

    `active` are the triggers that are on; the numbers that answer each one
    stay in `condition`, which is the dump's object as is: they are many
    fields and each is read only by whoever needs it.
    """

    def __init__(self, data):
        condition = sub(data, "condition")
        flags = sub(condition, "flags")
        self.active = [n for n in TROOP_TRIGGERS if flags.get(n)]
        self.condition = condition
        self.commands = commands(data)


# The LDB's fifteen sections, each in its own file. The names are the fields
# of `Database`, which is what the files in `db/` are called.
SECTIONS = ("actors", "skills", "items", "enemies", "troops", "terrains",
            "attributes", "states", "animations", "chipsets", "terms",
            "system", "switches", "variables", "commonevents")
# And the ones that are a list of numbered elements; `system` and `terms` are
# a single object.
LIST_SECTIONS = tuple(s for s in SECTIONS if s not in ("system", "terms"))

# The sound effects `Game_System::GetSystemSE` hands out, in the order
# `events.BATTLE_AUDIO_SE` walks.
SYSTEM_SE = ("battle_se", "escape_se", "enemy_attack_se", "enemy_damaged_se",
             "actor_damaged_se", "dodge_se", "enemy_death_se", "item_se")

# The terms the port uses by name. The rest are still in `db.terms`, by
# chunk, which is how the shop asks for them.
TERM_MENU = ("command_item", "command_skill", "menu_equipment", "menu_save",
             "menu_quit")
TERM_PARAMS = ("attack", "defense", "spirit", "agility")
TERM_EQUIPMENT = ("weapon", "shield", "armor", "helmet", "accessory")
TERM_SINGLE = {
    "term_new_game": "new_game", "term_load_game": "load_game",
    "term_load_message": "load_game_message",
    "term_save_message": "save_game_message", "term_file": "file",
    "term_level": "level", "term_lvl_short": "lvl_short", "term_gold": "gold",
    "term_normal_status": "normal_status", "term_hp_short": "hp_short",
    "term_exp_short": "exp_short",
}


def system_songs(path):
    """The names of the songs in the LDB's `System` at `path`: the title's,
    the battle's, Game Over's, the vehicles'...

    Without loading the whole database, which is what `snes_music` needs:
    numbering the MSU-1 tracks has no reason to read the actors.
    """
    system = read_json(dump_dir(path), "db", "system.json")
    return sorted({text(value["name"]) for name, value in system.items()
                   if name.endswith("_music") and isinstance(value, dict)})


def sound(data):
    """A `Music` or a `Sound` as the tuple the port expects."""
    return (field(data, "name"), field(data, "volume"),
            field(data, "tempo"), field(data, "balance"))


class Database:
    """RPG_RT.ldb: the chipsets, the characters and the starting party.

    Of the `path` only the directory is used, and only to know whether it
    carries a dump of its own: the data come from the dump's `db/`.
    """

    def __init__(self, path):
        root = os.path.join(dump_dir(path), "db")
        self.sections = {s: read_json(root, "%s.json" % s) for s in SECTIONS}

        raw = {s: by_id(self.sections[s]) for s in LIST_SECTIONS}
        # The ChipSets `rom/parches/manual/` adds. They **are added**: an id
        # already in the database is an error, because a fork that overwrites
        # an entry goes stale without warning the day `just datos` changes
        # it. See `fork.py`.
        if root == os.path.join(project.data(), "db"):
            for number, data in fork.chipsets().items():
                if number in raw["chipsets"]:
                    raise ValueError(
                        "ChipSet %d is already in rom/data/: the fork adds, "
                        "it does not replace" % number)
                raw["chipsets"][number] = data["chipset"]
        self.chipsets = {i: Chipset(f) for i, f in raw["chipsets"].items()}
        self.actors = {i: Actor(f) for i, f in raw["actors"].items()}
        # The items, and the highest number: `ITEMS_N` in events.py is this
        # plus one, and test_items.py checks it.
        self.items = {i: Item(f) for i, f in raw["items"].items()}
        # The skills, which `lcf.Actor.skills` names by number.
        self.skills = {i: Skill(f) for i, f in raw["skills"].items()}
        self.items_max = max(self.items, default=0)
        # The enemies and the troops: what a battle needs.
        self.enemies = {i: Enemy(f) for i, f in raw["enemies"].items()}
        self.troops = {i: Troop(f) for i, f in raw["troops"].items()}
        # Each terrain's battle background: the one for a battle on a map
        # that does not name its own. See `TreeMap.map_background`.
        self.terrain_backdrops = {i: field(f, "background_name") or ""
                                  for i, f in raw["terrains"].items()}
        # The common events, which used to be read from the raw chunk: here
        # they are already their commands, which is the only thing asked of
        # them.
        self.common_events = {
            i: commands(f, refit=True)
            for i, f in raw["commonevents"].items()}
        # And when each one runs on its own: `(trigger, switch_flag,
        # switch_id)`, with the `trigger` of `rpg::CommonEvent` —3 automatic,
        # 4 parallel, 5 only through `CallEvent`—. See
        # `events.PARTY_COMMON_EVENTS`.
        self.common_event_triggers = {
            i: (field(f, "trigger"), field(f, "switch_flag"),
                field(f, "switch_id"))
            for i, f in raw["commonevents"].items()}

        # The party the game starts with. In RM2k the hero's graphic is that
        # of the first one in the list, so this datum is what decides which
        # sprite it is drawn with.
        system = self.sections["system"]
        self.party = field(system, "party") or []
        # The game's System: the PNG with the window frame, the text colors
        # and the shadow. This game uses `ablskin`.
        self.system_name = field(system, "system_name")
        # Which font it draws text with: 0 Gothic, 1 Mincho. easyrpg picks
        # ttyp0 or rmg2000 with this, and the letters come out different.
        # This game asks for Mincho.
        self.font_id = field(system, "font_id")
        # The title screen image and its song. In ABL they are 'ABL20Title'
        # and 'Fantasia_Of_The_Wind'; the other PNG in Title/ —'LineTitle'—
        # is from an earlier version and the game does not use it.
        self.title_name = field(system, "title_name")
        self.title_music = field(sub(system, "title_music"), "name")
        # And the Game Over one and its song. ABL says 'GameOver' and
        # 'GameOver3', and **neither of them is in the game**: they come from
        # the RTP, as in RM2k. The `ablgameover.png` the game ships in
        # GameOver/ is named by nobody, and the original under Wine shows the
        # RTP's.
        self.gameover_name = field(system, "gameover_name")
        self.gameover_music = field(sub(system, "gameover_music"), "name")
        # The battle audio. It comes from here and not from a literal of ours
        # for the same reason as the terms: it is game data. In ABL the
        # battle song and the victory song are **the same one**
        # —T_VGFighterMAX_Masako—, and `battle_se` is "(OFF)", which is a
        # name that resolves to no file and comes out silent without having
        # to be handled separately.
        self.battle_music = field(sub(system, "battle_music"), "name")
        self.battle_end_music = field(sub(system, "battle_end_music"), "name")
        self.system_se = {n: sound(sub(system, n)) for n in SYSTEM_SE}

        # The title screen terms. In ABL they are not the stock ones: they
        # say 'Begin the Story' and 'Resume the Story', which is what the
        # game chose, and that is why they come from here and not from a
        # literal of ours.
        terms = self.sections["terms"]
        for attribute, name in TERM_SINGLE.items():
            setattr(self, attribute, field(terms, name))
        self.term_menu = [field(terms, t) for t in TERM_MENU]
        self.term_params = [field(terms, t) for t in TERM_PARAMS]
        self.term_equipment = [field(terms, t) for t in TERM_EQUIPMENT]
        # And all the terms, by name, which is what the shop asks for: there
        # they are not named one by one but in blocks —the thirteen of each
        # message set—. Until 2026-09-20 the key was the chunk number, and
        # that required knowing which chunk each term falls in, which is
        # format data: the only thing that knew it was the schema Python no
        # longer has.
        self.terms = {
            name: field(terms, name).encode("cp1252", "replace")
            for name in terms}

    def leader(self, party=None):
        """The CharSet of the first one in the party: (name, index).

        An empty party has nothing to draw the hero with. It happens in RM2k
        —everyone can be removed— and there the engine draws nothing; here it
        stops, which is more honest than making up a sprite.
        """
        members = self.party if party is None else party
        if not members:
            raise ValueError("the party is empty: there is nothing to draw the hero with")
        actor = self.actors[members[0]]
        return actor.charset, actor.charset_index

    def decode(self, unknown=None):
        """The whole database as dicts, for whoever wants it field by field.

        It is `rom/data/` as is, with two touch-ups that are not part of the
        format: arrays of structs become indexed by id, which is how they are
        looked up, and texts go through `text`. Everything else —the
        defaults applied, the enums as numbers— already comes that way.
        """
        return {section: normalize(self.sections[section])
                for section in SECTIONS}


def normalize(data):
    """A piece of `rom/data/` indexed by id and with the texts guessed.

    An array of structs becomes `{id: element}` again, which is how it is
    looked up; those without an id —an event's commands, which in the format
    go one after the other and unnumbered— stay as a list. The resolved view
    writes every field, so the `id` is always there and there is no need to
    know beforehand which struct each thing is: it shows.
    """
    if isinstance(data, list):
        if not data or not isinstance(data[0], dict):
            return data        # a list of numbers: the tiles, a curve
        if "id" in data[0]:
            return {e["id"]: normalize(e) for e in data}
        return [normalize(e) for e in data]
    if not isinstance(data, dict):
        return text(data) if isinstance(data, str) else data
    return {name: normalize(value) for name, value in data.items()
            if name != "id"}  # the id is the key, not a field


class TreeMap:
    """RPG_RT.lmt: the map tree and the player's starting position."""

    def __init__(self, path):
        data = read_json(dump_dir(path), "maps.json")
        infos = by_id(list_field(data, "maps"))
        # The maps the game does not have bring their node: see
        # `fork.new_maps`. Only on this game's dump, same as `Map`'s forks.
        if dump_dir(path) == project.data():
            for map_id, (_json, _tiles, node) in fork.new_maps().items():
                infos[map_id] = node

        self.map_names = {i: field(f, "name")
                          for i, f in infos.items()}
        self.map_parents = {i: field(f, "parent_map")
                            for i, f in infos.items()}
        # Type 0 = root of the tree, 1 = real map, 2 = **area**. An area is a
        # node without a `.lmu` that hangs off a map and covers a rectangle
        # of it. Here they are used for random encounters, which is the only
        # thing ABL puts in them.
        self.map_types = {i: field(f, "type")
                          for i, f in infos.items()}

        # The random encounters, which live in the tree and not in the
        # `.lmu`: the list of troops, every how many steps and —for areas—
        # the rectangle they cover.
        self.encounters = {}
        self.encounter_steps = {}
        self.area_rect = {}
        for i, f in infos.items():
            self.encounters[i] = [
                field(e, "troop_id")
                for _, e in sorted(by_id(list_field(f, "encounters")).items())]
            # RM2k's default is 25 steps; 0 is "no encounters".
            self.encounter_steps[i] = field(f, "encounter_steps")
            rect = sub(f, "area_rect")
            self.area_rect[i] = tuple(field(rect, c) for c in "ltrb")

        # Each node's battle background: `background_type` 0 is "the
        # parent's", 1 "the terrain's" and 2 "this one", with the name beside
        # it.
        self.background = {i: (field(f, "background_type"),
                               field(f, "background_name"))
                           for i, f in infos.items()}

        self.music = {}
        for i, f in infos.items():
            song = sub(f, "music")
            self.music[i] = (field(f, "music_type"), {
                "name": field(song, "name"),
                "volume": field(song, "volume"),
                "tempo": field(song, "tempo"),
            })

        self.tree_order = field(data, "tree_order") or []
        start = sub(data, "start")
        self.start_map_id = field(start, "party_map_id")
        self.start_x = field(start, "party_x")
        self.start_y = field(start, "party_y")

    def map_background(self, map_id):
        """The battle background of an encounter on this map: its name, or
        None if it is that of the terrain the hero is standing on.

        It is easyrpg-player's `Game_Map::SetupBattle`: it climbs the tree
        while the node says "the parent's", and only 2 carries a name.
        Everything else —1, or reaching the root without any 2— leaves the
        name empty, and `Spriteset_Battle` then uses the background of the
        cell's terrain (`Database.terrain_backdrops`). What is looked at is
        **the map and not the area**: ABL's areas are all "the parent's", and
        easyrpg starts from `GetMapInfo()`.
        """
        seen = set()
        while map_id and map_id not in seen:
            seen.add(map_id)
            kind, name = self.background.get(map_id, (0, ""))
            if kind != 0:
                return (name or None) if kind == 2 else None
            map_id = self.map_parents.get(map_id, 0)
        return None

    def map_music(self, map_id):
        """A map's song, following the inheritance up to the parent.

        music_type 0 means "the parent's"; 2, the one the map carries. 1 is
        "an event sets it", which without interpreting scripts is the same
        as nothing.
        """
        seen = set()
        while map_id and map_id not in seen:
            seen.add(map_id)
            kind, music = self.music.get(map_id, (0, None))
            if kind == 2 and music["name"]:
                return music
            if kind == 1:
                return None
            map_id = self.map_parents.get(map_id, 0)
        return None
