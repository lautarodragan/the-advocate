# rm2k-snes-battle: an RPG Maker 2000 game's battle, as a cartridge's tables

    rm2k-snes-battle tables --data dump/ --request request.json --out build/battle/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

A cartridge's battle is RM2k's, computed ahead of time into tables the
console only reads. Today this makes two of them:

* **experience and level per actor**: RM2k's experience curve —in floating
  point, which the console does not have— for every level, the starting
  experience and level, the level cap and the six parameter curves, in
  one slot per actor that can fight;
* **the random encounters of each map**: which troops come out where —the
  whole map or an area of it—, and RM2k's odds per step, turned into
  integers the console shifts and compares.

The rest of the battle is still made by the converter that calls this; it
comes here as it moves.

## One stage of a converter

This is one domain of a game converter that is moving to Rust a stage at a
time. The converter still orchestrates, and calls each stage by the PATH as
a separate program. Every stage has the same shape, and this crate was the
first to be written to it:

* **It reads the game itself**, from a Ditto dump —`--data`—, **with
  Ditto's library**: `ditto::dump::Dump` and the schema's types, which are
  liblcf's names. It keeps no model of the format and no reader of its
  own, and it reads only the sections it uses —here `actors` and the
  tree—. A field the dump leaves out holds the format's default, which is
  what Ditto says an absent field means.
* **The rules of RPG Maker are `rm2k-rules`'**, not the stage's: here the
  experience curve and which zones a map's encounters come from. What the
  stage keeps is what belongs to the console: how the tables are laid
  out and what fits.
* **What the game does not say comes in a request**: a JSON the caller
  writes, with what the cartridge decided —here, which actors fight and
  which maps it carries, with their sizes— and whatever the project changed
  on top of the dump —here, tree nodes of maps the game does not have—. The
  request carries decisions and patches, never data the dump already has.
* **Logic of another domain comes as input, not as code.** Which actors
  can fight is the party's business, and arrives as a list; which troops
  the cartridge carries is the troops' business, and goes back as a list
  for the caller to hand over. A constant of the engine comes along, with a
  comment that says where it was measured.
* **What it writes is pieces of the `.inc`**, text for ca65, one file per
  piece, which the caller puts where they go —`--out`—; **and a JSON** with
  what the rest of the conversion needs to know about them —`battle.json`—.
  Nothing in it knows where a cartridge is built.
* **Two exit codes**: `1` when the answer is no —it does not fit, the dump
  is broken—, `2` when the call is wrong. The message goes to standard
  error.
* **Its tests need no game**: a small one is built inside the test, and
  what comes out is compared against the hashes of what the Python it
  replaced wrote for the same input (`tests/python.rs`).

## The request

    {"party": [1, 3, 8],
     "maps": [{"id": 4, "width": 40, "height": 30}, ...],
     "encounter_steps": null,
     "tree_nodes": []}

* `party`: the actors that can fight, by RM2k number. Only they gain
  experience, so only they get a slot: the save grows by four bytes per
  actor that fights, not per actor in the database.
* `maps`: the cartridge's maps, in its order, with their size in cells.
* `encounter_steps`: `null`, or the steps every map gets instead of its
  own. It is for test cartridges: an encounter every hundred steps is what
  a player wants and not what a test does.
* `tree_nodes`: nodes of `maps.json`, in the dump's shape, over the dump's.

## What comes out

Into `--out`:

* `experience.inc`: `EXP_K`, `EXP_LEVEL_MAX` and the tables `actor_exp_k`,
  `exp_initial`, `exp_level_max`, `exp_curve`, `exp_table`, `level_row` and
  `level_params`, in `RODATA`, which is where it leaves the segment.
* `encounters.inc`: `enc_map`, `enc_base`, `enc_threshold_n`,
  `enc_zone_init`, `enc_zone_n`, the four sides of each zone, and
  `enc_troop_init`, `enc_troop_n` and `enc_troop`. It opens no segment: it
  goes wherever it is included, outside bank 0.
* `battle.json`: the experience slots —which actor each save slot belongs
  to, `null` for one nobody owns—; per map, its encounter record or 255;
  how many records and zones; and the troops the encounters name, in order,
  which the cartridge has to carry.

Every table has a `.block` in front: the ROM reads them with
`lda f:table, x`, and one split across two banks would read its second half
from the next.

## Where the numbers come from

The experience curve, the level cap, the starting experience and level are
easyrpg-player's `Game_Actor` —`CalculateExp`, `MakeExpList`,
`GetNextExp`, `GetMaxLevel`, `SetLevel`—, and which troops a map's zones
hold is its `GetEncountersAt`: both in `rm2k-rules`. The encounter odds are its
`Game_Player::UpdateEncounterSteps`, whose eight rows of `pmod` are powers
of two, so `1 / steps` in 1/65536 is shifted instead of multiplied. The
source says which function each one is.

The encounters assume **the terrain changes nothing**: RM2k adds the
terrain's `encounter_rate` each step, and this assumes 100 everywhere,
which is what every terrain the hero steps on had in the game it was
measured against. It is an assumption of the engine, not a fact of the
format, and `RATE` says so.
