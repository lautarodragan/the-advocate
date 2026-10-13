# rm2k-snes-audio: a game's music, for the SPC700

    rm2k-snes-audio compile --job job.json --out build/ \
        --game-dir game/ --rtp-dir rtp/ --soundfont bank.sf2
    rm2k-snes-audio cartridge --request request.json --out build/ \
        --msu build/game.msu --data dump/ --game-dir game/ --soundfont bank.sf2
    rm2k-snes-audio msu-index build/game.msu
    rm2k-snes-audio decode --stream stream.bin --sounds sounds.bin
    rm2k-snes-audio keys song-a song-b --game-dir game/ --soundfont bank.sf2
    rm2k-snes-msu build/game.sfc --game-dir game/ --soundfont bank.sf2
    rm2k-snes-volume-ceilings --measure

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

An RPG Maker 2000 game's songs are MIDIs, written for a General MIDI
synthesizer with as many voices as it wants; the Super Nintendo has an
S-DSP with eight voices that play samples out of 64 KB of RAM. This turns
the one into the other: from each song's MIDI and the SoundFont the game was
composed with, the samples, a stream per song that says what each voice
plays frame by frame, and which samples each map has to have in the SPC700
when it is entered. The console only plays it back.

It uses [Gunter](../../snes/gunter/) as a library for what is about formats —reading
the SoundFont, encoding BRR—, and `rm2k-project` to read what the game
decides about its music in its `rm2k-snes.toml`. Where the game, the RTP
and the SoundFont are is the caller's to say: nothing here has a default
path.

## The job

`compile` reads what to build from a JSON, which is what a cartridge's
compiler knows and this does not: which songs, in the order its bytecode
already numbers them; which sound effects, from most to least requested;
and **the packages** —which songs and sound effects each map can play,
which songs it starts only to leave (`exits`), which ones go up alone with
its sound effects (`separate`)—, and which song may already be playing when
each one loads (`inheritance`). With `emit`, it also writes what goes into
the cartridge besides the music: which song plays at boot, which one each
map starts, the table of sounds. `--help` lists every field.

## What comes out

Into `--out`:

* `musicdata.inc`, with `emit`: the driver, the sample directory and every
  sample, each song's stream and its table of sounds, the packages, the
  sound effect table; for ca65, everything in `RODATA` with a `.block` or a
  `.crossbank` in front of each piece. Its second line, `; Songs: …`, lists
  the songs in order, and is read by whoever needs to know which song an
  index is.
* `music.json`, with `emit`: each song's length, MSU-1 track and the
  fingerprint of its mix.
* `audio.json`, always: the bank —which sample each song plays each key
  with, what each one weighs and which package limited it—, each song and
  each sound effect, the boot's estimate, and each package's MSU-1 versions
  of its sound effects; with `--detail`, each song's notes, writes and voice
  allocation too.

And to standard output, what each song and the bank came out as.

## How it decides

* **One sample per General MIDI program and per percussion key**, shared by
  every song, from the SoundFont zone where the whole cartridge plays that
  program the most.
* **Each sample has the budget of its worst package**, not of the whole
  bank: the ARAM holds one package at a time, and a package's samples and
  sound effects have to fit together. A sample that a crowded package
  limits gets **a copy** for the songs outside it, as long as the
  directory's 255 entries allow.
* **The eight voices belong to every channel**, allocated note by note: a
  note takes a free voice, or steals the weakest that is not a channel's
  last, or does not play.
* **The stream is per note**, and expands into exactly the DSP writes it
  stands for: `decode` is the model of the console's decoder, and `compile`
  stops if a song's stream does not decode to what it has to write.
* **Sound effects share the directory's last entries**: two that are never
  in the same package go to the same place.

## A cartridge's music, as a converter's stage

`cartridge` is what a converter calls, with the shape of the one described
in `../battle/README.md`, "One stage of a converter". It builds the job
itself, compiles it in the same process, and leaves the job next to what it
made —`audio-job.json`— so `compile` can rebuild that music alone. What it
decides that `compile` does not:

* **Which songs the cartridge carries**: the ones the event compiler
  numbered, and after them —so as not to renumber what the bytecode
  already carries— the boot map's, the title's, the Game Over's and each
  map's own, from the map tree.
* **Each map's audio package**: its own song in front, the boot one, its
  sound effects in the order its pages ask for them; apart, its exit songs
  and its separate ones —the project's `[music] apart_themes`—; and the
  battle's, the Game Over's and the title's.
* **Which song may be playing when each one loads**, following the jumps of
  the compiled pages without looking at conditions, minus the project's
  `[music] jumps_that_never_happen`: see `inherited_songs`.
* **That the boot fits in the ROM's `BOOT_FRAMES`**, read from the runtime.
* **The `.msu`** with the data the MSU-1 serves the ROM: the quality battle
  backdrops, which come made in the request, and behind them each
  package's quality sound effects —see `msu_data.rs` for the format—, and
  the tables the ROM reads it with, at the end of `musicdata.inc`.

It reads the map tree and the database's `System` from a Ditto dump
(`--data`), with Ditto's library and `rm2k-rules`' tree. `--help` lists what
the request carries. `msu-index` and `msu-sign` are for whoever looks
inside a `.msu`: its entries, and the same file signed again.

## Exactly those bytes

Until 2026-09-29 the same music was compiled by a Python program, and this
was checked equal to it byte for byte —streams, samples, tables— on two
whole cartridges of a real game. So it rounds as Python did (to even),
floors its integer divisions, filters the samples with numpy's kernel summed
in numpy's order and calls the C library's `pow` even for a square. What
`tests/python.rs` keeps is the SHA-256 of what that Python wrote for a small
game generated inside the test —see `tests/fixture/`—, so the check needs
neither the Python nor a game. The same goes for `cartridge`, whose
decisions were the converter's Python until 2026-09-30: `tests/cartridge.rs`
keeps the SHA-256 of the job and of the `.msu` it gave for the small game of
`tests/cartridge.json`.

Two tests read a real SoundFont's envelopes, in `SOUNDFONT`; without the
variable they are skipped with a message.

## The other two programs

Two more binaries come out of this crate, because they are about the same
music and read what `compile` leaves next to a built cartridge:

* **`rm2k-snes-msu`**, the MSU-1 tracks: one `<rom>-N.pcm` per song of the
  cartridge, rendered from its MIDI with `fluidsynth` and the same
  SoundFont —or decoded with `ffmpeg`, from a replacement or a WAV—, and
  normalized. Both programs are looked up on the PATH. A track made from
  the same sources is not made again: the disk cache keeps the sha256 of
  each `.pcm` under a key that carries the MIDI, the SoundFont, both
  programs and this binary itself.
* **`rm2k-snes-volume-ceilings`**, each song's volume ceiling, measured by
  playing it in the built ROM on a libretro core, and written to the
  project's table —the one `compile` reads—. It runs the cartridges'
  builder to make the copy it measures and to rebuild with the table, and
  plays each song in a process of its own —itself, with `--play`—, because
  a libretro core is one console per process. `--play` is also what a test
  asks when it wants a single song.

They are separate binaries and not subcommands so they keep the names the
game's recipes already call, and so the MSU-1 tracks' key only changes when
code that goes into that binary changes: a new flag in `compile` does not
make every track again.

Until 2026-09-29 both were Python scripts; the tracks come out byte for
byte the same, and the ceilings measure the same numbers.

## Exit codes

`1` when the answer is no: the samples do not fit in the ARAM even at the
minimum, a song's stream would not write what it has to, a song or a WAV
is not there. `2` when the call is wrong: a job that does not parse, a file
that cannot be read.
