"""The screens, which are `rm2k-snes-screens`: what goes into its requests
and the shape its answer takes for the converter.

**The screens are drawn by the stage** —the message window and its font,
the title's menu, the save slots and the pause menu, the text screens with
their windows, End Game—, which reads the game from the dump itself and
the System, the faces and the title from the game's folder; see its
README, `tools/rm2k-snes/screens/`. What stays here is what the cartridge
decided and the stage does not know —which actors, which items, how many
slots, where each layout puts BG1— and the answer in the shape `mapdata`
emits.

It is also where the rest of the converter asks for the geometry the
screens were drawn with (`layout`), for the message boxes reflowed for the
console's window (`boxes`, `refit_commands`), and where the tests ask for a
screen as the console has to show it (`render`).
"""

import io
import json
import os
import types

from port import constants, stage, vram
from port.snes_format import BYTES_PER_TILE

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


def item_text(text, width):
    """What the text screens' font can write: the characters it has, with a
    '?' instead of the others, and cut to the width. It is the stage's rule
    —`item_text` in its `texts.rs`—, over the same range of characters, and
    every text the emission writes for those screens goes through it."""
    first, count = layout().ITEM_FIRST_CHAR, layout().ITEM_CHARS
    return "".join(c if first <= ord(c) < first + count else "?"
                   for c in text)[:width]


def dump_of(game_dir):
    """The dump the game is read from: `lcf`'s rule."""
    from rpgmaker import lcf
    return lcf.dump_dir(os.path.join(game_dir, "RPG_RT.ldb"))


def _game(game_dir):
    return ["--data", dump_of(game_dir),
            "--game-dir", os.path.abspath(game_dir)]


_BOXES = {}


def boxes(dump):
    """Every text box of the game the port rebuilds for the console's
    window, with the boxes that go in its place: `[{"from": lines, "to":
    boxes}]`, only those that change. The maps come from the dump and the
    project's files over it, like everything the compiler reads."""
    from port import compiler
    key = (os.path.abspath(dump), constants.COLUMNS, constants.LINES)
    if key not in _BOXES:
        _BOXES[key] = _answer("boxes", "boxes.json", {
            "map_files": compiler.map_files(dump),
            "columns": constants.COLUMNS, "lines": constants.LINES,
        }, "--data", dump)
    return _BOXES[key]


def refit(boxes):
    """Each of `boxes`, a list of lines, reflowed for the console's window:
    `[{"to": boxes, "speaker": bool}]`. For whoever checks the reflow over a
    whole game."""
    return _answer("refit", "refit.json", {
        "boxes": [list(b) for b in boxes],
        "columns": constants.COLUMNS, "lines": constants.LINES})


_TABLES = {}


def refit_commands(commands):
    """A list of commands from the dump —dictionaries, as they are in the
    JSON— with each text box rebuilt for the console's window: what
    `lcf.REFIT_TEXTS` is set to. The boxes are those of `boxes` for the
    game being converted.

    A `ShowMessage` with its `ShowMessage_2`s is replaced by one or more
    boxes in the same format, with the same `indent`. What is not text, and
    the boxes that already fit, come out as **the same objects**: whoever
    compares with `is` knows what changed.
    """
    from port import events
    from rpgmaker import resources
    dump = os.path.abspath(dump_of(resources.GAME_DIR))
    if dump not in _TABLES:
        _TABLES[dump] = {tuple(b["from"]): b["to"] for b in boxes(dump)}
    table = _TABLES[dump]
    out = []
    i = 0
    while i < len(commands):
        command = commands[i]
        if command["code"] != events.SHOW_MESSAGE:
            out.append(command)
            i += 1
            continue
        j = i + 1
        while j < len(commands) and commands[j]["code"] == events.SHOW_MESSAGE_2:
            j += 1
        originals = commands[i:j]
        frames = table.get(tuple(c["string"] for c in originals))
        if frames is None:
            out.extend(originals)
        else:
            for frame in frames:
                for k, text in enumerate(frame):
                    out.append({
                        "code": (events.SHOW_MESSAGE if k == 0
                                 else events.SHOW_MESSAGE_2),
                        "indent": command["indent"],
                        "parameters": [],
                        "string": text,
                    })
        i = j
    return out


def _tile(cell):
    return tuple(tuple(row) for row in cell)


def _color(c):
    return tuple(c)


