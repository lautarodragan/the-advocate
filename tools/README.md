# tools/

Everything that runs outside the console: what reads the RPG Maker game, what
converts it, what builds the ROM, and what runs it in the tests. Nothing
loose: each thing lives in the folder of its responsibility.

## The layers

From the bottom up. A folder imports only from the ones below it, never from
one in its own row or above.

    common/      where everything is (project), the converter's disk cache
                 (disk_cache), and spreading pure work across forked
                 processes (parallel). It imports nothing from `tools/`, and
                 any of the ones above may import it

    rpgmaker/    the game as data: the JSON dump of rom/data/ (lcf), what is
                 ours and overrides it (fork), the RM2k command codes
                 (event_codes), its rules and the geometry of its images
                 (rm2k), and where the game and the RTP are (resources). No
                 rule of the format lives here: rom/data/ comes resolved. It
                 has its own README
    assembly/    only `entregar`, which is A Blurred Line's and not the
                 suite's: what builds the ROM is `rm2k-snes/cartridge/`, in Rust
    emulator/    the libretro core from Python (retro), and the bsnes-libretro
                 patch that exposes the WRAM

    render/      the call the converter uses to ask `rm2k-render` for
                 pictures, the `Renderer` that holds the game the converter
                 reads, and the image of the fork's ChipSets
                 (chipset_recipe); uses rpgmaker. A map's layers and its
                 CharSets are drawn by `rm2k-snes-maps`, below

    port/        the converter to SNES —snes_convert, which is `main`— and
                 everything only it uses: the parts it was split into on
                 2026-09-29 (options, cases, game_scan, map_convert,
                 map_layers, sprites, obj_extras, vram, screen_stage,
                 battle_stage, image_stage, battle_scenes,
                 battle_animations, mapdata —the request of the emission—,
                 and stage, which runs the parts that are programs of their
                 own, and compiler, what goes into the event compiler's two
                 calls and what comes back; the docstring of snes_convert
                 says what each one is), and events —what the converter
                 keeps of the event compiler: the constants, the registries
                 its answer is read into, the models the tests use—,
                 event_opcodes, experience, picture, window, scene,
                 animation, compress, fullscreen; and beneath all of them, because they
                 import nothing from the port, rules (from Game_Actor and
                 the LDB), constants, palette (a full screen at 8 bpp) and
                 snes_format (a tile, a color and a cell as the PPU reads
                 them)

And the Rust projects, which are not layers of the port but separate tools,
in English and without a single mention of this game (see AGENTS.md). They
have layers of their own, one folder each:

    snes/        the console's formats, knowing nothing of RPG Maker
      protocol/  declares a bytecode and generates the constants for both
                 sides; generic, but its constants are for the 65816
                 assembler
      adeleine/  Adeleine: which colors a picture loses and how the ones
                 left are grouped into palettes
      gunter/    Gunter: BRR codec and SoundFont reader
      voodoo/    Voodoo: from an image to tiles, palettes and tilemap
      lz2/       Nintendo's LC_LZ2, with an optimal parser
      resample/  Pillow's LANCZOS resize, to the bit, as a library

    rm2k/        RPG Maker 2000's, knowing nothing of the console
      ditto/     reads and writes its formats; and as a library, the one
                 place in Rust that reads a dump, with the schema's types
      rules/     `rm2k-rules`, the library of what the format means:
                 passability, which layer covers which, the page a new
                 game starts on and what it draws, the experience curve,
                 what a map inherits from the tree. The converter's Python
                 has the same rules, and a test holds the two together
      rm2k-render/  a map's tile layers, its CharSets, what its battles are
                 drawn with —animation cells, backdrops, enemies—, and the
                 faces, windows and pictures of the screens, as pictures

    rm2k-snes/   what joins the two: an RPG Maker game made into a cartridge
      project/   `rm2k-project`, the library: which game, its settings, the
                 machine's flags and the disk cache's key
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
                 converter runs it as a stage, through `port/stage.py` and
                 `port/battle_stage.py`, and its README says what shape a
                 stage has
      events/    `rm2k-snes-events`: the event compiler —a game's event
                 pages to the bytecode the ROM runs—; the converter calls
                 it twice, through `port/compiler.py`
      map-background/  `rm2k-snes-map-background`, a library: a map's two
                 background layers in the lower half of colour memory, and
                 its 16x16 blocks
      map-sprites/  `rm2k-snes-map-sprites`, a library: a map's characters
                 as objects —the palette split, the VRAM bank and the pose
                 bank— and the extras at the end of the bank
      maps/      `rm2k-snes-maps`: a whole map —its layers, the events baked
                 into them, its objects, its blocks—, with those two; the
                 converter runs it once per map, through
                 `port/map_convert.py`
      text/      `rm2k-snes-text`, a library: easyrpg-player's fonts, a line
                 of text drawn over the System, and a message box reflowed
                 for a narrower window
      screens/   `rm2k-snes-screens`: the screens —the message window and
                 its font, the title's menu, the save slots and the pause
                 menu, the text screens with their windows, End Game—, the
                 geometry they are drawn with, and every message box
                 reflowed; the converter runs it once per cartridge,
                 through `port/screen_stage.py`, and the game's tests ask it
                 for the screens they compare against
      images/    `rm2k-snes-images`: the pictures —the title and the Game
                 Over, the picture of a `ShowPicture`, the battle's
                 backdrops, battlers and animations—, scaled with
                 `resample`, toned and brought down to their palettes with
                 Adeleine; the converter runs it through
                 `port/image_stage.py`
      mapdata/   `rm2k-snes-mapdata`: the emission —the cartridge's data
                 `.inc`, written from what every other stage answered—,
                 the LZ2 streams of what the console decompresses, and the
                 VRAM layouts, which it publishes for the maps and the
                 screens; the converter runs it through `port/mapdata.py`
                 and `port/vram.py`

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
`ditto` and `protocol` keep optimizing for size there. They are still
separate projects, installed and tested one by one:

    just -f tools/justfile install lz2    one, with `cargo install --locked
                                          --path`, from the workspace's lock
    just -f tools/justfile lz2-test       one project's tests
    just -f tools/justfile rust-test      all of them, `cargo test --workspace`

