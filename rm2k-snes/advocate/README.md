# advocate

Builds an rm2k-snes game: the program a person runs, standing in the game's
directory or naming it with `--project`, where its `advocate.toml` is.

    advocate build                  every cartridge that is not up to date
    advocate build release          only that one, with its MSU-1 tracks
    advocate build --force          all of them, even the ones up to date
    advocate build --list           which case goes in which cartridge
    advocate build release --into DIR -- --some-converter-flag
                                    a copy, somewhere else, with more flags

It takes the machine's values by flags —`--game-dir`, `--rtp-dir`,
`--soundfont`, `--cache`, `--test-cartridges`, `--replacements`—, which a
game's `justfile` translates from its variables.

**It runs no tool of ours.** The converter and its stages, the bank packing
and the assembler, and the MSU-1 tracks are libraries it calls:
`rm2k-snes-convert`'s, `rm2k-snes-cartridge`'s and `rm2k-snes-audio`'s.
What it still runs is not ours: `ca65` and `ld65`, from the cc65 project,
and the tracks' `fluidsynth` and `ffmpeg`, all on the PATH. The cartridges
convert at the same time, in threads, each one saying what it says in its
own `converter.log`.

**Every build leaves `build/advocate.json`** beside `advocate.toml`, also
when every cartridge was up to date and when one failed, written aside and
renamed: the project as the tools resolve it, the machine values it was
built with, its cartridges —what each carries, where, whether it was up to
date when the build ended and how much room it has left— and the runtime's
memory map and sources. It is what a game's tests and recipes read instead
of running a tool; what each key holds is at the top of `src/file.rs`. At
the end of a build it prints one line per cartridge, its free data banks
and its tightest bank; the rest of the space is in the file.

It is one binary, in a crate of its own on top of the libraries, so that
what it installs is said by its name. Until 2026-11-25 building was `rm2k-snes-cartridges`, which ran the
converter once per cartridge and the tracks as processes; and what is now
the file the tests asked it and `rm2k-snes-project`.

Its tests are the cartridge library's and the games': building a game needs
the game.
