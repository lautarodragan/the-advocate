# rm2k-snes-screens: an RPG Maker 2000 game's screens, as a cartridge carries them

    rm2k-snes-screens convert --data dump/ --game-dir game/ --request request.json --out build/screens/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

Everything the console shows that is not a map or a battle scene, drawn
once when the cartridge is built:

* **the message window**: the empty window cut into tiles, the text area
  the cartridge rewrites, the font, and the glyphs precomposed for each of
  the four places a letter can land in a cell;
* **the title's menu**: the game's two options over the title picture, one
  tilemap per option chosen;
* **the save slots and the pause menu**, which share a tile bank: the text
  that does not depend on the save, the glyphs the cartridge composes names
  and numbers with, and each actor's face with its palette —with fewer
  colours when it has too many, and with another face's palette when there
  are none left—;
* **the text screens' font** —items, equipment, shop, the battle's text—:
  each letter in two cells, in four colours;
* **the windows behind the text screens**, with the System's frame and
  cursor, as the cartridge stores them: one tilemap per screen and only the
  cells a cursor changes;
* **End Game**, whose cursor is two palettes over one tilemap;
* **the texts the cartridge composes**, cut to what fits;
* **every message box of the game reflowed** for the console's window.

It is a stage of a converter, with the shape `rm2k-snes/battle/README.md`
describes in "One stage of a converter": it reads the game from a Ditto
dump itself —the terms, the actors, the items and the System's settings—,
and the System, the faces and the title from the game's folder; it gets in
a request what the cartridge decided, and writes a JSON.

## Two crates

* `rm2k-snes-text`: the letters —easyrpg-player's two 6x12 fonts—, a line
  of them drawn over the System as RM2k's `Font::Render` draws it, and a
  message box reflowed for a narrower window. It knows nothing about menus.
* `rm2k-snes-screens`: this one, every screen with those letters.

## The subcommands

`convert` is the one the converter calls, once per cartridge:

    {"slots": 4, "actors": [11, 12, 14], "items": [1, 2, 7],
     "bank_items": [1, 2], "title": true, "cgram_reserved": 9,
     "vram": {"slot_vram": 8192, "slot_map": 15360,
              "bg1_banks": [["WINDOW", 4096, 20480]]}}

What the cartridge decided: `slots`, how many save slots; `actors`, who can
be in the party —their faces and the letters of their names go in the
bank—; `items`, the items it knows, in its order, whose names and
descriptions go as text; `bank_items`, the ones whose medicines' names the
menu's bank carries the letters of, which is `items` if it is not there;
`title`, whether it has a title screen.

**What other domains answered, as data**: `cgram_reserved`, where the maps'
background starts in colour memory —the message window goes below—; and
`vram`, where the slot screen's tiles and tilemap go and each map layout's
BG1 bank. Every screen is opened over a map and closed back to it by
reloading that bank, so everything a screen writes has to fall inside the
bank of every layout: this checks it, and the answer is no when it does
not.

It writes `screens.json`: the pieces above, the geometry the screens were
drawn with —`layout`, by name, so the emission writes the same numbers and
keeps no copy of them—, and what the conversion has to say, in order.

`render` draws one screen as the console has to show it —the menu, the
item screen, the actor choice, the slot screen, equipment, the shop or End
Game—, built from the same blocks `convert` makes, with the game's state it
shows in the request. It is for whoever compares a capture against it.

`boxes` reflows every box of the dump's maps and common events, and of the
project's maps over them, for a window of `columns` by `lines`: the table
the event compiler reads its boxes through.

`layout` writes the geometry alone.

## Its tests

They build a small game and its System inside the test, and compare what
comes out against the hashes of what the Python that drew these screens
until 2026-09-30 answered for the same input: they need no game.
