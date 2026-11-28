# rm2k-snes-audio: a game's music, for the SPC700

`cargo test`. It is a library a converter is compiled with —see "A
cartridge's music, as a converter's stage"—, and has no binary since
2026-11-28, when its last subcommand, `volume-ceilings`, went: see "The
tracks and the ceilings".

An RPG Maker 2000 game's songs are MIDIs, written for a General MIDI
synthesizer with as many voices as it wants; the Super Nintendo has an
S-DSP with eight voices that play samples out of 64 KB of RAM. This turns
the one into the other: from each song's MIDI and the SoundFont the game was
composed with, the samples, a stream per song that says what each voice
plays frame by frame, and which samples each map has to have in the SPC700
when it is entered. The console only plays it back.

It uses [Gunter](../../snes/gunter/) as a library for what is about formats —reading
the SoundFont, encoding BRR—, and `rm2k-project` to read what the game
decides about its music in its `advocate.toml`. Where the game, the RTP
and the SoundFont are is the caller's to say: nothing here has a default
path.

## The job

`compile` builds from a job, a JSON object, which is what a cartridge's
compiler knows and this does not: which songs, in the order its bytecode
already numbers them; which sound effects, from most to least requested;
and **the packages** —which songs and sound effects each map can play,
which songs it starts only to leave (`exits`), which ones go up alone with
its sound effects (`separate`)—, and which song may already be playing when
each one loads (`inheritance`). With `emit`, it also writes what goes into
the cartridge besides the music: which song plays at boot, which one each
map starts, the table of sounds. `job.rs` lists every field.

## What comes out

As files, by name, for its caller to write:

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
  of its sound effects.

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
  stands for: `stream::decode` is the model of the console's decoder, and
  `compile` stops if a song's stream does not decode to what it has to
  write.
* **Sound effects share the directory's last entries**: two that are never
  in the same package go to the same place.

## A cartridge's music, as a converter's stage

`stage::cartridge` is what a converter calls, as a function and not a
subcommand, with the shape of the one described in `../battle/README.md`,
"One stage of a converter". It builds the job
itself, compiles it in the same process, and leaves the job next to what it
made —`audio-job.json`—, which says what it was asked. What it decides
that `compile` does not:

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

It reads the map tree and the database's `System` from a Ditto dump,
with Ditto's library and `rm2k-rules`' tree; `Request` says what it is
asked. And it leaves what a game's tests read of the music without
asking it: the `.msu`'s index, `msu-index.json`, and what each song's
stream writes to the DSP, `music-writes/<song>.json.gz` —see
`song_writes`—.

## Its tests

The tests compile a small game generated inside them —see `tests/fixture/` and
`tests/small_game.rs`—, songs made in the test with the shapes a real
game's showed —`tests/real_shapes.rs`: a crowded frame, packages that do
not fit—, and plan the small cartridge of `tests/cartridge.json`, so they
need neither a game nor a SoundFont of one's own.

Two tests read a real SoundFont's envelopes, in `SOUNDFONT`; without the
variable they are skipped with a message.

## The tracks and the ceilings

* **Each song's volume ceiling**, in `src/ceilings.rs`: the highest
  headroom that does not clip, measured while `compile` builds the song, by
  playing what it writes to the S-DSP in a model of the chip —blargg's,
  in [`spc-dsp`](../../snes/spc-dsp/)— with the samples it plays. Each
  song's peak is kept per mix in the converter's disk cache, so a change to
  one song plays only that one again. How it measures, and how far the
  model is from the console, is at the top of `src/ceilings.rs`. Until
  2026-11-28 it was a subcommand, `volume-ceilings`, which built a copy of
  the cartridge, played each song on its title screen in a libretro core
  —one process per song—, and wrote a table into the game's automatic
  patches, which `compile` read and which went stale with every change to
  the mix.
* **The MSU-1 tracks**, `Tracks` in `src/tracks.rs`, which `advocate
  build` calls after building `release`: one `<rom>-N.pcm` per song of the
  cartridge, rendered from its MIDI with `fluidsynth` and the same
  SoundFont —or decoded with `ffmpeg`, from a replacement or a WAV—, and
  normalized. Both programs are looked up on the PATH. A track made from
  the same sources is not made again: the disk cache keeps the sha256 of
  each `.pcm` under a key that carries the MIDI, the SoundFont, both
  programs and the source of the code that writes a track —`OWN_SOURCES`
  in `src/tracks.rs`—. It is not a stage of the converter.

Until 2026-11-23 they were binaries of their own, `rm2k-snes-msu` and
`rm2k-snes-volume-ceilings`, so the game's recipes kept their names and so
the MSU-1 tracks' key, which was the running executable, only changed when
code that went into that binary did. taro folded them in, to have fewer
commands on the PATH; the key stopped being the executable then, which
carries the whole compiler, and became the source of the tracks' code: a
new flag in `compile` still does not make every track again. The tracks
were the subcommand `msu` until 2026-11-25, which the cartridges' builder
ran as a process.

## Its errors

`Bad::Answer` when the answer is no: the samples do not fit in the ARAM
even at the minimum, a song's stream would not write what it has to, a song
or a WAV is not there, a song that still clips with its volume ceiling.
`Bad::Usage` when the call is wrong: a job that does not parse, a file that
cannot be read. Until 2026-11-28, when the binary went, they were its exit
codes, `1` and `2`.
