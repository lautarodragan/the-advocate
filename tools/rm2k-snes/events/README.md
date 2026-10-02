# rm2k-snes-events: an RPG Maker 2000 game's event pages, as a cartridge's bytecode

    rm2k-snes-events scan    --data dump/ --request scan.json    --out build/events/
    rm2k-snes-events compile --data dump/ --request compile.json --out build/events/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

RM2k has about 130 event commands, and a page is a script of them. The
console runs a bytecode of its own, one opcode per thing it knows how to do
with every operand already resolved: an event's id is its index in the map's
table, a map is its index in the cartridge, a variable is its slot in RAM, a
text is its offset in the ROM's text block. This compiles one into the other.

The rule is a single one: **a page is emitted only if all its commands can
be run.** One the console does not model leaves the whole page out, and its
event does nothing: running half a script would leave the game in a state
that does not exist.

The opcodes are not declared here: they are the protocol's, `events.toml`,
which belongs to neither the compiler nor the interpreter. `src/opcodes.rs`
is generated from it by `protocol --rust` and committed.

## One stage of a converter, called twice

It has the shape of `rm2k-snes-battle` —see its README, "One stage of a
converter"—: it reads the game from a Ditto dump with Ditto's library, the
rules of the format are `rm2k-rules`' and the ones of RM2k's engine come
with the source they were taken from, what the dump does not say comes in a
request, and what it makes goes into `--out` as a JSON, `events.json`.

What is different is that the caller needs it twice. It needs to know which
pages compile, and what they send walking, **before** it builds each map's
sprite bank; and it can only compile for real **after**, because a
`TileSubstitution` is translated to the map's blocks, which are built with
the bank. So there are two calls, and each is the compiler run with a
different context:

* `scan`: the indices of the whole game —each variable's slot, each (actor,
  skill) pair's bit, the graphics an actor can be given, the equipment
  common events—; every page of every map of the cartridge, **each compiled
  on its own**, with its code —which pages compile is what decides who can
  lead the party—; and each map's pages the way the map will have them,
  compiled with a text block of the map's own and without songs —who walks,
  which graphics a route changes to—.
* `compile`: every page of the cartridge with everything, in the
  cartridge's order and through the same registries —the text block, the
  songs and effects with the audio package each map asks for, the troops—;
  the test pages; the debts; the troops' pages; the battle's audio; and the
  equipment common events. It runs twice: the first pass only gathers the
  boxes that go into the cartridge, and the text block is then written with
  a pair table chosen over them —DTE, a byte from 95 up standing for two
  letters; see `Pairs` in `messages.rs`—, which the answer carries next to
  the block.

The indices come from sweeping **every map of the game**, whether its pages
compile or not, and the troops' pages: a cheap superset, and a page that
starts compiling later shifts nobody's slot, so a game saved with one
cartridge loads in another.

## The request

Both calls read these:

    {"map_files": {"11": "path/Map0011.json"},
     "boxes": [{"from": ["KERSH", "a line too long"], "to": [["KERSH", "a line"], ["KERSH", "too long"]]}],
     "names": [[1, 7, 1, "Ghost~baked:1:3:4"]],
     "window": {"columns": 39, "lines": 4},
     "maps": [4, 1, 2],
     "test_commands": [{"code": 10110, "indent": 0, "string": "Hi", "parameters": []}],
     "extra_variables": [1000],
     "test_event_map": 4}

* `map_files`: maps read from another file than the dump's —a project's
  fork of one of the game's, or one the game does not have—.
* `boxes`: text boxes the project rebuilt for the console's window: the
  lines as the dump has them, and the boxes that go in their place, with
  the same indent. A box that is not here stays as it is. It applies to the
  maps and the common events, not to the troops, whose window is another.
* `names`: graphics the project calls by another name —`[map, event, page
  id, name]`—: how a translucent page, or one drawn apart from the hero,
  gets a graphic of its own. The compiler only reads it to know which events
  share a graphic, and so a palette: two of those flash together. `scan`
  does not need it.
* `window`: the message window's size, which is the runtime's; the boxes
  are trimmed to it.
* `maps`: the cartridge's maps, in its order: a teleport to one that is not
  here does not compile.
* `test_commands`: every test page's commands, one after the other. They
  name variables, skill pairs and graphics like any page, and their texts
  go first in the block, so their offsets depend on nothing else.
* `extra_variables`: variables no page names that need a slot anyway.
* `test_event_map`: the map the test pages boot in, which carries an event
  without pages at index 0 —so that they run before the game's— or null.

