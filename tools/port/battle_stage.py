"""The battle's model and its text screen, which are `rm2k-snes-battle`'s:
what goes into its second request and the shape its answer takes for the
converter.

**The rules are the stage's** —which skills the battle offers, what each
enemy can do, which items go in the list, what a troop gives— and so are
the battle screen's geometry and the texts it writes, already cut; see its
README, `tools/rm2k-snes/battle/`. What stays here is what the cartridge
decided and the stage does not know: which actors, troops and items it
carries, and the (actor, skill) pairs the compiler gave a slot.

The stage's first call, `tables` —experience and encounters—, comes before
the pages compile, and `snes_convert` makes it itself.
"""

import json
import types

from port import stage

BINARY = "rm2k-snes-battle"
PROJECT = "battle"


def model(dump, actors, troops, items, pairs, item_name_width):
    """The battle's model for this cartridge, as `model.json` answers it,
    with its `layout` as a namespace: `model(...)["layout"].BA_MSG_ROW1`.

    `pairs` are the compiler's (actor, skill) pairs, in the order of their
    slot; `item_name_width`, how much of an item's name the item screens
    write, which is theirs."""
    written = stage.run(BINARY, PROJECT, "model", {
        "actors": list(actors), "troops": list(troops), "items": list(items),
        "skill_pairs": [list(p) for p in pairs],
        "item_name_width": item_name_width,
    }, "--data", dump)
    answer = json.loads(written["model.json"])
    answer["layout"] = types.SimpleNamespace(**answer["layout"])
    return answer
