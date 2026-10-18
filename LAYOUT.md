# The layout

Everything that runs outside the console: what reads the RPG Maker game, what
converts it, what builds the ROM, and what runs it in the tests. Nothing
loose: each thing lives in the folder of its responsibility.

## No Python but the tests

The converter is Rust since 2026-10-02 —`rm2k-snes/convert/`, below—, and
so is everything it runs. The only Python left is `tests/`, which looks at
this tree: see `tests/README.md`; and the test game's tests, below.

What the game's tests read of their game —a reader of the dump, the models
they predict the console with, the clients of the stages they ask— went to
their harness the same day: it is theirs. And on 2026-10-02 the game itself,
A Blurred Line, went to its own repo, with its tests and their harness, and
the libretro driver they run the ROM with, `emulator/`, went with them. What
they ask the tools about their project —its paths, the suite's, its
settings— they ask `rm2k-snes-project`, below, which answers with the same
library every tool reads the project file with: until that day they read
it through a second reader in Python, `common/`. What stayed here names the
game only in comments —limits measured against it, the case that explained
a rule—: a test uses invented names and a fixture invented content, and
`tests/test_no_game_names.py` fails if anything else does.

And the Rust projects, which are not layers of the port but separate tools,
in English and without a single mention of this game (see AGENTS.md). They
have layers of their own, one folder each:

    snes/        the console's formats, knowing nothing of RPG Maker
      adeleine/  Adeleine: which colors a picture loses and how the ones
                 left are grouped into palettes
      gunter/    Gunter: BRR codec and SoundFont reader
      goombario/ Goombario: static checks for 65816 code built with ca65
                 and ld65, for what assembles fine and is wrong
      voodoo/    Voodoo: from an image to tiles, palettes and tilemap
      lz2/       Nintendo's LC_LZ2, with an optimal parser

    rm2k/        RPG Maker 2000's, knowing nothing of the console
      ditto/     reads and writes its formats; and as a library, the one
                 place in Rust that reads a dump, with the schema's types
      rules/     `rm2k-rules`, the library of what the format means:
                 passability, which layer covers which, the page a new
                 game starts on and what it draws, the experience curve,
                 what a map inherits from the tree. Its tests hold it to the
                 answers the converter's Python gave, in `tests/python.json`
      sketch/    `rm2k-sketch`: a map's tile layers drawn as text —a grid of
                 characters and a legend of the tiles each one stands for—
                 made into the `.tiles` of a dump; the test game's maps are
                 written that way
      rm2k-render/  a map's tile layers, its CharSets, what its battles are
                 drawn with —animation cells, backdrops, enemies—, and the
                 faces, windows and pictures of the screens, as pictures

    rm2k-snes/   what joins the two: an RPG Maker game made into a cartridge
      project/   `rm2k-project`, the library: which game, its settings, the
                 machine's flags and the disk cache's key; and
                 `rm2k-snes-project`, which prints all that in JSON for
                 whoever is not a tool
      bytecode/  `rm2k-snes-bytecode`, the library that declares the two
                 bytecodes a cartridge reads —the events one and the music
                 stream—, once: the Rust side takes its constants with a
                 `use`, and `rm2k-snes-assemble` writes the 65816 side's
                 equates at every build
      cartridge/ `rm2k-snes-cartridges`, `rm2k-snes-assemble` and
                 `rm2k-snes-space`: which cartridges there are and building
                 them, the bank packing, ca65 + ld65, and the space left
      patches/   `rm2k-snes-patches`: what the converter decided to lose
                 —a map's colors, an animation's size, a battler's
                 palette—, written as TOML next to each ROM, copied to the
                 project and checked against every cartridge; the
                 converter hands it the decisions in a request
      rm2k-snes-audio/  a game's music for the SPC700: the shared sample
                 bank, a stream per song, an audio package per map, and
                 the `.msu` with the data the MSU-1 serves; the converter
                 runs it as a stage, `cartridge`, and it uses `gunter` as
                 a library
      battle/    `rm2k-snes-battle`: the battle's tables —experience and
                 level per actor, each map's random encounters—, its model
                 and text screen, and the battle played for the tests; the
                 converter runs it as a stage, and its README says what
                 shape a stage has
      events/    `rm2k-snes-events`: the event compiler —a game's event
                 pages to the bytecode the ROM runs—; the converter calls
                 it twice
      wally/     Wally, `wally`: a whole map —its layers, the events baked
                 into them, its objects, its blocks—; the converter runs it
                 once per map. Its two halves are modules that do not know
                 each other: `background`, the two background layers in the
                 lower half of colour memory and the 16x16 blocks, and
                 `sprites`, the characters as objects —the palette split,
                 the VRAM bank and the pose bank— and the extras at the end
                 of the bank
      text/      `rm2k-snes-text`, a library: easyrpg-player's fonts, a line
                 of text drawn over the System, and a message box reflowed
                 for a narrower window
      screens/   `rm2k-snes-screens`: the screens —the message window and
                 its font, the title's menu, the save slots and the pause
                 menu, the text screens with their windows, End Game—, the
                 geometry they are drawn with, and every message box
                 reflowed; the converter runs it once per cartridge,
                 and the game's tests ask it
                 for the screens they compare against
      images/    `rm2k-snes-images`: the pictures —the title and the Game
                 Over, the picture of a `ShowPicture`, the battle's
                 backdrops, battlers and animations—, scaled with the
                 `image` crate, toned and brought down to their palettes
                 with Adeleine; the converter runs it
      mapdata/   `rm2k-snes-mapdata`: the emission —the cartridge's data
                 `.inc`, written from what every other stage answered—,
                 the LZ2 streams of what the console decompresses, and the
                 VRAM layouts, which it publishes for the maps and the
                 screens; the converter runs it, and reads the layouts
                 from it as a library
      convert/   `rm2k-snes-convert`, the converter: it asks each stage
                 above, in order, what the cartridge needs and hands each
                 what the others answered; what it decides itself is what
                 joins them —which maps and test pages, who can lead the
                 party, which items, pictures, backdrops and battlers go
                 in, the checks of the compiled pages—. It also answers
                 the game's tests how it asks: `scan`, `compile`,
                 `leaders`, `map-context`, `boxes`

