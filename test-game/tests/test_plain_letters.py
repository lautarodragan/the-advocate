"""A text box with letters the console's font does not have: each one is
shown as its plain ASCII stand-in —`é` as `e`, `ß` as `ss`, `¿` as `?`,
`…` as `...`—, and the build lists them in `degradations.json`.

Until 2026-10-16 such a letter left the whole page out —`Messages::store`,
in the event compiler's `messages.rs`—: RM2k's font has Latin-1 and the
console's is printable ASCII, and the games in Spanish and German lost most
of their talk to it; Zounds' intro stopped on map 8. taro's that day:
unblock the whole game first. The table is `plain` in `rm2k-snes-text`;
the compiler notes the letters of each command as one `letter-plain` loss.

Common event 3, `Plain Letters`, in `src/db/commonevents.json`, shows a box
with Spanish, German, French and Danish letters, the guillemets and the
ellipsis. The case `plain-letters` calls it.

Seen red with the tools before the change: the common event's page did not
compile, the call was skipped, and no box came up.
"""

import json
import os

from game import MESSAGE_SHOWN, Session, cartridge, golden

COMMON = 3
LETTERS = ("¿ as ?, é as e, ¡ as !, ß as ss, ñ as n, … as ..., « as <<, "
           "Ç as C, » as >>, Æ as AE, ø as o, Œ as OE, Ü as U, ç as c, à as a")


def test_the_box_shows_each_letter_plain(core):
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
