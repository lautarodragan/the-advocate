# rm2k-project

The library every tool of an `rm2k-snes` suite starts from: **which game is
being built, what it decided, and where the machine keeps things**. The
tools that use it compile it in.

Its one executable, `rm2k-snes-project`, is for whoever is not a tool: it
prints a project as the tools resolve it, in JSON —the `[paths]` resolved
against the file, the suite's own directories and the whole file—, so that
a game's tests, in whatever language, ask instead of reading the TOML
themselves. One reader of the file means one set of rules:

    rm2k-snes-project [--project <directory>]

## Which game: the project file

The tools do not know where any game lives: they find it, the way cargo finds
its `Cargo.toml`. A game declares itself with an `advocate.toml` at its root,
and a tool looks for one from the current directory upwards, or is told with
`--project <directory>`. Until 2026-10-20 the file was called
`rm2k-snes.toml`; that name is not read, and a directory that still has it
stops the search with an error that says to rename it:

```rust
let project = Project::locate(explicit.as_deref())?;
let name = project.string(&["rom", "name"])?;
let data = project.data()?;   // [paths] data, relative to the file
```

**A missing key is an error that names the key, never a default.** A default
in a tool would be one game's value, and another game that forgot to declare
it would be built with it without a warning. So `int`, `string`, `boolean`,
`list`, `ints`, `strings` and `table` fail with the file and the full key
—`missing key cartridges.release.start_map`—, or with what the key was
expected to be and what it is. TOML keeps booleans and integers apart, so a
`true` never passes for `1`.

**How the game is laid out inside is declared by its file**, in `[paths]`,
relative to it: the dump (`data`), what was decided (`patches`), what was
built (`build`) and the test cases (`cases`).

The keys of a table come back in the order the file writes them.

## Where the machine keeps things: `environment`

The original game, the RTP, the SoundFont, the replacements for the MSU-1
tracks, the cache, the test cartridges and where builds are delivered belong
to the machine and not to the project. **They arrive by flags**
—`--game-dir`, `--rtp-dir`, `--soundfont`…—, never by environment variables:

* `environment::arguments(&["game_dir", "cache"])` gives the flags to add to
  an executable's command line, with their help;
* `Environment::from_matches` reads them back, made absolute;
* `Environment::as_flags` passes them on to another tool, in a fixed order.

**A value nobody passed is an error, not a default**, except the cache and
the test cartridges, which have their place inside the project's `build`.

**The game and the RTP can be a `.zip`** of the directory. Nobody reads
inside it: `Environment::unpack(&project)`, right after `from_matches`,
unpacks it once into `zip/` in the cache —named by its content, see
`archive`— and from then on the value is that directory, in `as_flags` too.
A tool that skips `unpack` and gets a `.zip` gets an error from `game()` and
`rtp()`. `rm2k-snes-project --game-dir X --unpacked game_dir` prints the
directory, for whoever reads the game without being a tool.

## What a cached value depends on: `cache`

The converter keeps what it computes the same way on every build in a disk
cache, and **what changes —the code— goes into the key**. `cache::key` gives
exactly the key the converter gives for the same parts, so a value one side
wrote is found by the other; `cache::version_of` is the hash of the files a
value comes from. `NO_CACHE=1` turns the cache off, which is how a build is
checked to come out byte for byte the same with and without it.

## The suite's own files: `suite`

The runtime —the console-side engine— travels with the tools, not with any
game. A binary finds it through the source tree it was compiled from, which
cargo records at build time: an installed binary answers for **the checkout
it was installed from**, the way a symlink to a script does.

## Tests

    cargo test

They build their projects inside the test, so they need no game.
