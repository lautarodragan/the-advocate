"""A `ChangePBG` that swaps the panorama for another picture, while a page
carried from another map is waiting: the lookout, map 10.

Since 2026-11-16 a panorama's tiles travel as LZ2 and are decompressed
into `LZ2_BUFFER` before their DMA —see `pano_load` in `runtime/pano.s`—.
On a load nothing else lives there yet; on a swap in the middle of the map
the buffer holds the bytecode of a page that goes on after a `Teleport`
—`CODE_CARRY`— and the battle animation's frames, and `pano_image`
rebuilds both after the tiles. This is the first of the two: the case
`panorama-swap` teleports to the lookout and waits a second there; the
lookout's parallel page, "Dawn", swaps `Stars` for `Dawn` half a second
in; and the case page goes on, from `CODE_CARRY`, to turn switch 1700 on
and show a box.

**What it asks**: that on arriving the panorama is `Stars` and the case
page is the carried one —`CARRY_MAP` is the map it came from—; that
after the swap the picture is `Dawn` and the carried bytecode is byte for
byte what it was; that the page goes on to its switch and its box; and
what it looks like, before and after.

Seen red with `pano_image` not calling `code_carry_after`: the carried
bytecode comes back as the picture's tiles.

What it does not ask: the battle animation's frames, the other thing in
the buffer —`anim_buf_clear` after the swap—; no case shows a battle
animation on a map while its panorama is swapped.
"""

from game import MESSAGE_SHOWN, Session, golden

LOOKOUT = 10
AFTER_SWAP = 1700   # the case page's switch, after its wait
STARS, DAWN = 0, 1  # the lookout's `pano_table` records: its own, then Dawn's
NONE = 0xFFFF       # `CARRY_MAP` when no page is carried


def test_a_swap_keeps_the_carried_page(core):
    sess = Session(core, case="panorama-swap")
    sess.until("on map %d" % LOOKOUT,
               lambda: sess.map_() == LOOKOUT and not sess.byte("fade"), 600)
    # The fade in and a few ticks more, so the map is drawn whole; the
    # parallel waits half a second before its swap.
    for _ in range(8):
        sess.advance()
    assert sess.byte("PANO_ON"), "the lookout shows no panorama"
    assert sess.byte("PANO_IMG") == STARS, (
        "the lookout arrived with record %d, not Stars'" % sess.byte("PANO_IMG"))
    carried = sess.word("CARRY_MAP")
    assert carried != NONE, (
        "no page is carried: the case page did not go on past its Teleport")
    at = sess.symbol("CODE_CARRY") & 0x1FFFF
    code = bytes(sess.console.ram(at, 256))
    golden("lookout-stars", sess.image(), core)

    sess.until("the swap to Dawn", lambda: sess.byte("PANO_IMG") == DAWN, 120)
    assert sess.word("CARRY_MAP") == carried, "the carried map changed"
    assert bytes(sess.console.ram(at, 256)) == code, (
        "the carried bytecode changed with the swap: `pano_load` "
        "decompressed the tiles over `CODE_CARRY` and nothing put it back")

    sess.until("switch %d on" % AFTER_SWAP, lambda: sess.switch(AFTER_SWAP), 120)
    sess.until("the box shown", lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN, 300)
    for _ in range(4):
        sess.advance()
    golden("lookout-dawn", sess.image(), core)
