"""The screens, which are `rm2k-snes-screens`, as the tests ask for them:
a screen as the console has to show it (`render`), what equipping leaves
(`equip`), the geometry the screens are drawn with (`layout`) and the
message boxes reflowed for a window (`refit`).

It was the converter's `port/screen_stage.py`, which also built the
request the conversion sends, until the converter moved to Rust on
2026-10-02; what is left is what the game's tests ask.
"""

import io
import json
import os
import types

import stage

BINARY = "rm2k-snes-screens"
PROJECT = "screens"


def _run(command, request, *flags, raw=False):
    written = stage.run(BINARY, PROJECT, command, request, *flags, raw=raw)
    return written


def _answer(command, name, request, *flags):
    return json.loads(_run(command, request, *flags)[name])


_LAYOUT = []


def layout():
    """The geometry the screens are drawn with, by the names the emission
    writes it with: `layout().SLOT_Y`. The stage's `layout.rs` is the only
    place the numbers live."""
    if not _LAYOUT:
        _LAYOUT.append(types.SimpleNamespace(
            **_answer("layout", "layout.json", {})))
    return _LAYOUT[0]


def dump_of(game_dir):
    """The dump the game is read from: `lcf`'s rule."""
    import lcf
    return lcf.dump_dir(os.path.join(game_dir, "RPG_RT.ldb"))


def _game(game_dir):
    return ["--data", dump_of(game_dir),
            "--game-dir", os.path.abspath(game_dir)]


def refit(boxes, columns, lines):
    """Each of `boxes`, a list of lines, reflowed for a window of `columns`
    by `lines`: `[{"to": boxes, "speaker": bool}]`. For whoever checks the
    reflow over a whole game."""
    return _answer("refit", "refit.json", {
        "boxes": [list(b) for b in boxes],
        "columns": columns, "lines": lines})


_SLOTS = []


def _slots():
    """How many save slots the cartridge has: what `rm2k-snes-mapdata
    vram` publishes, with the rest of the cartridge's memory."""
    if not _SLOTS:
        written = stage.run("rm2k-snes-mapdata", "mapdata", "vram",
                            {"maps": []})
        _SLOTS.append(json.loads(written["vram.json"])["slots"])
    return _SLOTS[0]


def render(screen, **state):
    """Screen `screen` —menu, items, target, slots, equipment, shop or
    end_game— as the console has to show it, in RGB, with the state it
    shows: see `render.rs` in the stage for each one's. Numbers keyed by
    actor or item go as dictionaries."""
    from PIL import Image
    import resources

    def plain(value):
        if isinstance(value, dict):
            return {str(k): plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [plain(v) for v in value]
        return value

    request = dict(plain(state), screen=screen)
    request.setdefault("slots", _slots())
    written = _run("render", request, *_game(resources.GAME_DIR), raw=True)
    with Image.open(io.BytesIO(written["screen.png"])) as image:
        return image.convert("RGB")


def equip(equipment, inventory, slot, item):
    """What equipping `item` in `slot` leaves —`Game_Actor::ChangeEquipment`,
    as the equipment screen does it—: `(equipment, inventory)`, the
    inventory from item number to how many. For the tests that predict the
    console's RAM with the same rule that draws the screen."""
    import resources
    answer = _answer("equip", "equip.json", {
        "equipment": list(equipment),
        "inventory": {str(k): v for k, v in inventory.items()},
        "slot": slot, "item": item,
    }, *_game(resources.GAME_DIR))
    return (answer["equipment"],
            {int(k): v for k, v in answer["inventory"].items()})