`compile` also reads:

    {"substitutions": {"4": [{"upper": false, "old": 5, "new": 6, "pairs": [[1, 2]]}]},
     "picture": {"name": "Pic", "number": 1, "x": 160, "y": 120},
     "counters": [{"common_event": 9, "variable": 48}],
     "sound_effects": {"per_map": [...], "route_effects_left_out": [...],
                       "troop_effects_in_package": [...]},
     "cases": [{"map": 4, "commands": [...]}],
     "test_graphics": {"4": [["Extra", 0]]},
     "messages_step": 4,
     "encounter_troops": [3, 1]}

* `substitutions`: per map, every `TileSubstitution` its pages can ask for
  —its own, the test pages' that run there, the common events'— with the
  `(old block, new block)` pairs it translates to, or null if it cannot be
  expressed. One the request does not resolve stops the compilation: it is
  the caller's bug. Which ones some page asked for comes back.
* `picture`: which `ShowPicture` took the cartridge's one place, or null.
  Whether a picture fits is decided converting it, which is not this.
* `counters`: common events the project declares as the display of a
  variable in two digit pictures. A `CallEvent` to one compiles to
  `OP_COUNTER` instead of its body, and so does a `ShowPicture` of a digit
  on one of its pictures; see `compile_counter`. Optional: none if left out.
* `sound_effects`: what the project decided by ear —an effect that plays
  with another sample on some map, route effects left out of a map's
  package, troop effects that go into the battle's—, as its project file
  writes it.
* `cases`: each test page and the map it runs in, compiled as event 0 of
  that map. What the caller puts in front —the switch a test page turns
  itself off with— comes in the commands. One that does not compile comes
  back null.
* `test_graphics`: graphics a map's table carries after its own.
* `messages_step`: how many bytes at a time `OP_MESSAGE`'s offset counts:
  each box starts at a multiple of it.
* `encounter_troops`: the random encounters' troops, which
  `rm2k-snes-battle` answers. They go after the ones the maps' battles ask
  for and before the test pages'.

## What comes out

`events.json`, with the indices —`variables`, `skills`, `associations`,
`party_common_events`— and `maps`, one entry per cartridge map, and:

* from `scan`, per map, `compiled` —`[event, page, code]` of every page
  that compiles on its own—, `pages` and `graphics`;
* from `compile`, per map, `pages`, `graphics` —the table the map's pages
  number against, before the test pages—, `debts` —the commands the
  automatic pages that compile accept without doing— and `substitutions`
  —which ones some page asked for—; and `cases`, `messages` —the text
  block, in hex—, `songs`, `troops`, `troop_pages` —their code and their
  messages, each distinct body once—, `battle_audio`,
  `party_common_events` with their code, and `commons` when there are
  shared common event bodies —see below—.

**The shared common event bodies** —`commons.rs`— are the automatic common
events, the ones the pages that run in the foreground call, and every one
those call, each compiled once without a map: `bodies`, `[number, code]` by
the index an `OP_CALL` names; `autostart`, `[switch, index]` of the
automatic ones; `depth`, the deepest chain of frames, which the ROM's call
stack has to hold; and `left_out`, what an automatic one reaches that does
not compile. A page calls a body instead of pasting it when the body
compiled with the page's map is the same as without it; a parallel page
always pastes.

A page's record is its trigger, its conditions —a variable one with its
slot—, its layer, frequency and speed, its code or null, the events its
code sends a route to —by index in the map's table, walking the bytecode—,
its own route if it can be walked, and whether it turns toward the hero. What it **draws**
is not here: that is the caller's, who knows the ChipSet and what it drew.

## Where the numbers come from

The command codes are liblcf's, and a test holds each one to the name
Ditto's schema gives it. What each command does is easyrpg-player's —the
`Game_Interpreter` function each one is, named in the comments—, and what
the console does instead, and why, is in the comment next to each case.
The limits measured on the game this was built for —how many items, how
many switches— go as constants with a comment that says so.

## Its tests

They need no game. `tests/game/` is a small one built for them, with the
two requests a caller would send for it, `tests/scan.json` and
`tests/compile.json`. `tests/python.json` is the SHA-256 of each part of
what the converter's Python compiler answered for them, which this
replaced on 2026-09-29 after both gave the same bytes on every page of
every cartridge of a whole game: **those hashes are not to be regenerated
to make a test pass**. `tests/escapes.json` holds the escape tail of a
text box to the copy `rm2k-snes-text` rebuilds boxes around.