They are used from the PATH: no `.py` here builds them or looks for them in
`target/`. The same goes for the Python scripts that get executed: see "The
ones that run".

## Cycles

Counting the imports inside functions, which Python does not see at load
time but are still dependencies, there is no import cycle among the `.py`
files of `tools/`. Inside `port/`, the ones at the bottom are those that
import nothing from the port; above them, those that ask another for
something —`screens` from `menus` and `events`,
`game_scan`, `sprites` and `mapdata` from `compiler`,
`title` and `menus` from `palette`—; and on top of everything `snes_convert`,
which uses all of them. The parts `snes_convert` was split into import
from each other in one direction —`map_convert` and `mapdata` on top,
`stage` at the bottom— and none imports from `snes_convert`. The imports
still inside a function no longer hide any cycle.

Until 2026-09-29 there was one exception, `assembly/cartridges.py`, the
orchestrator: it lived at the bottom, imported from `port/` and `audio/`,
and `port/patches.py` imported it back. It went to Rust —`rm2k-snes-cartridges`—,
and whoever needs what it knows asks it: `ceilings` runs it with `--list
--json`, and `rm2k-snes-patches`, in Rust since 2026-09-30, uses it as a
library.

The graph, per file and per package, is printed by the script in appendix D
of `docs/research/el-mapa-de-las-herramientas-de-python.md`. That script puts
`comun` —`common` since 2026-09-29— in the same row as `rpgmaker`, as it
was when it was written; since it has `project` it goes at the very bottom,
with `"common": -1` in its `NIVEL`.

## How imports work

Each folder is a Python package, and is imported by its name, with `tools/`
—and only `tools/`— on `sys.path`:

    from rpgmaker import lcf
    from rpgmaker.resources import find_resource

A bare `import lcf` fails, on purpose: if it worked too, the same module
could be loaded twice under two names, and what one changes on the other
—`snes_convert` changes `DECORATE_TRANSLUCENT` on `lcf`— would not get
through.

## The ones that run

The scripts that get run are executables —shebang and `chmod +x`— and `just
install` installs them as symlinks in the same `bin/` as the Rust
binaries; `just install-scripts`, the symlinks alone, without compiling
anything, which is what a renamed or new script needs: a symlink points to
a file path. The `justfile` calls them by name and does not know where they
are:

    rm2k-snes-convert           port/snes_convert.py
    abl-entregar                assembly/entregar.py

and next to them the ones that are Rust binaries —`rm2k-snes-cartridges`,
`rm2k-snes-assemble` and `rm2k-snes-space`, from `rm2k-snes/cartridge/`, which find
the runtime through the checkout they were installed from; and
`rm2k-snes-msu` and `rm2k-snes-volume-ceilings`, from
`rm2k-snes/rm2k-snes-audio/`; `rm2k-snes-battle`, from
`rm2k-snes/battle/`; `rm2k-snes-events`, from `rm2k-snes/events/`;
`rm2k-snes-maps`, from `rm2k-snes/maps/`; `rm2k-snes-mapdata`, from
`rm2k-snes/mapdata/`; and `rm2k-snes-patches`, from
`rm2k-snes/patches/`—.