`rm2k-snes/` may depend on the other two; `snes/` and `rm2k/` on nothing
outside themselves —not on each other, and not on `rm2k-snes/`—. So either
can go on its own, to a game that is not for the console or a console game
that is not from RPG Maker. `tests/test_layers.py` enforces it, from `cargo
metadata`; and since a crate can also know the layer above without
depending on it, by reading its files, it also fails if anything in
`snes/` or `rm2k/` names `rm2k-snes.toml`, the project file.

They are one Cargo workspace, `Cargo.toml` here: one `Cargo.lock` and one
`target/`, so what they share is compiled once and at one version. The
build profiles are the workspace's too, because Cargo ignores a member's;
`ditto` keeps optimizing for size there. They are still
separate projects, installed and tested one by one:

    just install lz2    one, with `cargo install --locked
                                          --path`, from the workspace's lock
    just crate-test lz2 one project's tests
    just rust-test      all of them, `cargo test --workspace`

They are used from the PATH: nothing here builds them or looks for them in
`target/`.

## The test game

    test-game/   a game of our own, written as text, with free assets: where
                 the engine's ROM tests are going to live instead of in A
                 Blurred Line. Its `README.md` says what is in it, how it is
                 built and how it is tested

It is a project like a port's —its `rm2k-snes.toml`, its `justfile`—, and
it builds with the installed tools, like any game. Its tests run the
cartridge in an emulator, so they are not in `tests/` and `just test` does
not run them: `just test-game` does.

## The ones that run

`just install` installs the Rust binaries, and a game's `justfile` calls
them by name and does not know where they are. Until 2026-10-02 there were
Python scripts too, installed as symlinks next to them: the last ones were
`abl-entregar`, which went to A Blurred Line's repo with the game, and
`rm2k-snes-python-path`, which told a game's tests where to import
`common/` and `emulator/` from, and went with them.

The binaries are `rm2k-snes-convert`, from
`rm2k-snes/convert/`; `rm2k-snes-cartridges`,
`rm2k-snes-assemble` and `rm2k-snes-space`, from `rm2k-snes/cartridge/`, which find
the runtime through the checkout they were installed from; and
`rm2k-snes-msu` and `rm2k-snes-volume-ceilings`, from
`rm2k-snes/rm2k-snes-audio/`; `rm2k-snes-battle`, from
`rm2k-snes/battle/`; `rm2k-snes-events`, from `rm2k-snes/events/`;
`wally`, from `rm2k-snes/wally/`; `rm2k-snes-mapdata`, from
`rm2k-snes/mapdata/`; `rm2k-snes-patches`, from
`rm2k-snes/patches/`; and `rm2k-snes-project`, from `rm2k-snes/project/`,
which prints for a game's tests what the tools know about their project.

