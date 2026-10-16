"""A text box with letters outside ASCII: the Latin-1 ones the console's
font draws come out with their own glyphs —`é`, `ñ`, `¿`, `ß`—, and the rest
as their plain ASCII stand-ins —`…` as `...`, `Œ` as `OE`, and `ø`, which
the font leaves out, as `o`—, which the build lists in `degradations.json`.

Until 2026-10-16 any letter outside ASCII left the whole page out
—`Messages::store`, in the event compiler's `messages.rs`—: RM2k's font has
Latin-1, the console's had printable ASCII, and the games in Spanish and
German lost most of their talk to it; Zounds' intro stopped on map 8. taro's
that day: unblock the whole game first. So first every such letter went
plain —the table is `plain` in `rm2k-snes-text`—, and then the font drew
Latin-1: the cartridge carries the letters its boxes use, after the
console's 96 glyphs. The compiler notes the letters of each command that go
plain as one `letter-plain` loss.

Common event 3, `Plain Letters`, in `src/db/commonevents.json`, shows a box
with Spanish, German, French and Danish letters, the guillemets, the
ellipsis and `Œ`. The case `plain-letters` calls it.

Seen red with the tools before the first change: the common event's page did
not compile, the call was skipped, and no box came up. And its golden moved
with the second: the letters it showed plain, drawn.
"""

import json
import os

from game import MESSAGE_SHOWN, Session, cartridge, golden

COMMON = 3
LETTERS = "… as ..., ø as o, Œ as OE"


def test_the_box_shows_each_letter_drawn_or_plain(core):
    sess = Session(core, case="plain-letters")
    sess.until("a message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 300)
    # A few ticks more, so the window has finished opening.
    for _ in range(30):
        sess.advance()
    golden("plain-letters", sess.image(), core)


def test_the_build_lists_the_letters_shown_plain():
    with open(os.path.join(cartridge().directory, "degradations.json")) as file:
        degradations = json.load(file)
    lost = [loss for loss in degradations["losses"]
            if loss["kind"] == "letter-plain" and loss.get("common") == COMMON]
    assert len(lost) == 1, lost
    assert lost[0]["name"] == "ShowMessage", lost
    assert lost[0]["text"].endswith(": " + LETTERS), lost
