# Ditto

Reads the RPG Maker 2000 and 2003 files —`.ldb`, `.lmu`, `.lmt`— and dumps
them to JSON, **and writes them back from the JSON**. It is called that because
it does one thing only: copy somebody else's shape.

    cargo run --release -- read   Map0001.lmu map1.json
    cargo run --release -- write  map1.json   Map0001.lmu

    cargo run --release -- unpack ./game      ./exact ./resolved
    cargo run --release -- pack   ./exact     ./game-again

    cargo run --release -- schema schema.json

`read`/`write` do one file, which is what one wants in order to look at a single
map. `unpack`/`pack` do a whole game as **a tree of files**, which is what one
wants in order to keep it in a repository; that layout has [its own
section](#a-game-as-a-directory-and-not-one-big-json). `unpack` writes that tree
**twice, in one run**, in the two views of [the next
section](#two-views-of-the-same-document). `schema` writes out what the exact
dump does not carry and a reader of it needs: see
[below](#the-schema-is-published-as-data).

## Two views of the same document

The **exact dump** has the binary's own shape: a field holding its default is
left out —the format's own rule— and an enum travels as the name `enums.csv`
gives it. It is compact, it is the one that reads back, and it is the only one
`pack` accepts. Reading it takes the schema.

The **resolved view** is the same document with nothing left to know: **every
field written**, its default already filled in, and every enum as the number the
file stores. It is bigger —on the measured game, 19.4 MB against 30.9 MB— and it
takes no schema at all: a consumer indexes the field and gets the value. It
cannot be written back, and `pack` says so by name instead of quietly producing
a binary with every chunk in it, which would be a valid file nobody ever wrote.

**`unpack` writes both or neither**, which is why it takes two output
directories and not one. They are the same document said in two ways, and what
makes comparing them mean anything is that there is no way to have one from one
run and the other from another.

Both come out of the same `Serialize` impls and the same defaults —`src/lcf.rs`,
`as_resolved`— for the same reason: two serializers could say different things
about the same field.

## As a library: reading a dump with types

The resolved view needs no schema to be read, which is what it is for; but
a program in Rust that reads it by hand has to rebuild the model —which
field is which, of which type— and then there are two readers of the same
format, each with its own idea of it. So the library reads a dump **into
the schema's own types**, the same ones the binary is built from:

    let dump = ditto::dump::Dump::open(Path::new("data"))?;
    let db: Database = dump.database()?;
    let actors: Vec<Actor> = dump.section("actors")?;   // only that file
    let tree: TreeMap = dump.tree()?;
    let map: Map = dump.map(7)?;                         // layers included
    let other: Map = ditto::dump::read_map(Path::new("elsewhere/Map0007.json"))?;

**Either view reads into the same values.** The exact dump leaves a field
out and `#[serde(default)]` puts its default back; the resolved view writes
it. An enum reads from every shape the JSON holds it in —the name, the
number the resolved view writes, and `{"Other": n}`—: that is why the
generator writes its `Deserialize` instead of deriving it. And since a field
the JSON leaves out holds the format's default, a piece of a dump —a map a
caller patched and sends somewhere, a node of the tree— reads with these
types too.

`tests/library.rs` requires the two views of a game written in the test to
read into the same values, with no corpus; with one, `there_and_back`
requires the same of the whole game. `pack` reads through `Dump` too, so
the binary and a consumer read a dump with the same code.

## The only thing that makes it worth anything: the way back is byte for byte

Over a whole game —328 `.lmu`, the `RPG_RT.ldb` and the `RPG_RT.lmt`— reading,
dumping to JSON, writing back from the JSON and comparing against the original
gives **330 out of 330 identical**. Through the directory layout, where the
database is split into sections and the tile layers leave the JSON altogether,
it is **330 out of 330** as well. That is what lets a game live in a version
control system as JSON, be opened with the real RPG Maker —or with EasyRPG's—,
saved, and come back, using the proprietary format as nothing but a transport.
An "almost" is no good: one byte too many breaks somebody else's game.

`cargo test` measures it:

    cargo test                                             # a sample of maps, one second
    cargo test --release -- --include-ignored --nocapture  # the whole corpus, with the number

The short batch is the default so that `cargo test` stays something one runs
without thinking about it.

### The tests need a game, and the game is not in here

No RPG Maker game ships with this repository —they belong to their authors— so
the tests that measure the round trip take one from the environment:

    DITTO_CORPUS=/path/to/a/game cargo test

That directory is the one holding `RPG_RT.ldb`, `RPG_RT.lmt` and the `Map*.lmu`
files. Without it, those tests **skip with a message** instead of failing: a
missing corpus is not a defect of the code under test. The tests that need no
game —the defaults of the generated schema, for one— always run. `DITTO_ALL=1`
makes the sample test cover every map.

And there is a second test, because the round trip on its own is not enough: a
reader that understood **nothing** and kept every chunk raw would also give
byte for byte, and the JSON would be useless. So `no_chunk_goes_unnamed`
requires that not a single chunk survives unnamed in the dump.

### The corpus Ditto writes for itself

A fresh clone with no game still measures something: `tests/synthetic.rs`
builds its own files and needs nothing from the environment.

Half of it is **not a round trip**. A round trip only proves that the reader
and the writer agree with each other: if both misread the same field the same
way, the comparison comes out clean and says nothing. So those tests write the
bytes **out by hand** —a BER integer and the boundaries where it grows, a
chunk `(id, length, body)`, a whole map spelled byte by byte— and assert which
value each one stands for. A reader that invented its own format fails them.

The other half builds documents holding what a real game rarely does: the
extremes of a BER integer, text in the range where cp1252 departs from
Latin-1, empty vectors next to full ones, a field set to its default on
purpose, and a chunk the schema does not name. Those close through the binary
and through the JSON.

The two corpora answer different questions and neither replaces the other:
the synthetic one proves the implementation is consistent and covers what a
game does not exercise; a real game proves the format is the one RPG Maker
actually writes. A brand new project made with the editor is worth more here
than a finished game, because almost everything in it holds the factory
default, which is exactly what the omission rule is about.

## A game as a directory, and not one big JSON

A game written as a single JSON per binary file is unusable as a repository: the
database alone is 17 MB in one file, so a one-word change to a term lands in a
diff next to every enemy in the game. `unpack` writes a tree instead:

    ditto.json            the layout's version and view, and every file's header
    maps.json             the map tree: the `.lmt`
    maps/Map0001.json     one file per map, without its tile layers
    maps/Map0001.tiles    those layers, as a grid
    db/actors.json        the `.ldb`, one file per section (15 of them)
    db/database.json      what is left of the database: its `version`

`pack` builds `RPG_RT.ldb`, `RPG_RT.lmt` and every `.lmu` back from that tree,
and `tests/directory_dump.rs` requires the result to be the same 330 files byte
for byte. That is the test that says the layout lost nothing: everything needed
to write the binary back had to find a place in it.

**The `format`/`header`/`data` envelope is gone, and the header is not.** One
JSON on its own needs the envelope because nothing else says what the file is;
in a tree the place says it —`db/` is the database, `maps/Map0001.json` is a
map—. The header *string* is another matter: liblcf has an option to preserve
it precisely because there are games with a changed name, and assuming it would
give a different binary. So it lives in `ditto.json`, once per kind, with a
per-map override for the map that disagrees (normally there is none).

**The tile layers are a text grid and not JSON.** 100x100 numbers per layer are
what makes a map file unreadable, and in a diff they bury the event that
actually changed; one line per row puts a changed tile on its own line, at the
row and the column it is on the map. It is not for space —measured: the 837,270
tiles of the corpus are 5,123,812 bytes as `.tiles` against some 5,334,435
packed into the JSON, 4%—. `pack` takes the layers from the `.tiles` when there
is one and from the JSON when there is not, so a layer that cannot be laid out
as a `width * height` grid simply stays in the JSON.

**The database is split by shape, not by a list of names.** Every field of
`Database` that is an array or an object gets a file named after it; the scalars
stay together in `database.json`. A section liblcf adds tomorrow gets its own
file with no change here.

`unpack` empties a previous dump before writing —otherwise a `Map0400.json` left
over from an older one would put a map back into the game— and refuses to write
into a non-empty directory that has no `ditto.json`, which would be somebody
else's.

### The JSON is pretty-printed, with lists kept on their line

`serde_json`'s pretty printer puts one array element per line, and this format
is lists all the way down: the parameters of an event command, the ranks of a
state, the frames of an animation. So the printer here keeps a list of plain
values on one line while it fits in 96 columns, and does the same with a small
object that holds nothing but plain values —which is what an event command is,
and there are 65,596 of them in the battle events of the measured game alone—.
Objects that hold other objects always go one key per line: that nesting is the
shape of the data, and it is what a diff is read for.

Over that game it is the difference between a 29.5 MB dump and a 19.4 MB one.

## The names are not ours

The binary has no names in it: the format is *chunk-based* and every field is a
numeric index —an enemy's maximum HP is field `0x04` of `Enemy`—. The names,
the types and the defaults come from **liblcf**, which defines them in a set of
CSV tables (`generator/csv/`), and the structs are generated from there.

That is not fidelity —liblcf is reverse engineering too, done by EasyRPG—, it
is **compatibility and culture**: using the vocabulary the ecosystem already
uses saves decisions and makes this dump comparable with any other tool's.

## The generated code is committed

`src/schema/` comes out of liblcf's tables, **but it is in git and it is this
project's source of truth**. Regenerating is an explicit action:

    cargo xtask generate --liblcf /path/to/liblcf

What that produces is a diff that gets read and reviewed, not a hidden build
step. If liblcf renames a field, the commit says exactly that: a name changing
in the corresponding struct.

Conceptually the CSV is a **dependency** of Ditto: bumping its version is a
change that gets reviewed like any other.

Four things are generated, and all four come from the CSV and from no
judgement of ours: the structs and the enums, the default of every field, the
codec —which field is which chunk, how it is encoded, and whether it is
emitted when it holds the default— and the description `schema` prints.

**A text default in the CSV is a C++ literal, quotes and all.** `Music,name`
holds `"(OFF)"` and the name is the five characters inside it. The generator
used to quote it a second time, so the default was seven characters long: a
value no file can ever hold, which means the field was never recognised as
holding its default and the name was written into every JSON. The round trip
never noticed, because `Music::name` and `Sound::name` are the only two fields
this hit and both are `PersistIfDefault`, so the binary carries them either
way. It is exactly the kind of wrong default this project exists to remove, and
it cost 61 KB of a 19.5 MB dump.

### The schema is published as data

The exact dump **is not self-describing**, and that is the point: a field
holding its default is left out, and an enum travels as a name. So a reader that
is not Ditto cannot know what an absent `max_hp` holds, nor what number
`"auto_start"` is. It needs the schema, and until it has it, it is reading the
file wrong. (A reader that wants none of this reads the resolved view instead,
and that is what it is for.)

    cargo run --release -- schema schema.json

writes it out: every struct, and per field its chunk, its default as JSON,
the enum its values are names of, whether the binary stores it even when it
holds the default, and the struct it nests; plus every enum table. The same
`cargo xtask generate` run emits both this and the structs above, from the
same CSV rows, so the two cannot drift apart.

The alternative —and what a consumer of this project actually did until
2026-09-20— is to read `src/schema/mod.rs` with regular expressions and pull
the defaults out of the Rust. It works until it does not: a default written as
an expression (`9 * 256`) comes out as its first number.

### The default goes next to the field, written once

    pub max_hp: i32 = 10,

This is not about looks. The default is what fills a field in when reading
**and** what decides to omit it when writing: they have to be the same thing or
the round trip stops being byte for byte. Written twice —as it used to be: a
`/// default: 10` comment and an `impl Default` at the end of the struct— the
two can drift apart with nothing warning about it. The `schema_struct!` macro
(`src/lcf.rs`, 40 lines, no dependencies) builds the `Default` from there, and
the struct's `#[serde(default)]` uses it for the JSON. It removed 61
`impl Default` blocks and 1,889 lines of generated code.

The `= <value>` is **mandatory on every field**, including the ones
`fields.csv` declares no default for: if it were optional, a field without a
default would fall back to the zero of its type through the back door, which is
the bug that gave rise to Ditto. Being part of the macro's grammar, forgetting
it is a compile error.

And that is why **neither** per-field `#[serde(default)]` nor
`serde-inline-default` is used. The first one fills in with the zero of the
*type* and reintroduces the bug. The second one —evaluated: 1.0.2 on crates.io,
no new deps, syn 3 which is already here— only emits
`#[serde(default = "fn")]`: it **does not implement `std::default::Default`**,
which is exactly what the codec needs in order to decide omission and what
`trait Chunked: Default` asks for. So it would remove no `impl Default` at all:
it would leave the default written twice all the same, with a proc-macro
dependency on top.

#### And the same default decides what the JSON leaves out

`Serialize` is **not derived**: `schema_struct!` writes it, and it leaves out
every field that equals `Self::default()` —the very value the codec compares
against when it decides to omit a chunk—. The binary's rule and the JSON's are
then the same rule, and reading costs nothing because `#[serde(default)]` puts
the field back. Nothing is lost by it: the round trip is measured through the
JSON, and it stays at 330 of 330.

It is written out by hand rather than with `#[serde(skip_serializing_if = "…")]`
because that attribute takes the *path of a function*, and the default here is
an arbitrary expression: one function per field would mean building an
identifier out of the struct's name and the field's, which `macro_rules!` cannot
do. Comparing against `Self::default()` needs no name at all.

One trap, and it cost the first version two files: `stringify!` on a raw
identifier keeps the `r#`. The field liblcf calls `type` is `r#type` in Rust and
went into the JSON as `"r#type"`, which the derived `Deserialize` —which does
strip it— did not find, so it came back holding its default: `Skill` 71 read
back as `Normal` instead of `Teleport`. `json_name` strips it.

## The format, and the four things that make the exact round trip hard

A file is a header —a length and a name— and a struct behind it. A struct is a
run of chunks `(id, length, bytes)` closed by an id 0. An array of structs is a
count and, per element, its id and its struct. Integers are in **BER**: seven
bits per byte, the high bit says it continues.

That much is mechanical. What costs is this:

**1. A field holding its default is not written.** The JSON does the same, and
for the same reason it can: `Serialize` is written by `schema_struct!` and
leaves out every field that holds its default, and `#[serde(default)]` puts it
back on the way in. In this format that is most of them —over the corpus the
`.ldb` goes from 25,675,888 bytes to 17,569,229 as a single JSON— and it costs
nothing to read back.
 Except for the ones
`fields.csv` marks with `PersistIfDefault`, which are always written —even with
length 0—. So reading and writing are not symmetric by construction: they are
symmetric because the default that fills a field in when reading is the same
one that decides to omit it when writing, and both come from the same table.
That is the whole trick, and it is why the default has to come from the CSV and
not from anybody's judgement.

#### The limit of the omission rule, measured

The rule belongs to **whoever writes**, not to the format, so a file made by
another tool could store a field with its default value instead of omitting it.
Measured over a map (`tests/omission.rs`): adding by hand the `0x33` chunk
—`generator_surround`, whose default is `True`— with the value `True`, 43,958
bytes go in and 43,955 come out. **Exactly 3 bytes are lost** —the id, the
length and the body of the chunk—, and what comes out is the original file
unchanged. The same goes for any other one: it is always that chunk's bytes.

Now, the two writers that matter do the same thing Ditto does:

* **RPG Maker 2000** itself: over the 328 maps of the measured game there are
  2,363 top-level chunks present out of 10,824 possible, that is, it **omitted
  8,461 times**. With that count, 330 files coming back byte for byte stops
  being luck: it is the proof that the editor follows the same rule.
* **EasyRPG**: `Struct<S>::WriteLcf` in liblcf's `reader_struct_impl.h` skips
  the field with `if (!field->isPresentIfDefault(...) && field->IsDefault(...))`,
  which is literally what the generated codec here does.

So the risk exists but neither of the two tools this was built for triggers it.
If a third one ever does, the cheap way out is to **remember the anomalous
chunks, without touching the type of the fields**: in `read_struct`, compare the
ids that came in the file against the ones `write_chunks` would emit again, and
keep the ones that would be lost in the `unknown` list that already exists
—`dump` reinserts them ordered by id—. That is some 15 lines in `lcf.rs`, zero
changes in the generator and zero noise in the JSON of a game written by the
editor (the list stays empty in all 330 files); the cost is one extra
serialization per struct when reading. The expensive way would be `Option<T>`
on the fields, which would move the default out of the schema and into every
consumer, which is where it is taken from.

**2. The length of some vectors lives in its own chunk.** `fields.csv` marks
those with a `t` and gives them a separate index, always the one before the
data's. There are two variants and the CSV tells them apart by type:
`Count<...>` stores the **number of elements** and the rest store the **bytes**.
Ditto recomputes them when writing instead of keeping them in the JSON, which
is what liblcf does, and over the measured game that gives the same number in
all 330 files.

**3. Six structs are not chunk-based.** `Parameters`, `Equipment`, `Rect`,
`EventCommand`, `MoveCommand` and `TreeMap` are positional inside their chunk:
the CSV declares their fields but not their indices, because they have none.
liblcf resolves them by hand and so does this (`src/raw.rs`). The two with a
shape of their own:

* the command list of an event does **not** store how many there are: it ends
  with four zero bytes;
* a movement route is read until the chunk runs out, and how many parameters
  each command carries depends on its code —only four of the 35 carry any—.

**4. `Database` and `Save` do not carry the trailing 0.** liblcf warns that
giving them one breaks RPG_RT's parser. Every other struct does carry it.

**5. RPG Maker 2003 is the same format with a few more chunks, and it is
told apart by one field.** `System.ldb_id` is 2003 in a 2003 database, which
is how liblcf and RPG_RT know (`GetEngineVersion`). The 2003-only fields
—`fields.csv` marks them `Is2k3`: the classes, the battle commands, the
battler animations, the second timer of an event page, the turn and command
conditions of a troop page— are read whenever their chunk is there, in any
file. What the version changes is on the way **back**, and it is all in
`Writer::is2k3` (`src/lcf.rs`):

* a `*_Flags` field packs the 2003 bits after the 2000 ones, so a troop page
  condition is 1 byte in 2000 and 2 in 2003; the width is the version's, the
  positions never move;
* a 2003-only field of the database is never written into a 2000 file, and
  the ones marked `PersistIfDefault` are always written into a 2003 one;
* three of `Actor`'s defaults change —`final_level` 50 → 99, `exp_base` and
  `exp_inflation` 30 → 300—, and the default is what decides which chunks are
  omitted, so the version is looked up **before** the actors are decoded;
* `Database.version` is always present in a 2003 file, empty when it is 0.

A map or a tree has none of those cases —no flag field of theirs changes
width, no persisting 2003 field, no versioned default— so they are read and
written without knowing the version. Over a 2003 game of 190 files the round
trip is 190 of 190; the 2000 corpus and its exact dump do not change by a
byte. Two things liblcf does are **not** done, both measured against a game
saved by RPG Maker 2003 1.08: it leaves `Terms` 0x01 and 0x03 out of a 2003
file when empty —that file has them— and it persists `Terms` 0x26 and 0x27
—that file does not have them—; `NOT_PERSISTED` in the generator says where
to look if a game saved by a later 2003 comes back four bytes off.

### Details that bite

* **`Int32` is BER, `Vector<Int32>` is not.** Inside a vector every integer is
  four raw bytes. Same for `Vector<UInt32>` and the `Rect`s.
* **`DBBitArray` is not a bitfield**: it is a whole byte per value. The one
  that *is* a bitfield is a `*_Flags` field, and there `flags.csv` gives the
  order of the bits —from the least significant one upwards— and the flags that
  only exist in 2003 come **after** the 2000 ones and **take no bit** in a
  2000 file (point 5 above).
* **Text is cp1252**, with the five bytes the table leaves undefined (0x81,
  0x8D, 0x8F, 0x90, 0x9D) mapped to their C1 control, so the table is a
  bijection and no byte is lost. A game may carry messages in another encoding
  —Shift-JIS, for instance— that its author never touched: in the JSON they
  come out as odd characters and go back to the binary identical. Decoding them
  properly would mean guessing the encoding field by field and would cost the
  exact round trip, which is the only thing that makes this useful.
* **The header is kept in the JSON** instead of being taken for granted: liblcf
  has an option to preserve it precisely because there are games with a changed
  name.
* **Enums have an `Other(n)`.** A value `enums.csv` does not name is stored as
  a number and comes back the same, instead of falling to the default and being
  lost.
* **Every struct has an `unknown` list** where any chunk the schema does not
  name goes, so that it returns to the file in its place. Over the measured
  game it is empty in all 330 files, and there is a test that requires it.

## What is missing

* **`.lsd`** —the save files—. The structs are generated; the codec is not. It
  is not in the corpus the round trip is measured against, and without that
  there would be nothing to check it with.
* **The RPG Maker 2003 fields.** The generator skips them wholesale: Ditto
  targets 2000. A 2003 file read with Ditto would keep those chunks in
  `unknown` and come back identical, but they would not be visible in the JSON.
