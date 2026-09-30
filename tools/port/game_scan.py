"""What the converter deduces from the whole game before converting any map:
which actors can end up leading the party, which items and members can be in
it, where the hero starts, and whether some map sets rain.

The input is the ROM's maps and the database; the output, sets of ids. The
game directory comes from `main` through `args_game_dir`.
"""

import os

from port import compiler, events
from rpgmaker import lcf
from rpgmaker import resources


def has_rain(map_ids, extra=()):
    """Whether some page of these maps sets rain: then every map of the ROM
    carries the drops, because the weather persists across map changes.
    `extra` are the commands of the test pages."""
    def rains(cmd):
        return (cmd.code == events.WEATHER_EFFECTS
                and cmd.parameters[:1] == [events.WEATHER_RAIN])
    if any(rains(cmd) for cmd in extra):
        return True
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_game(),
                                        "Map%04d.lmu" % map_id))
        for event in game_map.events:
            for page in event.pages:
                for cmd in page.commands:
                    if rains(cmd):
                        return True
    return False


def possible_leaders(renderer, map_ids, party, scan=None):
    """The actors that can end up drawn as the hero in this ROM.

    The party it starts with, plus all the ones some `ChangePartyMembers` of
    some page that compiles adds. Removing someone also changes the leader,
    but to the next on the list, who is already counted.

    It is compiled with a text block, same as the real compilation: a page
    that adds someone to the party after a text box compiles only with it.
    Filtering differently here than there would leave that actor without its
    tiles in VRAM and the ROM would draw it with the previous one's. The text
    block built is throwaway: here only the yes or no matters.

    It is needed because the hero's tiles live in VRAM and aren't loaded on
    the fly: if the leader can change mid-map, the sprites of all the
    candidates have to be in place from the start.

    **And they are the ones that can go first, not all the ones that join the
    party.** The hero's graphic is the first one's; someone who always joins
    behind another is never drawn, and their twelve poses are 192 tiles that
    don't fit. It shows in the opening cutscene, which removes 10 and adds 11,
    12 and 13: with all four it is 628 sprite tiles and the layout gives 512.

    Who goes first is known by simulating: the `ChangePartyMembers` of the
    pages that compile are applied, in the order they appear, with the same
    rules as `PartyState.change_party`. It is an approximation —which page runs
    and when depends on switches that aren't known here— and that is why the
    order matters: if a ROM ever draws the hero with no graphic, start by
    looking here.

    **The party is reset in each map**, and that is the part that was hard.
    It used to be carried from one map to the next in file order, which isn't
    the order they are played in: the "1 year earlier" page of map 4 sets
    Talan, and since 4 goes before 1, when the simulation reached the opening
    the party already had Talan. The opening's `pone Kersh` put him
    **behind**, so Kersh was never leader, didn't go into the actor table and
    the hero was drawn with no graphic. taro saw it while playing: Core and
    Manta showed up at the end of the stairs and Kersh didn't.

    Resetting per map isn't more correct in general —it still isn't known
    with which party each one is reached— but it is the approximation that
    fits: the actor table is **per map**, so the question is who can lead
    while that map is loaded, and not what happened in the directory's
    previous maps.
    """
    actors = list(party[:1])
    for changes in _party_changes(map_ids, scan):
        state = events.PartyState(party)
        for batch in changes:
            for who, operation in batch:
                state.change_party(who, operation)
            leader = state.leader()
            if leader is not None and leader not in actors:
                actors.append(leader)
    return actors


def _party_changes(map_ids, scan=None):
    """The `ChangePartyMembers` of the pages that compile, map by map and in
    order: the only thing of each map `possible_leaders` looks at.

    Which pages compile is the compiler's first answer —see `compiler.scan`—:
    `scan` if the caller already has it, and otherwise it is asked for.

    **It is computed once per conversion**, because it doesn't depend on the
    party: `possible_leaders` runs again for each test case that touches the
    party, and each run loaded all the maps again.
    """
    key = (_game(), tuple(map_ids))
    if key not in _changes_by_map:
        if scan is None:
            scan = compiler.scan(compiler.dump_of(_game()), map_ids)
        _changes_by_map[key] = [
            _map_changes(map_id, compiler.compiling_pages(scan, map_id))
            for map_id in map_ids]
    return _changes_by_map[key]


_changes_by_map = {}


