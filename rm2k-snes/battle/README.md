# rm2k-snes-battle: an RPG Maker 2000 game's battle, as a cartridge carries it

    rm2k-snes-battle tables --data dump/ --request request.json --out build/battle/
    rm2k-snes-battle model --data dump/ --request request.json --out build/battle/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

A cartridge's battle is RM2k's, computed ahead of time into what the
console only reads. `tables` makes two tables:

* **experience and level per actor**: RM2k's experience curve —in floating
  point, which the console does not have— for every level, the starting
  experience and level, the level cap and the six parameter curves, in
  one slot per actor that can fight;
* **the random encounters of each map**: which troops come out where —the
  whole map or an area of it—, and RM2k's odds per step, turned into
  integers the console shifts and compares.

`model` answers the rest of what the battle carries, as data the caller
writes into its tables:

* **the model**: which skills the battle offers and to whom, what each
  enemy can do, which items go in its list, what a troop gives;
* **its text screen**: where each thing goes on the grid of cells the
  console writes the battle on, and the texts it writes there —the
  commands, the victory's lines, the names—, already cut to what fits.

And `simulate` **plays a battle**, turn by turn, with the same rules and
the same randomness as the console, for whoever compares a console's
battle against it; `lines` builds the victory's lines the same way.

The battle's pictures —the backdrops, the battlers, the animations— are
still made by the converter that calls this.

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
  replaced wrote for the same input (`tests/python.rs`). The model's game
  is bigger and lives in `tests/game/`, with the requests and their hashes
  (`tests/model.rs`).

## The request of `tables`

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

## What `tables` writes

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

## `model`

It is the converter's second call, after the event pages compiled: by then
it knows every troop the cartridge fights and every (actor, skill) pair
the compiler gave a slot.

    {"actors": [11, 12], "troops": [82, 97], "items": [1, 2],
     "skill_pairs": [[11, 131], [11, 146]], "item_name_width": 20}

* `actors`: the ones that can be in the party.
* `troops`: the ones the cartridge's battles ask for, in its order.
* `items`: the ones the cartridge knows.
* `skill_pairs`: every (actor, skill) the event compiler gave a slot, in
  the slots' order. They are the skills an actor can end up knowing, which
  are more than its learning table's.
* `item_name_width`: how much of an item's name the item screens write,
  which is theirs: the victory names what it found with it.
* `font` and `letter_spacing`, optional: the game's font, as the screens
  stage takes them. With them the answer says what that font leaves out.

It writes `model.json`: `layout`, the geometry and the model's constants
—see `layout`—; `enemies`, those of the troops, and `actions`, what each
can do, as `[rating, skill or null, effective]`; `skills`, the ones the
cartridge carries, and `taught`, the ones leveling up teaches; per pair,
the level its learning table teaches it at (`pair_levels`); per item,
whether the battle offers it (`item_battle`); per troop, its experience and
gold; and `texts`, what the battle writes, cut to its place. With the
font, also `cut`, the names a place cuts —actors, states, enemies,
skills, items and commands, each against its cells—; `pairs`, how many
pairs of tiles of the text layer the busiest skill list and item list can
ask for, with the widest texts the cartridge can put in them; and
`party_line`, `null`, or why the party's line —its HP and SP, which are
runs the console does not cut— does not fit with that font. The answer is
no if the victory does not fit in its window or an enemy carries more
actions than the console weighs.

## `simulate`

A battle and its steps:

    {"seed": null,
     "actors": [{"id": 11, "equipment": null, "level": null, "skills": null}],
     "troop": 82, "enemies": null, "pages": null, "switches": {},
     "steps": [{"start": null}, {"set": {"side": "enemies", "place": 0, "hp": 1}},
               {"turn": [[0, 0], [1, 0], [4, 150, 0], [3, 12, 1]]},
               {"escape_chance": 0}, {"flee": null}, {"enemy_action": 0}]}

The actors with their equipment, level and skills —each `null` for the
database's—; the enemies of a `troop`, or loose ones in `enemies`, each
with its `id`, `place` and whether it is `hidden`; the troop whose event
`pages` run, and the `switches` they look at. A turn carries a command per
living actor, in party order: `[0, enemy]` attack, `[1]` defend, `[2]`
escape, `[3, item, actor]` an item, `[4, skill, target]` a skill. Escaping
is the party's, as in RM2k: `flee` tries it, and when it fails the turn
that follows carries no commands, `{"turn": []}` —RM2k's
`ProcessSceneActionEscape`, which goes on with the enemies' actions only—.
`escape_chance` puts the chance the next `flee` rolls against, as a test
puts it in the console's `BA_ESCAPE`.

It writes `simulate.json`: what each step returned —the outcome of a turn,
whether fleeing worked, the action an enemy chose— and the battle as it
was left, every combatant with every number. It keeps nothing between
calls: whoever wants to look at a battle turn by turn sends it again with
one more step, and it comes out the same, because the randomness is the
battle's own.

## `lines` and `layout`

`lines` builds the victory's lines as the console does:

    {"item_name_width": 20,
     "lines": [["victory"], ["exp", 90], ["gold", 285], ["item", 257],
               ["level", 11, 21], ["skill", 148]]}

`layout` writes the battle screen's geometry, in cells, and the model's
constants —the seed, the commands, the outcomes—, by name.

## `experience`

What an event's `ChangeExp` or `ChangeLevel` leaves an actor with, from
where it stands, and the lines of its level-up message —none if it did not
go up—:

    {"changes": [{"actor": 15, "level": 3, "exp": 90, "skills": [147],
                  "exp_by": 500},
                 {"actor": 15, "level": 3, "exp": 90, "skills": [147],
                  "levels_by": -2}]}

Each change answers its `level`, `exp`, `skills` and `lines`. It is not the
battle's, but it is the same experience, and the same lines as the
victory's.

## Where the numbers come from

The experience curve, the level cap, the starting experience and level are
easyrpg-player's `Game_Actor` —`CalculateExp`, `MakeExpList`,
`GetNextExp`, `GetMaxLevel`, `SetLevel`—, and which troops a map's zones
hold is its `GetEncountersAt`: both in `rm2k-rules`. The encounter odds are its
`Game_Player::UpdateEncounterSteps`, whose eight rows of `pmod` are powers
of two, so `1 / steps` in 1/65536 is shifted instead of multiplied. The
source says which function each one is.

The model's formulas —damage, hit, critical, variance, turn order, escape,
what an enemy chooses— are easyrpg-player's too, and `simulate.rs` says
which function each is. What is not RM2k's is on purpose and declared
there: the randomness is a sixteen-bit xorshift with the battle's own seed,
the divisions are integer, and states, attributes and rows do not exist.

The encounters assume **the terrain changes nothing**: RM2k adds the
terrain's `encounter_rate` each step, and this assumes 100 everywhere,
which is what every terrain the hero steps on had in the game it was
measured against. It is an assumption of the engine, not a fact of the
format, and `RATE` says so.