def convert(game_dir, members, items, bank_items, title):
    """What the cartridge carries of its screens, for `members` —the actors
    that can join the party— and `items` —the ones the cartridge knows—,
    with the title's menu if `title`. The letters of the medicines of
    `bank_items` go in the menu's bank, which the actor choice writes their
    names with.

    Returns `(window, slots, title_menu, texts, says, answer)`: in the
    shape the converter prints them, what the stage has to say, in order,
    and its answer as it came, which is what `rm2k-snes-mapdata emit`
    takes.
    """
    request = {
        "slots": vram.SLOTS,
        "actors": list(members),
        "items": list(items),
        "bank_items": list(bank_items),
        "title": bool(title),
        # The message window goes in the lowest palette, and the background
        # starts after it: see `cgram.rs` in `rm2k-snes-mapdata`.
        "cgram_reserved": _cgram_reserved(),
        "vram": {
            "slot_vram": vram.SLOT_VRAM,
            "slot_map": vram.SLOT_MAP,
            # Each layout's BG1 bank, which is what `load_map` restores on
            # coming back from a screen: the screens have to fall inside.
            "bg1_banks": [
                [name, layout["tiles"][0],
                 layout["tiles"][0]
                 + layout["tiles"][1] * (BYTES_PER_TILE // 2)]
                for name, layout in vram.LAYOUTS],
        },
    }
    answer = _answer("convert", "screens.json", request, *_game(game_dir))
    w = answer["window"]
    window = {
        "tiles": bytes.fromhex(w["tiles"]),
        "cram": w["cgram"],
        "celdas": w["cells"],
        "base": w["base"],
        "fondo": bytes.fromhex(w["background"]),
        "color": w["color"],
        "sombra": w["shadow"],
        "fuente": bytes.fromhex(w["font"]),
        "pre": [bytes.fromhex(t) for t in w["prerender"]],
    }
    s = answer["slots"]
    menu = s["menu"]
    items_font = answer["items_font"]
    items_border = answer["items_border"]
    shop = answer["shop_border"]
    target = answer["target"]
    end = answer["end_game"]
    slots = {
        "tiles": [_tile(c) for c in s["tiles"]],
        "paletas": [[_color(c) for c in p] for p in s["palettes"]],
        "cabeceras": s["headers"],
        "filas": s["rows"],
        "caras": {int(a): c for a, c in s["faces"].items()},
        "menu": {
            "opciones": menu["options"],
            "cursor": menu["cursor"],
            "glifos": menu["glyphs"],
            "moneda": menu["currency"],
            "fila": menu["row"],
            "exp_termino": menu["exp_term"],
        },
        "items_tiles": [_tile(c) for c in items_font["tiles"]],
        "items_paletas": [[_color(c) for c in p]
                          for p in items_font["palettes"]],
        "items_glifos": items_font["glyphs"],
        "items_marco": ([_tile(c) for c in items_border["tiles"]],
                        [_color(c) for c in items_border["colors"]],
                        [(m, bars) for m, bars in items_border["maps"]]),
        "items_marco_primero": answer["items_border_first"],
        "tienda_marco": ([_tile(c) for c in shop["tiles"]],
                         [_color(c) for c in shop["colors"]],
                         (shop["rows"], shop["top"], shop["layers"],
                          shop["patches"], shop["bars"])),
        "objetivo": ([_tile(c) for c in target["tiles"]],
                     [_color(c) for c in target["colors"]],
                     (target["map"], target["bars"], target["row0"],
                      target["rows"], target["col0"], target["cols"]),
                     (target["menu_bar"], target["menu_bar_at"])),
        "fin": ([_tile(c) for c in end["tiles"]], end["rows"], end["row0"],
                [[_color(c) for c in p] for p in end["palettes"]]),
    }
    title_menu = None
    if answer["title"] is not None:
        t = answer["title"]
        title_menu = {"texts": t["texts"],
                      "tiles": [_tile(c) for c in t["tiles"]],
                      "palette": [_color(c) for c in t["palette"]],
                      "tilemaps": t["tilemaps"]}
    return window, slots, title_menu, answer["texts"], answer["says"], answer


def _cgram_reserved():
    return vram.published()["cgram_reserved"]


def render(screen, **state):
    """Screen `screen` —menu, items, target, slots, equipment, shop or
    end_game— as the console has to show it, in RGB, with the state it
    shows: see `render.rs` in the stage for each one's. Numbers keyed by
    actor or item go as dictionaries."""
    from PIL import Image
    from rpgmaker import resources

    def plain(value):
        if isinstance(value, dict):
            return {str(k): plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [plain(v) for v in value]
        return value

    request = dict(plain(state), screen=screen)
    request.setdefault("slots", vram.SLOTS)
    written = _run("render", request, *_game(resources.GAME_DIR), raw=True)
    with Image.open(io.BytesIO(written["screen.png"])) as image:
        return image.convert("RGB")