The reason for the names is in `justfile`. **Where everything is** is
answered by `rm2k-project`, the library in `rm2k-snes/project/`: what
belongs to the suite —the root, the runtime— from the checkout it was built
from; what belongs to the game, from its project file: see "How they find
the game".

A worktree that modifies the tools uses its own with `just -f
justfile install-local <destination>`, which builds a `bin/` of its
own wherever whoever will use it says: the game's `justfile` looks for its
own in a directory of its own, and this one, in `.local-tools/`.
Each puts it first on the PATH of its recipes: see the recipe, and
"Sub-agents" in AGENTS.md.

## What the game decides: the project file

**What belongs to a game is not written in the tools**: which maps and which
cases each cartridge carries, what the ROM is called, the title in its
header and the signatures of its save files, which sound effects go whole,
which songs go separately, which CharSet weighs most when splitting
palettes. The game declares it at its root, in `rm2k-snes.toml`, and it is
read by one reader, `rm2k-project`: `project.int(&["maps", "below"])`.
Whoever is not a tool asks `rm2k-snes-project` instead of reading it.

* **A missing key is an error**, with its name, and not a default value: a
  default in a tool would be ABL's value, and another game would be built
  with it without a warning. The library's tests enforce it, and on
  ABL's side `test_perillas_repetidas.py`, which fails if a `.py` here
  —since 2026-10-02 only `tests/`— writes a value from the file again.
* **What the runtime needs** —the title, the SRAM signature— reaches it as a
  `.define` in the `mapdata.inc` the converter emits: the runtime does not
  read TOML.
* **The keys are in English**, because they are the tools' interface; the
  comments, in the game's language.
* **What does not go there**: where the game is on the machine —that belongs
  to the environment, and arrives by flags: see below— and the engine limits
  that were measured on ABL, which stay in the code with a comment that says
  so.

## How they find the game

**The tools do not know where any game lives: they find it**, the way cargo
finds its `Cargo.toml`. They look for `rm2k-snes.toml` from the current
directory upwards, or receive it through `--project <directory>`; if they do
not find it, they stop and say where they searched from.

**How the game is laid out inside is declared by its file**, in `[paths]`,
relative to it: the dump (`data`), what was decided (`patches`), what was
built (`build`) and the suite's cases (`cases`). What goes inside —`manual/`
and `auto/` in the decided part, one directory per cartridge in the built
part— is the shape the tools give it. What only the game's tests read —their
goldens, what they leave to look at— does not go there: they know it by
their location.

**What belongs to the machine arrives by flags**: `--game-dir`, `--rtp-dir`,
`--soundfont`, `--replacements` (the MSU-1 tracks that come from an audio file
and not from the MIDI), `--cache`, `--test-cartridges` and `--shared`, where
a game delivers its builds. Each executable adds the ones it uses with
`environment::arguments` and reads them back with `Environment`, both in
`rm2k-project`. **None has a default value**, except the cache and the test
cartridges, which have their place in the project's `build`: a machine's
value belongs to the caller. A Blurred Line's `justfile`, in its repo,
translates its variables into flags. That nothing here reads one of its
`ABL_*` variables is part of what `tests/test_no_game_names.py` checks.

## `justfile`

The tools' recipes —running their tests, installing— live in `justfile`,
at the root, and A Blurred Line's in its own repo. They are run with
`just <recipe>` and run standing in the root. Until 2026-10-02 a root
`justfile` imported ABL's and this one lived in `tools/`; until 2026-10-10
the tools themselves did, and it was `just -f tools/justfile <recipe>`.

## The bsnes patch

The patch for bsnes-libretro that exposes the WRAM, and how to build it,
went with the libretro driver to A Blurred Line's repo on 2026-10-02: see
`tests/harness/emulator/README.md` there.

A copy came back on 2026-10-18, next to the test game's copy of the driver,
`test-game/tests/emulator/bsnes-wram.patch`, for the CI workflow to build
the core with; a fix to one goes to the other.

## CI

    .github/workflows/ci.yml
                 what GitHub Actions runs on every push to `main`: the Rust
                 workspace and its tests, `just test`, and the test game
                 with the tools installed from the commit, in both cores,
                 Goombario over its cartridge among its tests
    requirements.txt
                 what the Python tests import that is not the standard
                 library, pinned: the workflow installs it

cc65 and the two libretro cores are built by the workflow from pinned
commits, cached, and not installed from Ubuntu's packages: why, at the top
of the workflow.
