"""The maps where the console loses colours, graded: the meadow loses
none —its golden is `test_meadow.py`'s—, the garden a reasonable amount,
and the showcase too much.

A map's background is 8 bits a pixel with a budget of colours that
depends on how many palettes the layer above the hero needs, and that
layer is 4 bits a pixel, every cell drawn with one palette of fifteen: see
"The CGRAM split" in the book. The garden, `src/maps/Map0002.toml`, puts
two roofs, a dome and a tent above the hero, so Adeleine groups their
cells into the palettes the background leaves and merges a colour here and
there. The showcase, `src/maps/Map0003.toml`, draws ninety-six lower tiles
and the forty most coloured upper tiles, every one of them above the
hero: the background asks for more colours than its budget and the layer
above is left a single palette, and both are merged down hard. The book's
"The tools" page shows the three next to RM2k's own drawing.

These goldens freeze what the console draws today for each grade: a
change in Adeleine or in Wally that moves a merge shows here, on a map
small enough to look at. A capture that looks worse than its golden is
not blessed.
"""

from game import Session, golden


def arrived(sess, map_id):
    """The case's Teleport done and the map drawn whole, as the meadow's
    test waits for it."""
    sess.until("on map %d with control" % map_id,
               lambda: sess.map_() == map_id and sess.has_control(), 600)
    for _ in range(30):
        sess.advance()


def test_the_garden_loses_a_little(core):
    sess = Session(core, case="garden")
    arrived(sess, 2)
    golden("garden", sess.image(), core)


def test_the_showcase_loses_too_much(core):
    sess = Session(core, case="showcase")
    arrived(sess, 3)
    golden("showcase", sess.image(), core)
