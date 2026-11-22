"""RM2k's variables: that the ROM computes them, compares them and saves them.

The ROM is asked about its far RAM, which is where they live, and about the
switches a branch by variable turned on. The case pages write them with
RM2k's own numbers: variable, operation (0 sets, 1 adds, 2 subtracts, 3
multiplies, 4 divides, 5 takes the modulo), class of the operand (0
constant, 1 another variable, 3 random, 4 an item, 6 a character, 7 other)
and two numbers. Each one turns 1401 on last, so a page that stopped
halfway is told apart from one that computed wrong.

It came from A Blurred Line's suite, in the ports, on 2026-11-22, where the
pages ran on its map 5 and two of the cases were that game's own: its
common event 45, which sets six variables past the word, and its actor
Kersh's weapon. Here the first is the same command written in a case, and
the second this game's Sword.
"""

import pytest

from rm2k_snes_harness import Session, core_name, engine

INSIDE, END = 1400, 1401


def ran(core, case):
    """The case, run to its end: the switch it turns on last, or a red that
    says it did not get there."""
    sess = Session(core, case=case)
    try:
        sess.until("the page's end", lambda: sess.switch(END), 300)
    except AssertionError:
        raise AssertionError("the page did not reach the end: the case tested nothing")
    return sess


def next_random(x):
    """The ROM's generator, a sixteen-bit xorshift —x ^= x << 7; x ^= x >> 9;
    x ^= x << 8—, seeded at reset with `engine.RANDOM_SEED`: no entropy, on
    purpose, so what a page draws can be frozen. It is the generator of the
    battle's model too, `rm2k-snes-battle`."""
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x


def test_the_operations_give_what_they_give_in_python(core):
    """Set, add, subtract with sign, copy from another and read the gold."""
    sess = ran(core, "variables")
    assert sess.variable(17) == 12
    assert sess.variable(39) == 12
    assert sess.variable(40) == -7, "the signed subtraction did not give -7"
    assert sess.variable(41) == 0, "the starting gold is zero"


def test_the_randomness_is_the_same_on_both_sides(core):
    """The ROM's first random number is the first of the xorshift from the
    same seed: if they drifted apart, the tests that compare a battle number
    by number would drift apart with it."""
    sess = ran(core, "variables")
    expected = next_random(engine.RANDOM_SEED) % 101
    assert sess.variable(21) == expected, (
        "the ROM drew %d and Python's xorshift %d" % (sess.variable(21), expected))


def test_the_branch_by_variable_decides(core):
    sess = ran(core, "variables")
    assert sess.switch(INSIDE), "var 17 is 12 and the >= 12 branch was not taken"


def test_the_unmet_branch_by_variable_does_not_run(core):
    """And the other half, which is the one that can break without anything
    noticing: until 2026-09-12 the `ConditionalBranch` by variable was
    **always** taken —`compare_var` left the answer in the flags and the
    `ply` that restores the cursor overwrote them—, and everything looked at
    the branch that is met. Seen red with that defect, in A Blurred Line."""
    sess = ran(core, "variables-branch-no")
    assert not sess.switch(INSIDE), (
        "var 17 is 12, the branch asked for >= 99, and it was taken anyway")


def test_the_variables_travel_in_the_save(core):
    """They are saved with the game and come back after the reset, which
    zeroes the WRAM before loading."""
    if core_name(core) == "bsnes":
        # bsnes exposes no SRAM to clear afterwards, and keeps it from one
        # console to the next in the same process: a cartridge without a
        # title loads a saved game on boot, so every test after this one
        # would start from it. The save is the ROM's: one core is enough.
        pytest.skip("bsnes keeps the SRAM between tests and does not let it be cleared")
    sess = Session(core, case="variables-saved")
    try:
        sess.screen_up()
        sess.choose()
        assert sess.variable(17) == 12
        sess.reset()
        sess.run(10)
        assert sess.variable(17) == 12, "variable 17 did not come back from the SRAM"
        assert sess.variable(40) == -7
    finally:
        sess.console.write_sram(0, bytes(len(sess.console.sram())))