def _map_changes(map_id, compiling):
    """`compiling` are the `(event, page)` that compile, by index. They are
    compiled with the same context as the real compilation —the map's, the
    text block, the songs, the graphics—, and it was not always so: without
    the map, a page that sends another event walking didn't compile here and
    did there, and the actors it adds were lost —the opening cutscene adds
    Kersh right after sending event 8 walking, and the hero wasn't drawn—;
    without the songs, the same with the chase car, whose `RaceController1`
    of map 49 starts with a `PlayBGM` and then adds `CarRED`."""
    changes = []
    game_map = lcf.Map(os.path.join(_game(),
                                    "Map%04d.lmu" % map_id))
    for e, event in enumerate(game_map.events):
        for k, page in enumerate(event.pages):
            if (e, k) not in compiling:
                continue
            # **In batches of consecutive commands**, and the leader is looked
            # at the end of each one: `ChangePartyMembers` stuck together run
            # in the same frame —none waits— so the hero isn't drawn with the
            # mid-batch leader. Looking at it after each command, 41 —which
            # removes everyone before adding Talan back, and does it in two
            # consecutive pages— left Arden, Saldra and AG7 as possible
            # leaders, with their poses and their colors in every map of the
            # cartridge, and moved the palettes of maps that have nothing to
            # do with it.
            batch = None
            for cmd in page.commands:
                if cmd.code != events.CHANGE_PARTY_MEMBERS:
                    batch = None
                    continue
                p = cmd.parameters
                if len(p) < 3 or p[1] != events.PARTY_FIXED_ID:
                    batch = None
                    continue
                if batch is None:
                    batch = []
                    changes.append(batch)
                batch.append((p[0], p[2]))
    return changes


# The game directory, for `possible_leaders`. It is ugly but it is a single
# place: the alternative was passing it through three functions that don't
# use it. `main` sets it, from `--game-dir`.
args_game_dir = [None]


def _game():
    """`main`'s or, if it didn't go through there —a test that calls these
    functions on their own—, the environment's, which is the same
    `--game-dir`."""
    return args_game_dir[0] or resources.GAME_DIR


def possible_items(map_ids, actors=(), db=None, extra=()):
    """The items that can be in the inventory with these maps in the ROM: the
    ones some `ChangeItems` of any page gives, whether it compiles or not,
    the ones some `OpenShop` sells, the equipment the `actors` start with
    and the ones the test page gives. It is a superset, like
    `possible_members`, and for the same reason: one item too many costs its
    text in the cartridge, one too few isn't seen in the list. `extra` are
    the commands of the test pages, which are swept the same as the maps'."""
    items = set()
    for actor in actors:
        if db is not None and actor in db.actors:
            items.update(i for i in db.actors[actor].initial_equipment if i)

    def sweep(commands):
        for cmd in commands:
            p = cmd.parameters
            if (cmd.code == events.CHANGE_ITEMS and len(p) >= 5
                    and p[0] == 0 and p[1] == 0):
                items.add(p[2])
            elif cmd.code == events.OPEN_SHOP:
                items.update(p[4:])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_game(),
                                        "Map%04d.lmu" % map_id))
        for event in game_map.events:
            for page in event.pages:
                sweep(page.commands)
    sweep(extra)
    return sorted(i for i in items if 0 < i < events.ITEMS_N)


def drop_items(db, troops):
    """The items some enemy of these troops can drop on losing a battle —its
    `drop_id`—, so that the cartridge carries their name: the victory tells
    it and the menu's list shows it. The ones `possible_items` doesn't find
    in any page. All the members, like `rom_enemies`."""
    return {db.enemies[e].drop_id for n in troops if n in db.troops
            for e in db.troops[n].members
            if 0 < db.enemies[e].drop_id < events.ITEMS_N}


def possible_members(map_ids, party, extra=()):
    """The actors that can be in the party with these maps in the ROM.

    The starting ones plus the ones any `ChangePartyMembers` of any page of
    these maps adds. Whether the page compiles isn't looked at: it is for the
    slots screen, which needs the face and the name of whoever can show up in
    a saved game, and one face too many costs nothing that matters. `extra`
    are the commands of the test pages.

    `party` can bring repeats —the cartridge's plus that of each test case,
    which is usually the same— and they are counted once: repeated, an actor
    took one face for each case that asked for it.
    """
    actors = list(dict.fromkeys(party))

    def sweep(commands):
        for cmd in commands:
            if cmd.code != events.CHANGE_PARTY_MEMBERS:
                continue
            p = cmd.parameters
            if len(p) < 3 or p[1] != events.PARTY_FIXED_ID:
                continue
            if p[0] == 0 and p[2] not in actors:
                actors.append(p[2])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_game(),
                                        "Map%04d.lmu" % map_id))
        for event in game_map.events:
            for page in event.pages:
                sweep(page.commands)
    sweep(extra)
    return sorted(actors)
