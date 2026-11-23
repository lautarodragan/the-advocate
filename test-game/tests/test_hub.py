"""The meadow's hub: that it is what `hub.toml` says, that it offers every
case and every map, and that each map is reached from it and left with the
Way Home.

Every other test of the game reaches what it tests through the hub —see
`play.py`—, so a case that the tester's menus lead to the wrong place is
red there; this is the part no other test walks: the maps nobody tests
yet, and the way back from each.
"""

import json
import os

import pytest

from rm2k_snes_harness import MESSAGE_SHOWN

import hub
from play import MEADOW, START, boot, go_home, go_to

GAME = hub.ROOT


def test_the_meadow_has_the_hub_that_hub_toml_says():
    with open(hub.MEADOW) as file:
        text = file.read()
    assert hub.written(text) == text, (
        "src/maps/Map0001.json is not what hub.toml and tester/ make: run "
        "`python3 tests/hub.py` in test-game/")


def test_the_tester_offers_every_case_once():
    data = hub.load()
    offered = [n for g in data["tester"]["group"] for n in g["cases"]]
    assert len(offered) == len(set(offered)), "a case is offered twice"
    files = {n[:-len(".json")] for n in os.listdir(hub.TESTER)}
    used = {data["tester"].get("case", {}).get(n, {}).get("file", n) for n in offered}
    assert used == files, (
        "tester/ and the tester's menus disagree: not offered %s, no file %s"
        % (sorted(files - used), sorted(used - files)))
    paths = hub.tester_paths(data)
    assert sorted(paths) == sorted(offered)
    assert len({tuple(p) for p in paths.values()}) == len(paths), (
        "two cases share the same options")


def test_the_harness_cases_are_only_the_boot_and_the_probe():
    """What stays in `cases/` is what the harness still injects: `nothing`,
    the game as it boots, and the probe cartridge's `terrace`, which is the
    guide's teleport to the same cell —keeping the facing the hero boots
    with, where the guide's turns them down, which is the same—."""
    cases = sorted(os.listdir(os.path.join(GAME, "cases")))
    assert cases == ["nothing.json", "terrace.json"]
    with open(os.path.join(GAME, "cases", "terrace.json")) as file:
        teleport = json.load(file)["event_commands"]
    terrace = next(m for m in hub.load()["guide"]["map"] if m["label"] == "Terrace")
    assert [c["code"] for c in teleport] == ["Teleport"]
    assert teleport[0]["parameters"][:3] == terrace["to"][:3]


def test_the_guide_goes_to_every_map():
    with open(os.path.join(GAME, "src", "maps.json")) as file:
        maps = {m["id"] for m in json.load(file)["maps"] if m.get("type") == "map"}
    reached = {m["to"][0] for m in hub.load()["guide"]["map"]}
    assert reached == maps - {MEADOW}, (
        "the guide does not go to %s" % sorted(maps - {MEADOW} - reached))


# Each of the guide's teleports, and where it lands: the map, or for the
# lookout sent on, the clearing its dispatcher sends the hero to.
LANDINGS = [(m["label"], m["to"]) for m in hub.load()["guide"]["map"]]
# Maps that start a scene of their own on arriving, which takes the player's
# presses: they are walked to and not left.
SCENES = {"Terrace"}
# The vast is left out of the cartridge: its teleport is a box on the
# meadow.
LEFT_OUT = {"Vast"}


@pytest.mark.parametrize("label,to", LANDINGS, ids=[l for l, _ in LANDINGS])
def test_each_map_is_reached_and_left(core, label, to):
    sess = boot(core)
    if label in LEFT_OUT:
        from play import choose, talk_to
        talk_to(sess, "left")
        for option in hub.guide_paths()[label]:
            choose(sess, option)
        sess.until("the box that says it is not there",
                   lambda: sess.byte("msg_open")
                   and sess.byte("msg_state") == MESSAGE_SHOWN, 300)
        assert sess.map_() == MEADOW
        return
    go_to(sess, label)
    if to[0] == 10 and 1430 in hub.load()["guide"]["map"][
            [l for l, _ in LANDINGS].index(label)].get("on", []):
        sess.until("sent on", lambda: sess.map_() == 4, 600)
    else:
        assert sess.map_() == to[0]
        sess.until("arrived", lambda: not sess.byte("fade"), 300)
        assert sess.cell() == (to[1], to[2]), "landed at %s" % (sess.cell(),)
    if label in SCENES:
        return
    sess.until("control", sess.has_control, 600)
    go_home(sess)
    assert sess.cell() == START
