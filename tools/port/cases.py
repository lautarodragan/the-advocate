"""The cartridge's test cases: the command line split at each `--case`,
each case's page of RM2k commands, the map it runs in, and the party it
leaves behind. See `--case` in `snes_convert.py`.
"""

import json
import sys

from port import events
from rpgmaker import lcf
from port.options import map_order


def test_graphics(argument):
    """The (CharSet, index) pairs of `--test-graphic`, or () if none."""
    return tuple((charset, int(index)) for charset, index in argument or ())


def page_party(case, party):
    """Which party the test continues with after its page, if the page
    touches it: the case's `ChangePartyMembers` applied to the cartridge's
    party, with the same rules as the interpreter. None if it doesn't touch
    it."""
    state = events.PartyState(party)
    touches = False
    for cmd in case.commands:
        p = cmd.parameters
        if (cmd.code == events.CHANGE_PARTY_MEMBERS and len(p) >= 3
                and p[1] == events.PARTY_FIXED_ID):
            state.change_party(p[0], p[2])
            touches = True
    return state.party if touches else None


# The flags that describe **a test case** —what its page does— and not the
# cartridge. They are the ones that can go after a `--case`; the rest belong
# to the whole cartridge and go before the first one. Since cut 3 of step 9d
# there is a single one, the file with the page: what the page does is RM2k
# data, not flags. `--test-graphic` belongs to the cartridge on purpose:
# it says which graphics are in the sprite bank of the maps where the cases
# run, not what the page does. And where a case runs isn't a flag either: the
# `Teleport` it starts with says so, see `case_map`.
CASE_FLAGS = ("test_commands",)


def split_cases(argv):
    """The command line split at `--case`: the cartridge's part, and the
    flags of each case that goes after."""
    stretches = [[]]
    for token in argv:
        if token == "--case":
            stretches.append([])
        else:
            stretches[-1].append(token)
    return stretches[0], stretches[1:]


def test_cases(parser, args, stretches):
    """The cartridge's test pages, one per case, in the order of their pages.
    Each one is a copy of `args` with its case's flags.

    Case 0 is the flags before the first `--case`, so a single-case cartridge
    is built as before this existed. If there are none, the first `--case`
    becomes 0. Each case takes the commands of its file in `commands`.
    """
    import copy
    cases = [args] if asks_test_page(args) else []
    default_args = parser.parse_args([])
    for stretch in stretches:
        loose = parser.parse_args(stretch)
        for dest, value in vars(loose).items():
            if dest not in CASE_FLAGS and value != getattr(default_args, dest):
                sys.exit("--%s belongs to the cartridge and not to a case: it "
                         "goes before the first --case" % dest.replace("_", "-"))
        case = copy.copy(args)
        for dest in CASE_FLAGS:
            setattr(case, dest, getattr(loose, dest))
        if not asks_test_page(case):
            sys.exit("a --case with nothing for the test page to do")
        cases.append(case)
    for case in cases:
        with open(case.test_commands, encoding="utf-8") as fh:
            case.commands = lcf.handwritten_commands(json.load(fh))
    return cases


def case_commands(args, map_id=None):
    """The commands of all the test pages, one after the other.

    It is what the functions that look at the map's pages to decide what the
    cartridge carries —variables, items, members, rain— sweep: a test page is
    one more page.

    With `map_id`, only those of the cases that **run** in that map —see
    `case_map`—: they are the ones that decide what belongs to each map,
    like who walks or which graphics go in its sprite bank.
    """
    return [cmd for case in args.cases
            if map_id is None or case.run_map == map_id
            for cmd in case.commands]


def case_map(case, order, initial):
    """The map where a case runs: that of its `Teleport`, if it starts with
    one, and otherwise the map where the ROM boots.

    It is how a case chooses where to start since step 9e, instead of a
    `--map-id` and a starting cell per cartridge: with RM2k's `Teleport`,
    which is data and not a flag. The page still lives in event 0 of the boot
    map —that is where the ROM finds it and where it runs first—, but what
    comes after the jump runs in the other map, so it is compiled with that
    one's context: its events, the variables its pages look at, its graphics.
    Compiled with the boot map's, a write to a variable only the destination
    looks at didn't ask for a refresh, and the chest of map 133 didn't appear
    even though the variable already held what its page asks for.
    """
    first = case.commands[0] if case.commands else None
    if first is None or first.code != events.TELEPORT:
        return order[initial]
    dest = first.parameters[0]
    if dest not in order:
        sys.exit("%s: the case jumps to map %d, which isn't in the cartridge "
                 "(it carries %s)" % (case.test_commands, dest,
                                      " ".join(str(m) for m in order)))
    return dest


def test_maps(args):
    """The maps where some case runs, which are the ones that carry the
    graphics of `--test-graphic` in their bank."""
    if args.cases:
        return {case.run_map for case in args.cases}
    return {map_order(args)[args.start_index]}


def asks_test_page(args):
    """Whether there is a test page before the first `--case`."""
    return bool(args.test_commands)
