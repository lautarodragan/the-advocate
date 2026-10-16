"""A `ChangeMapTileset` is dropped, the page goes on, and the build lists it
in `degradations.json`.

Until 2026-10-16 the command did not compile and its whole page was left
out: in Frozen World that page is the intro's step on map 9, and the game
stopped there. Now the map keeps the ChipSet it was converted with and the
event compiler notes a `tileset-not-changed` loss; see its arm in
`compile_command`.

Common event 3, `Tileset`, in `src/db/commonevents.json`, asks for ChipSet
2 —"Exterior above", the meadow's graphics with every upper tile above the
hero— and then turns switch 1290 on. The case `tileset` calls it: a common
event's losses are listed, a test page's are not —they are the harness's—.

Seen red with the tools before the change: the common event did not
compile, the call was skipped, 1290 stayed off and `degradations.json`
listed nothing.
"""

import json
import os

from game import Session, cartridge

COMMON = 3
AFTER = 1290


def test_the_page_goes_on_past_the_tileset_change(core):
    sess = Session(core, case="tileset")
    for _ in range(60):
        sess.advance()
    assert sess.switch(AFTER), (
        "switch %d is off: the common event's page did not run past its "
        "ChangeMapTileset" % AFTER)


def test_the_build_lists_the_tileset_not_changed():
    with open(os.path.join(cartridge().directory, "degradations.json")) as file:
        degradations = json.load(file)
    lost = [loss for loss in degradations["losses"]
            if loss["kind"] == "tileset-not-changed" and loss.get("common") == COMMON]
    assert len(lost) == 1, lost
    assert lost[0]["name"] == "ChangeMapTileset", lost
    assert "tileset 2" in lost[0]["text"], lost
