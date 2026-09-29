"""Two battle tables of the cartridge: experience and level per actor
—the curves are `experience.py`'s— and the random encounters of each map.
"""

import sys

from port import events
from rpgmaker import lcf
from port import experience as X


def experience_slots(db, actors):
    """The actors that carry experience and level, in the order of their slot.

    They are the ones that can join the party —`ranuras["actores"]`—, because
    only they fight and experience is only gained by fighting: the game
    doesn't use `ChangeExp` or `ChangeLevel` in any map. Having a slot of their
    own and not one per actor number is what makes the save grow by four bytes
    per actor that fights and not for each of the sixty in the LDB. **Always at
    least one**, even if it belongs to nobody: with zero the reset DMA would
    copy 64 KB.
    """
    return sorted(a for a in actors if a in db.actors) or [None]


def experience_asm(db, actors, n_actors):
    """The experience and level tables: see `port.experience`.

    It leaves the segment in RODATA, which is where its caller finds it.

    Per slot of `experience_slots`:

        exp_initial    four bytes: the starting experience, 24 bits, and the
                       level. It is what the reset copies to `FAR_EXP`.
        exp_level_max  `GetMaxLevel()`, one byte.
        exp_curve      where its row starts in `exp_table`, a word.
        level_row      six words: where each parameter curve starts in
                       `level_params`, in the order of `lcf.CURVES`.

    `exp_table` is `MakeExpList` of each distinct curve —four bytes per level,
    `LEVEL_MAX` levels— and `level_params` the six curves of each slot,
    `LEVEL_MAX` words each. Everything goes outside bank 0: it is read when
    winning a battle, when setting it up and on the equipment screen, never
    per frame.
    """
    slots_exp = experience_slots(db, actors)
    k_of = {a: k for k, a in enumerate(slots_exp) if a is not None}
    curves, curve_of, initial, max_levels, rows, params = [], [], [], [], [], []
    for a in slots_exp:
        actor = db.actors[a] if a is not None else None
        exp_curve = (X.exp_list(actor) if actor else [0])
        exp_curve = exp_curve + [0] * (X.LEVEL_MAX - len(exp_curve))
        if exp_curve not in curves:
            curves.append(exp_curve)
        curve_of.append(4 * X.LEVEL_MAX * curves.index(exp_curve))
        exp = X.initial_exp(actor) if actor else 0
        initial += [exp & 0xFF, (exp >> 8) & 0xFF, exp >> 16,
                    X.initial_level(actor) if actor else 1]
        max_levels.append(X.max_level(actor) if actor else 1)
        for curve in lcf.CURVES:
            rows.append(2 * len(params))
            values = list(actor.params.get(curve) or []) if actor else []
            values = (values + [0] * X.LEVEL_MAX)[:X.LEVEL_MAX]
            params += [v & 0xFFFF for v in values]
    if 4 * len(slots_exp) > 0x200:
        raise SystemExit("%d actors with experience don't fit in the 512 "
                         "bytes of FAR_EXP" % len(slots_exp))
    out = ['.segment "RODATA"',
           "EXP_K = %d" % len(slots_exp),
           "EXP_LEVEL_MAX = %d" % X.LEVEL_MAX]

    def table(label, directive, values, width):
        out.append(".block %d" % max(width, width * len(values)))
        out.append("%s:" % label)
        for i in range(0, len(values), 16):
            out.append("    %s %s" % (directive, ", ".join(
                str(v) for v in values[i:i + 16])))

    table("actor_exp_k", ".byte",
          [k_of.get(a, 0xFF) for a in range(n_actors)], 1)
    table("exp_initial", ".byte", initial, 1)
    table("exp_level_max", ".byte", max_levels, 1)
    table("exp_curve", ".word", curve_of, 2)
    table("exp_table", ".dword", [v for c in curves for v in c], 4)
    table("level_row", ".word", rows, 2)
    table("level_params", ".word", params, 2)
    return "\n".join(out) + "\n"


def rom_encounters(maps, tree, test_steps, troops):
    """The random encounters of each map of the cartridge, ready to emit.

    The data lives in the tree and not in the `.lmu`: each node brings its
    list of troops, every how many steps, and —if it is an area— the
    rectangle it covers. See `events.encounter_zones`.

    Along the way it **asks for the troops**, which is what makes the
    cartridge carry their enemies and the battle's audio package: without
    that an encounter would start a battle against a troop that isn't in any
    table.

    `test_steps` replaces the `encounter_steps` of every map. It is for
    the test ROMs: with the game's —from 25 to 85— an encounter takes more than
    a hundred steps, which is what is wanted when playing and not what is
    wanted in a case of the suite.
    """
    records, zones, zone_troops, per_map = [], [], [], []
    for map_info in maps:
        game_map = map_info["game_map"]
        theirs = events.encounter_zones(tree, map_info["id"],
                                        game_map.width, game_map.height)
        steps = (test_steps if test_steps is not None
                 else tree.encounter_steps.get(map_info["id"],
                                               events.ENC_DEFAULT_STEPS))
        if not theirs or not events.enc_base(steps):
            per_map.append(0xFF)
            continue
        per_map.append(len(records))
        record = {"base": events.enc_base(steps),
                  "umbrales": events.enc_step_thresholds(steps),
                  "zona_ini": len(zones), "zona_n": len(theirs)}
        for left, top, right, bottom, which_ones in theirs:
            zones.append({"rect": (left, top, right, bottom),
                          "troop_init": len(zone_troops),
                          "troop_n": len(which_ones)})
            for number in which_ones:
                troops.request(number)
            zone_troops += which_ones
        records.append(record)
    if len(records) > 0xFF or len(zones) > 0xFF or len(zone_troops) > 0xFF:
        # The three tables are indexed with one byte. With the 53 maps of the
        # whole game it is 53 records, 56 zones and 322 troops, so the one
        # that can go over is the last —and today only in a cartridge that
        # carries all of them—.
        sys.exit("the encounters don't fit in one-byte tables: %d "
                 "record(s), %d zone(s), %d troop(s)"
                 % (len(records), len(zones), len(zone_troops)))
    return {"por_mapa": per_map, "registros": records, "zonas": zones,
            "tropas": zone_troops}