def test_the_place_on_screen_is_rm2ks(core):
    """`ControlVars` with a character's place on the screen —4 and 5 of
    class 6—, in pixels of **RM2k**'s screen, 320x240: the centre of its
    cell and its feet, minus where the view starts.

    On the plain, 200x200, the hero at (100, 100) is far from the edges, so
    RM2k's view follows them with its usual pan —nine cells to the left and
    seven up, liblcf's `kPanXDefault` and `kPanYDefault`— and starts at
    (1456, 1488): the hero is at (152, 128). On the meadow, which is the
    screen's size, the view stays at its corner: the hero at (10, 10) is at
    (168, 176), the elder at (10, 6), with a graphic, at (168, 112), and
    Chain 1 at (18, 1), with nothing to draw, at (296, 32)."""
    sess = ran(core, "screen-of-hero")
    read = [sess.variable(v) for v in (17, 39)]
    assert read == [152, 128], "the hero on the plain gave %s" % read
    sess = ran(core, "screen-of-events")
    read = [sess.variable(v) for v in (17, 39, 40, 41, 21, 25)]
    assert read == [168, 176, 168, 112, 296, 32], (
        "the hero, the elder and Chain 1 on the meadow gave %s" % read)


def test_putting_more_than_the_word_saturates(core):
    """999999, as "no cell", is what A Blurred Line's common event 45 sets
    six variables to. The ROM carries them in sixteen signed bits, so the
    compiler puts it at the word's ceiling: see the divergence
    `variables-saturate-at-16-bits` in the book."""
    sess = ran(core, "variables-past-the-word")
    for v in (177, 178, 179, 180, 183, 184):
        assert sess.variable(v) == 0x7FFF, (
            "variable %d was left at %d and should be at the ceiling"
            % (v, sess.variable(v)))


def test_a_random_range_wider_than_a_byte(core):
    """`ControlVars` random over any range of the word, as
    `Rand::GetRandomNumber(min, max)`. Five draws in a row: two wide ones
    —the second with its ends reversed, which RM2k swaps—, a negative one,
    the whole word, and a byte-wide one, which still goes through the
    hardware's divider. Each is `a + x mod (b - a + 1)` of the next step;
    the whole word, `x` itself."""
    sess = ran(core, "variables-random-wide")
    x, expected = engine.RANDOM_SEED, []
    for a, b in ((1000, 2500), (100, 500), (-300, -10), (-32768, 32767), (0, 100)):
        x = next_random(x)
        expected.append(a + x % (b - a + 1))
    read = [sess.variable(v) for v in (17, 39, 40, 41, 21)]
    assert read == expected, "the ROM drew %s and Python's xorshift %s" % (read, expected)


def rm2k_operation(left, operation, right):
    """easyrpg's `VarMult`, `VarDiv` and `VarMod`, clamped to the variable's
    range, which on the console is the signed word: C's division truncates
    toward zero and its remainder takes the dividend's sign; by zero, the
    division leaves the variable and the modulo gives 0."""
    if operation == 3:
        result = left * right
    elif right == 0:
        result = left if operation == 4 else 0
    else:
        quotient = abs(left) // abs(right)
        if (left < 0) != (right < 0):
            quotient = -quotient
        result = quotient if operation == 4 else left - quotient * right
    return max(-0x8000, min(0x7FFF, result))


# The page of `variables-arithmetic`: (variable, what it starts at, the
# operation, the operand). 40 and 80 take another variable: 41, which is
# -3, and 81, which is 7.
ARITHMETIC = (
    (17, 300, 3, 200), (39, -300, 3, 200), (173, 1000, 3, 1000),
    (123, -1000, 3, 1000), (84, 181, 3, 181), (82, -32768, 3, 1),
    (40, -12, 3, -3), (21, -7, 4, 2), (44, -7, 5, 2), (43, 7, 5, -2),
    (45, 17, 4, 0), (48, 17, 5, 0), (25, -32768, 4, -1), (79, 25000, 4, -3),
    (80, 1000, 5, 7),
)


def test_multiply_divide_and_modulo_are_rm2ks(core):
    """A product past the word on each side, with and without a high word,
    two that just fit, divisions and remainders of every sign, both by
    zero, -32768 / -1, and one of each by a variable; Python gives the
    numbers."""
    sess = ran(core, "variables-arithmetic")
    read = {v: sess.variable(v) for v, _, _, _ in ARITHMETIC}
    expected = {v: rm2k_operation(start, operation, operand)
                for v, start, operation, operand in ARITHMETIC}
    assert read == expected


def test_a_variable_from_an_item_count(core):
    """`ControlVars` from an item, `ControlVariables::Item`: how many the
    party carries, and how many its members have equipped, where 0 counts
    the empty slots, as RPG_RT does. The page carries thirteen Swords, adds
    the count to a 5, has the Hero equip one —which RM2k takes out of the
    bag— and counts again: twelve carried, one worn, and the Hero's other
    four slots empty."""
    sess = ran(core, "variables-item-count")
    read = [sess.variable(v) for v in (17, 39, 40, 41, 21)]
    assert read == [13, 18, 12, 1, 4]
