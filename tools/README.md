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
    assembly/    the memory map (banks), what builds the ROM (ensamblar), and
                 which ROMs exist and with which flags (cartuchos, used by
                 `just build`)
    emulator/    the libretro core from Python (retro), and the bsnes-libretro
                 patch that exposes the WRAM

    render/      a map and a chipset as images, with the CharSets on top,
                 and the image of the fork's ChipSets (chipset_recipe); uses
                 rpgmaker

    audio/       from MIDI to the SPC700: snes_music, midi, musica, sdsp,
                 spc700, brr_samples, snes_samples, music_opcodes, and the
                 MSU-1 tracks (msu); uses rpgmaker and common

    port/        the converter to SNES —snes_convert— and everything only it
                 uses: eventos, event_opcodes, batalla, experiencia,
                 pantallas, menus, titulo, imagen, ventana, fuente, escena,
                 animacion, textos, asignador, tiles_bin, comprimir,
                 pantalla_completa, fin_del_juego, msu_datos, parches; and
                 beneath all of them, because they import nothing from the
                 port, reglas (from Game_Actor and the LDB), constantes, color
                 (the screen tint), paleta (an image down to N colors) and
                 formato_snes (a tile, a color and a cell as the PPU reads
                 them)

And the Rust projects, which are not layers of the port but separate tools,
in English and without a single mention of this game (see AGENTS.md):

    ditto/       reads and writes the RPG Maker 2000 formats
    protocol/    declares a bytecode and generates the constants for both sides
    gunter/      Gunter: BRR codec and SoundFont reader
    voodoo/      Voodoo: from an image to tiles, palettes and tilemap
    lz2/         Nintendo's LC_LZ2, with an optimal parser

They are installed with `just -f tools/justfile herramientas` and used from
the PATH: no `.py` here builds them or looks for them in `target/`. The same
goes for the Python scripts that get executed: see "The ones that run".

## Cycles, and the violation that remains

Counting the imports inside functions, which Python does not see at load
time but are still dependencies, there is no import cycle among the `.py`
files of `tools/`. Inside `port/`, the ones at the bottom are those that
import nothing from the port; above them, those that ask another for
something —`batalla` from `eventos`, `pantallas` from `menus` and `eventos`,
`titulo` and `menus` from `paleta`—; and on top of everything `snes_convert`,
which uses all of them. The imports still inside a function no longer hide
any cycle.

The only exception is `assembly/cartuchos.py`, which is the orchestrator
and lives at the bottom: it imports from `port/` and `audio/`, runs
`port/snes_convert.py` as a subprocess, and `port/parches.py` imports it
back: the only cycle, if the subprocess counts. These are the only layer
violations, and they stay on purpose: what to do with it is an open
question, see `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

The graph, per file and per package, is printed by the script in appendix D
of `docs/research/el-mapa-de-las-herramientas-de-python.md`. That script puts
`comun` —`common` since 2026-09-29— in the same row as `rpgmaker`, as it
was when it was written; since it has `project` it goes at the very bottom,
and with `"common": -1` in its `NIVEL` the only violations it prints are
those of `cartuchos`.

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
herramientas` installs them as symlinks in the same `bin/` as the Rust
projects. The `justfile` calls them by name and does not know where they
are:

    rm2k-snes-cartridges        assembly/cartuchos.py
    rm2k-snes-assemble          assembly/assemble.py
    rm2k-snes-space             assembly/space.py
    rm2k-snes-convert           port/snes_convert.py
    rm2k-snes-patches           port/parches.py
    rm2k-snes-msu               audio/msu.py
    rm2k-snes-volume-ceilings   audio/ceilings.py
    abl-entregar                assembly/entregar.py

The reason for the names is in `tools/justfile`. A new one is added in
`_instalar`, and the `.py` finds its packages by resolving the symlink with
`realpath`, because `__file__` is the PATH location: it climbs up to
`tools/` and no further. **Where everything else is** is answered by
`common/project.py`, and by nobody else: `pruebas/test_project.py` enforces
it. What belongs to the repo —the root, the runtime— comes from where that
file is; what belongs to the game, from its project file: see "How they find
the game". The tests put `tools/` on the path themselves, from
`pytest.ini`: A Blurred Line's, from `rom/pytest.ini`, and the tools'
—`pruebas/`, the ones that do not need the game—, from the one here. See
`pruebas/README.md`.

A worktree that modifies the tools uses its own with `just -f
tools/justfile herramientas-locales <destination>`, which builds a `bin/` of
its own wherever whoever will use it says: the game's `justfile` looks for
its own in a directory of its own, and this one, in
`tools/.herramientas-locales/`. Each puts it first on the PATH of its
recipes: see the recipe, and "Sub-agentes" in AGENTS.md.

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
  with it without a warning. `pruebas/test_settings.py` enforces it, and on
  ABL's side `test_perillas_repetidas.py`, which fails if a `.py` here writes
  a value from the file again.
* **It is read when used, not at import**: the converter and what it uses
  must be importable without a game, which is what the tests here do. The
  exception is `assembly/cartuchos.py`, which is the game's orchestrator
  and reads the whole file when loaded.
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
`resources.GAME_DIR` and `snes_samples.SOUNDFONT` are resolved there when
read. **None has a default value**, except the cache and the test
cartridges, which have their place in the project's `build`: a machine's
value belongs to the caller. In A Blurred Line, `rom/justfile` translates its
variables into flags.

`pruebas/test_project.py` enforces it: it fails if a `.py` here reads an
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
which lives in `vueltas`, in the WRAM. Without the patch, whatever runs under
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
