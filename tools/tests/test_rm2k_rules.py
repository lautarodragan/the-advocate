"""The RPG Maker 2000 rules, in their two copies.

`rpgmaker/rm2k.py` —and the few rules `rpgmaker/lcf.py`,
`render/render_map.py` and `port/experience.py` carry— are what the converter
uses, and it is still in Python; `rm2k/rules/`, `rm2k-rules`, is the same
rules in Rust, for what moves to Rust. The two live side by side until the
converter moves, and this is what keeps them the same.

The link is a file, `rm2k/rules/tests/python.json`: some inputs and what
the Python answered for them. The Rust test reads it and requires its own
answers to be those; this one requires the Python to still answer them. So
a rule changed on one side only goes red on that side, and neither side
runs the other's language.

**The answers are not to be regenerated to make this pass.** A red here
means the Python rule changed: either the Rust copy changes with it, and
the file is written again by `answers()` below, in the same commit, or the
change was a mistake.
"""

import hashlib
import json
import os
from types import SimpleNamespace

from common import project
from port import experience
from render import render_map
from rpgmaker import lcf, rm2k

FIXTURE = os.path.join(project.tools(), "rm2k", "rules", "tests", "python.json")

# The fields of a page condition the Python reader wants; the fixture only
# gives the flags, which is all a condition's being there depends on.
CONDITION_IDS = {"switch_a_id": 1, "switch_b_id": 1, "variable_id": 1,
                 "item_id": 1, "actor_id": 1, "timer_sec": 0,
                 "variable_value": 0}


def _chipset(data):
    return SimpleNamespace(passable_lower=bytes(data["passable_data_lower"]),
                           passable_upper=bytes(data["passable_data_upper"]),
                           terrain=data["terrain_data"])


def _actor(data):
    return SimpleNamespace(**{k: data[k] for k in (
        "initial_level", "final_level", "exp_base", "exp_inflation",
        "exp_correction")})


def _tree(nodes):
    """What `lcf.TreeMap` keeps of the tree, for its two inheritance rules."""
    by_id = {n["id"]: n for n in nodes}
    return SimpleNamespace(
        map_parents={i: n["parent_map"] for i, n in by_id.items()},
        background={i: (n["background_type"], n["background_name"])
                    for i, n in by_id.items()},
        music={i: (n["music_type"], {"name": n["music"]["name"]})
               for i, n in by_id.items()})


def answers(inputs):
    """What the Python rules answer for the fixture's inputs."""
    out = {}
    out["chip_index"] = [rm2k.chip_index(i) for i in inputs["tile_ids"]]

    chipsets = [_chipset(c) for c in inputs["chipsets"]]
    tables = [render_map.build_passability(c) for c in chipsets]
    out["passability_sha256"] = [hashlib.sha256(bytes(t)).hexdigest()
                                 for t in tables]
    out["terrain"] = [[rm2k.terrain_of(c, i) for i in inputs["tile_ids"]
                       if i < rm2k.UPPER_BASE]
                      for c in chipsets]
    out["cells"] = [[rm2k.cell_passability(t, lower, upper)
                     for lower, upper in inputs["cells"]]
                    for t in tables]

    out["terrain_box"] = [list(rm2k.terrain_box(n)[:2]) for n in range(12)]
    out["common_box"] = [list(rm2k.common_box(i)[:2]) for i in range(288)]
    out["animated_step"] = [rm2k.animated_step(t) for t in inputs["frames"]]

    graphics, tile_pass = [], []
    game_map = SimpleNamespace(passability_table=tables[0])
    for data in inputs["pages"]:
        page = SimpleNamespace(**data)
        graphic = rm2k.page_graphic(page, "chipset")
        if graphic is None:
            graphics.append(None)
            tile_pass.append(None)
            continue
        name, index, pose = graphic
        if name.startswith(rm2k.TILE_PREFIX):
            graphics.append({"tile": int(name.rsplit(":", 1)[1]), "pose": pose})
        else:
            graphics.append({"name": name, "index": index, "pose": pose})
        tile_pass.append(rm2k.event_tile_passability(
            game_map, name, data["layer"]))
    out["page_graphic"] = graphics
    out["tile_passability"] = tile_pass

    starting = []
    for event in inputs["events"]:
        pages = []
        for data in sorted(event["pages"], key=lambda p: p["id"]):
            condition = lcf.EventPageCondition(
                dict(CONDITION_IDS, flags=data["condition"]["flags"]))
            pages.append(SimpleNamespace(id=data["id"],
                                         unconditional=not condition))
        page = lcf.Event.active_page(SimpleNamespace(pages=pages))
        starting.append(None if page is None else page.id)
    out["starting_page"] = starting

    actors = []
    for data in inputs["actors"]:
        a = _actor(data)
        top = experience.max_level(a)
        actors.append({
            "max_level": top,
            "initial_level": experience.initial_level(a),
            "initial_exp": experience.initial_exp(a),
            "exp_list": experience.exp_list(a),
            "next_exp": [experience.next_exp(a, n) for n in range(-1, top + 2)],
            "add_exp": [list(experience.add_exp(a, level, exp, amount))
                        for level, exp, amount in inputs["exp_gains"]],
        })
    out["actors"] = actors

    tree = _tree(inputs["tree"])
    ids = [n["id"] for n in inputs["tree"]] + [99]
    out["background"] = [lcf.TreeMap.map_background(tree, i) for i in ids]
    out["music"] = [(lambda m: None if m is None else m["name"])(
        lcf.TreeMap.map_music(tree, i)) for i in ids]
    return out


def test_the_python_rules_still_answer_what_the_rust_copy_is_held_to():
    with open(FIXTURE, encoding="utf-8") as handle:
        fixture = json.load(handle)
    now = json.loads(json.dumps(answers(fixture["inputs"])))
    for name, expected in fixture["answers"].items():
        assert now[name] == expected, (
            "%s: the Python rule no longer answers what rm2k-rules is "
            "held to; see this file's docstring" % name)
    assert set(now) == set(fixture["answers"])
