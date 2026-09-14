# Ditto

Reads the RPG Maker 2000 files —`.ldb`, `.lmu`, `.lmt`— and dumps them to
JSON, **and writes them back from the JSON**. It is called that because it does
one thing only: copy somebody else's shape.

    cargo run --release -- read  Map0001.lmu mapa1.json
    cargo run --release -- write mapa1.json  Map0001.lmu

## The only thing that makes it worth anything: the way back is byte for byte

Over a whole game —328 `.lmu`, the `RPG_RT.ldb` and the `RPG_RT.lmt`— reading,
dumping to JSON, writing back from the JSON and comparing against the original
gives **330 out of 330 identical**. That is what lets a game live in a version
control system as JSON, be opened with the real RPG Maker —or with EasyRPG's—,
saved, and come back, using the proprietary format as nothing but a transport.
An "almost" is no good: one byte too many breaks somebody else's game.

`cargo test` measures it:

    cargo test                                        # a sample of maps, one second
    cargo test --release -- --ignored --nocapture     # the whole corpus, with the number

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

Three things are generated, and all three come from the CSV and from no
judgement of ours: the structs and the enums, the default of every field, and
the codec —which field is which chunk, how it is encoded, and whether it is
emitted when it holds the default—.

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

## The format, and the four things that make the exact round trip hard

A file is a header —a length and a name— and a struct behind it. A struct is a
run of chunks `(id, length, bytes)` closed by an id 0. An array of structs is a
count and, per element, its id and its struct. Integers are in **BER**: seven
bits per byte, the high bit says it continues.

That much is mechanical. What costs is this:

**1. A field holding its default is not written.** Except for the ones
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

### Details that bite

* **`Int32` is BER, `Vector<Int32>` is not.** Inside a vector every integer is
  four raw bytes. Same for `Vector<UInt32>` and the `Rect`s.
* **`DBBitArray` is not a bitfield**: it is a whole byte per value. The one
  that *is* a bitfield is a `*_Flags` field, and there `flags.csv` gives the
  order of the bits —from the least significant one upwards— and the flags that
  only exist in 2003 **take no bit** in a 2000 file.
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
