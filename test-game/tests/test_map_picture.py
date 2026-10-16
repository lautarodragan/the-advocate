"""A translucent picture that stays put over a map, drawn into the map:
the lantern —map 5—, reached by the `Teleport` of case `lantern`.

Map 5's parallel event lays `Picture/Night` over it —a near-black mask with
a cone of light, fixed to the map at transparency 35— and erases itself,
the way Desert Nightmare lights its interiors. The console has no layer
free for a mask in mode 3, so with `[graphics] map_pictures` the converter
blends it into the map's tiles at its RM2k opacity before converting them
—`map_pictures.rs` in rm2k-snes-convert and in Wally—, into the layer
above the hero too: the tree in the cone keeps its crown lit, the one in
the dark has it shaded. What it loses, the hero not being shaded, is in the
book's "Pictures drawn into the map".

Two goldens, in snes9x and in bsnes: on arrival, in the dark, and three
steps up, under the lantern, where the camera has scrolled.

Seen red with the tools before the change: the crowns stayed at their
full colour under the mask, since only the lower layer was blended.
"""

from game import Session, golden

LANTERN = 5
# Where the case's Teleport leaves the hero, and where it walks to.
ARRIVAL = (10, 10)
UNDER_THE_LAMP = (10, 7)


def settled(sess):
    """A few ticks more, so the map is drawn whole and the hero is up."""
    for _ in range(30):
        sess.advance()


def test_the_mask_shades_the_map_and_its_layer_above(core):
    sess = Session(core, case="lantern")
    sess.until("on map %d with control" % LANTERN,
               lambda: sess.map_() == LANTERN and sess.has_control(), 600)
    settled(sess)
    assert sess.cell() == ARRIVAL, "the hero is at %s" % (sess.cell(),)
    golden("lantern-dark", sess.image(), core)
    # Up to the tree's trunk, which blocks: three cells.
    sess.walk_until_blocked("up")
    settled(sess)
    assert sess.cell() == UNDER_THE_LAMP, "the hero is at %s" % (sess.cell(),)
    golden("lantern-lit", sess.image(), core)