The reason for the names is in `tools/justfile`. A new one is added in
`_install`, and the `.py` finds its packages by resolving the symlink with
`realpath`, because `__file__` is the PATH location: it climbs up to
`tools/` and no further. **Where everything else is** is answered by
`common/project.py`, and by nobody else: `tests/test_project.py` enforces
it. What belongs to the repo —the root, the runtime— comes from where that
file is; what belongs to the game, from its project file: see "How they find
the game". The tests put `tools/` on the path themselves, from
`pytest.ini`: A Blurred Line's, from `rom/pytest.ini`, and the tools'
—`tests/`, the ones that do not need the game—, from the one here. See
`tests/README.md`.

A worktree that modifies the tools uses its own with `just -f
tools/justfile install-local <destination>`, which builds a `bin/` of its
own wherever whoever will use it says: the game's `justfile` looks for its
own in a directory of its own, and this one, in `tools/.local-tools/`.
Each puts it first on the PATH of its recipes: see the recipe, and
"Sub-agentes" in AGENTS.md.

## What the game decides: the project file

**What belongs to a game is not written in the tools**: which maps and which
cases each cartridge carries, what the ROM is called, the title in its
header and the signatures of its save files, which sound effects go whole,
which songs go separately, which CharSet weighs most when splitting
palettes. The game declares it at its root, in `rm2k-snes.toml` —A Blurred
Line's is `rom/rm2k-snes.toml`—, and it is read with `common/settings.py`:
`settings.value("maps", "below", kind=int)`.

* **A missing key is an error**, with its name, and not a default value: a
  default in a tool would be ABL's value, and another game would be built
  with it without a warning. `tests/test_settings.py` enforces it, and on
  ABL's side `test_perillas_repetidas.py`, which fails if a `.py` here writes
  a value from the file again.
* **It is read when used, not at import**: the converter and what it uses
  must be importable without a game, which is what the tests here do.
  `rm2k-snes-cartridges`, the game's orchestrator, reads the whole file when
  it starts; it is the Rust library `rm2k-snes/project/` that reads it there.
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
not find it, they stop and say where they searched from. The search happens
the first time someone asks, not at import: importing the converter does not
require a game.

**How the game is laid out inside is declared by its file**, in `[paths]`,
relative to it: the dump (`data`), what was decided (`patches`), what was
built (`build`) and the suite's cases (`cases`). What goes inside —`manual/`
and `auto/` in the decided part, one directory per cartridge in the built
part— is the shape the tools give it. What only the game's tests read —their
goldens, what they leave to look at— does not go there: they know it by
their location.

**What belongs to the machine arrives by flags**: `--game-dir`, `--rtp-dir`,
`--soundfont`, `--replacements` (the MSU-1 tracks that come from an audio file
and not from the MIDI), `--cache`, `--test-cartridges` and, in
`abl-entregar`, `--shared`. Each executable adds the ones it uses and
sets them in `common/environment.py`, where the rest read them from;
`resources.GAME_DIR` and `resources.RTP_DIR` are resolved there when
read. **None has a default value**, except the cache and the test
cartridges, which have their place in the project's `build`: a machine's
value belongs to the caller. In A Blurred Line, `rom/justfile` translates its
variables into flags.

`tests/test_project.py` enforces it: it fails if a `.py` here reads an
`ABL_*` variable or writes `rom/` as a path.

## `tools/justfile`

The tools' recipes —generating the bytecode, running their tests,
installing— live in `tools/justfile`, and A Blurred Line's in
`rom/justfile`, which names this directory only once: to say how a
worktree's tools are installed. The root `justfile` imports ABL's and not
this one. From the root they are run with `just -f tools/justfile <recipe>`;
standing here, with `just <recipe>`. Both forms run the recipe standing in
`tools/`.

## The bsnes patch

`emulator/bsnes-wram.patch` is for **bsnes-libretro**, not for this repo.
bsnes does not expose the WRAM —`retro_get_memory_data` returns null for
every id— and the tests' clock asks the ROM which tick of the loop it is on,
which lives in `ticks`, in the WRAM. Without the patch, whatever runs under
bsnes falls back to counting hardware frames, which works as long as the ROM
does not fall behind. And without bsnes there is nothing to answer what
`rom/pruebas/rpgmaker/test_cores.py` exists to answer.

The patch exposes only `RETRO_MEMORY_SYSTEM_RAM` and leaves the rest as it
is: bsnes's comment on that function is about the SRAM, which is not touched,
and that is why it is defensible upstream. Its commit message says the rest.

Building it takes `gcc` and `make`, and nothing else:

    git clone https://github.com/libretro/bsnes-libretro
    cd bsnes-libretro
    git am < .../tools/emulator/bsnes-wram.patch
    make -j$(nproc)
    cp bsnes_libretro.so /usr/lib/libretro/
