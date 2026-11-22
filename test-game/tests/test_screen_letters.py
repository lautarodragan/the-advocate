"""The database's Latin-1 letters on the text screens the cartridge composes
at run time, and an actor's name with them in a box, `\\N[0]`.

Until 2026-11-22 the text screens —the menu, the items, the shop, the
battle's lists, the names— showed each letter outside ASCII as its plain
stand-in, `Zoë` as `Zoe`, while the message boxes drew them. Now the
screens draw the letters the database's texts use, with the glyphs of the
cartridge's one font: the boxes' first, then the ones only the screens
write. See the book's divergence "Letters the font does not have".

Actor 4 is Zoë Peña: the `ñ` is a box's letter too —common event 4, the
plain letters' box—, and the `ë` only the screens write. Item 2 is the
Poción Ácida, `ó` and `Á` only the screens', and its description has `¡`,
a box's, and `á`, the screens'. Enemy 1, the Avispón, an `ó`. Each case
puts Zoë alone in the party and gives her three potions:

* `screen-letters` says "\\N[0] is here.", and then the menu's items
  screen is opened. **The box is the test that goes red without
  `msg_name_letter`'s translation** —see `runtime/actor_names.s`—: the
  name reaches the box as the screens' text, a letter as its glyph, and
  the composer took it as a box's letter index: seen red without it, the
  box read "Zoó PeÁa is here.", each letter the glyph after its own.
* `screen-letters-shop` opens a shop that sells the potion and the Sword:
  its buy list.
* `screen-letters-battle` starts a battle against the Avispón: its item
  list, with the potion's description on the help line.

The goldens are what RPG Maker 2000 shows with the same database: the
letters with their accents.
"""

from rm2k_snes_harness import MESSAGE_SHOWN, Session, golden


def shown(sess):
    """Waits for the next box, whole and waiting for a button."""
    sess.until("a message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 300)
    for _ in range(30):
        sess.advance()


def test_a_name_in_a_box_and_the_items_screen(core):
    sess = Session(core, case="screen-letters")
    shown(sess)
    golden("screen-letters-name", sess.image(), core)
    sess.press("a")
    sess.until("the case over", sess.has_control, 300)
    sess.choose("b")
    sess.screen_up()
    golden("screen-letters-menu", sess.image(), core)
    sess.choose("a")                    # Items, the menu's first command
    sess.console.run(30)
    golden("screen-letters-items", sess.image(), core)


def test_the_shop(core):
    sess = Session(core, case="screen-letters-shop")
    sess.screen_up()
    sess.choose("a")                    # Buy
    sess.console.run(30)
    golden("screen-letters-shop", sess.image(), core)


def test_the_battle(core):
    sess = Session(core, case="screen-letters-battle")
    for _ in range(1200):
        if sess.byte("menu_open") and sess.byte("BA_MODE") == sess.symbol("BA_M_COMMAND"):
            break
        sess.console.run(1)
    else:
        raise AssertionError("the battle did not reach its commands")
    sess.console.run(30)
    for _ in range(5):
        sess.choose("up")
    for _ in range(sess.symbol("BA_COMMAND_USE")):
        sess.choose("down")
    assert sess.byte("BA_COMMAND") == sess.symbol("BA_COMMAND_USE")
    sess.choose("a")
    for _ in range(120):
        if sess.byte("BA_MODE") == sess.symbol("BA_M_ITEM"):
            break
        sess.console.run(1)
    else:
        raise AssertionError("the battle's item list did not open")
    sess.console.run(30)
    golden("screen-letters-battle-items", sess.image(), core)
