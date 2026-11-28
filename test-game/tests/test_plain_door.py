"""A page with nothing left after its `Teleport` carries no bytecode.

RM2k lets a page go on after a `Teleport`, so the console carries that
page's bytecode to the new map: `code_carry_before` and `code_carry_after`,
in the runtime's `decompress.s`, decompress the whole bytecode stream of the
map being left into `CODE_CARRY` at the end of the load. Until 2026-11-28
they did it for every page halfway through, and a door is one: a touch page
whose only command is the `Teleport`. On a game whose maps carry a lot of
bytecode that was frames of every door, spent to run one `OP_DONE`. Now
a page whose next opcode —through the `OP_GOTO`s an `else` or a choice's
option leaves behind it— is an `OP_DONE` with nobody to return to is not
carried: it is pointed at an `OP_DONE` in the cartridge, and still ends on
the frame after the load.

Two such pages, both a jump to another map:

* the lookout's dispatcher, map 10, an automatic page whose only command is
  the `Teleport` to the clearing —the guide's "Lookout, sent on" turns its
  switch on—: a door's shape, with nothing after the jump;
* the guide's own teleport, the last command of a `ShowChoice`'s option:
  what follows it is the jumps past the other options, to the page's end.

**What it asks**: that after each `CARRY_MAP` says nothing is carried, and
that the player gets control on the new map —the page did end—.

Seen red with the runtime before the change: `CARRY_MAP` is the map left.

What it does not ask: a page that goes on after its jump is still carried,
which `test_panorama_swap.py` asks; and a page inside a call —the tester's
cases, a page each of the shelf the tester calls— is carried as before,
since its end returns to its caller.
"""

from play import boot, go_to

CLEARING = 4
GARDEN = 2
NONE = 0xFFFF       # `CARRY_MAP` when no page is carried


def carried(sess):
    """Which RM2k map's bytecode is carried, or None."""
    index = sess.word("CARRY_MAP")
    return None if index == NONE else sess.cartridge.maps[index]


def test_a_door_carries_nothing(core):
    sess = boot(core)
    go_to(sess, "Lookout, sent on")
    sess.until("control on the clearing",
               lambda: sess.map_() == CLEARING and sess.has_control(), 600)
    assert carried(sess) is None, (
        "the dispatcher's page has nothing after its Teleport, and map %s's "
        "bytecode was carried to the clearing" % carried(sess))


def test_a_jump_at_the_end_of_an_option_carries_nothing(core):
    sess = boot(core)
    go_to(sess, "Garden")
    sess.until("control on the garden",
               lambda: sess.map_() == GARDEN and sess.has_control(), 600)
    assert carried(sess) is None, (
        "the guide's page has nothing after its Teleport but the jumps past "
        "the other options, and map %s's bytecode was carried"
        % carried(sess))
