"""A text box with escapes the console cannot show: they are dropped, the
box shows its text, and the build lists each one in `degradations.json`.

Until 2026-10-15 any escape but the tail —`\\|`, `\\^`—, the waits in the
middle, `\\c[n]` and `\\s[n]` left the whole page out: `escape_tail`, in the
text crate's `refit.rs`, refused the box. taro's that day: a game is played
before each escape is done, and what is dropped is said, so it is not lost
and forgotten. The event compiler notes each one as a
`message-escape-dropped` loss of its command.

Common event 2, `Escapes`, in `src/db/commonevents.json`, shows a box with
`\\c[2]`/`\\c[0]` (color), `\\$` (the gold window), `\\>`/`\\<` (instant
text), `\\_` (a half space) and `\\q`, a letter RPG_RT knows no escape for
and shows nothing. The case `escapes` calls it: a common event's losses are
listed, a test page's are not —they are the harness's—. Since 2026-10-20
the colour and the instant text are done —see `test_colours.py`— and only
the other three are dropped.

Seen red with the tools before the change: the common event's page did not
compile, the call was skipped, and no box came up.
"""

import json
import os

from game import MESSAGE_SHOWN, Session, cartridge, golden

COMMON = 2
DROPPED = ["\\$", "\\_", "\\q"]


def test_the_box_shows_its_text_without_the_escapes(core):
    sess = Session(core, case="escapes")
    # The box is typed: a few hundred ticks for three lines at speed 1.
    sess.until("a message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 600)
    # A few ticks more, so the window has finished opening.
    for _ in range(30):
        sess.advance()
    golden("escapes", sess.image(), core)


def test_the_build_lists_each_dropped_escape():
    with open(os.path.join(cartridge().directory, "degradations.json")) as file:
        degradations = json.load(file)
    lost = [loss for loss in degradations["losses"]
            if loss["kind"] == "message-escape-dropped" and loss.get("common") == COMMON]
    assert [loss["text"].split(" ")[0] for loss in lost] == DROPPED, lost
    assert all(loss["name"] == "ShowMessage" for loss in lost), lost
    assert degradations["counts"]["message-escape-dropped"] >= len(DROPPED)
