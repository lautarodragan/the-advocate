# Gunter: BRR, and where samples come from

Gunter is the tool; **BRR is the format it writes**, the one the SPC700 plays.
The name of the format stays wherever it names the format — the `.brr` files,
the nine-byte blocks, the codec — and `gunter` is what you type.

Two jobs that always turn up together, as one binary:

* **`gunter encode`** — PCM into BRR, the compressed sample format the SNES sound
  chip plays. Nine bytes per sixteen samples, take it or leave it.
* **`gunter sf2`** — read a SoundFont and take a sample out of it, which is how
  you get PCM worth encoding in the first place.

The same two are a library, for a program that builds many samples and would
rather not start a process for each: `gunter::codec` encodes and decodes,
`gunter::sf2` reads the font, and `gunter::extract` is what `sf2 --extract`
does —the selector, the zone, the contract below and the audio—.

Nothing here knows what the samples are for. Where files go, what a sample is
called, how loud it should be and at what rate to store it are the caller's
decisions; this only does the two conversions, and says exactly what it did.

    gunter encode piano.wav -o piano.brr --loop-sample 1024
    gunter decode piano.brr -o back.wav --rate 22050
    gunter info piano.brr
    gunter sf2 bank.sf2 --list
    gunter sf2 bank.sf2 --extract program:0 -o piano.wav
    gunter sf2 bank.sf2 --extract drum:36 -o kick.wav

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints the
selectors and the rules below. The tests are samples generated inside the
test —silence, a ramp, a square, an impulse, clipping— plus the error
messages, so they need neither a game nor a SoundFont.

## A sample is not just its bytes

BRR carries the audio and almost nothing else: **no sample rate and no loop
point**. Both live in the DSP's registers, set by whatever plays the sample, so
a `.brr` file on its own is not playable — somebody has to remember two more
numbers. Losing them is the classic way a sample ends up an octave off or
clicking once a second.

So every command that produces or reads a sample prints them, and `--json`
prints the same thing in one line a build script can read:

    $ gunter encode piano.wav -o piano.brr --loop-sample 1024 --json
    {"output": "piano.brr", "samples": 8192, "rate": 22050, "blocks": 512,
     "bytes": 4608, "loop_block": 64, "loop_sample": 1024,
     "worst_error_percent": "1.870", "within_limit": true}

## The envelope comes with the sample

A SoundFont zone says how loud its sample is over time, and a player that
plays the audio without that envelope plays a different instrument: a piano
that never decays, a bass that rings for seconds after it is let go. So
`--extract` also reports the zone's **volume envelope**, generators 33 to 40:

    $ gunter sf2 bank.sf2 --extract program:38 --json
    {..., "env_delay_timecents": -12000, "env_attack_timecents": -12000,
     "env_hold_timecents": -12000, "env_decay_timecents": 2604,
     "env_sustain_centibels": 44, "env_release_timecents": -6071,
     "env_key_to_hold": 0, "env_key_to_decay": 37}

The values are resolved and nothing more. A preset zone's generators **add**
to the instrument zone's rather than replace them, generators nobody sets
take the specification's defaults, and the sum is clamped to the ranges the
specification allows —two legal amounts can add up to an illegal one—. They
stay in the file's units: timecents for times (1200 per doubling, 0 is one
second, -12000 is none), centibels of attenuation for the sustain level, and
timecents per key for the two key scalings, which apply around key 60.
Turning that into seconds, or into what some chip's envelope can do, is the
caller's business. Without `-o` nothing is written, so asking for the
envelope of every key a piece plays is cheap: well under a millisecond each.

A `sample:NAME` selector has no zone, so its envelope fields are `null`.

## The loop has to fall on a block

The DSP comes back to the **start of a nine-byte block**, so a loop point is a
multiple of sixteen samples and there is no rounding to be had. `--loop-sample`
takes the number in samples and refuses anything else, naming the two points
that would have worked; `--loop-block` takes the block index directly.

That constraint belongs to whoever picks the loop, not here: a sample whose
loop does not land on a block has to be resampled until it does, and resampling
is not this tool's business.

## Exit codes

    0   done
    1   the answer is no
    2   the call was wrong

The distinction is the same one `--check` makes in a generator, and it exists
so a script does not have to read the message. **1** is this tool working
correctly and answering no: the font has no program 47, `--max-error` was not
met. **2** is a broken call: a file that is not a SoundFont, a `.brr` whose
length is not a multiple of nine, a loop point off a block, an unwritable path.
Every message names the file and what was expected in it.

## Input and output formats

Encoding reads a **mono 16-bit `.wav`** — the least surprising way to hand
audio around, and what every editor writes. A file that does not start with
`RIFF` is read as **headerless signed 16-bit little-endian**, which is what
makes this easy to drive from a pipeline that already has samples in memory;
pass `--rate` to say what they are, since raw bytes cannot. An 8-bit or
multi-channel `.wav` is converted and the conversion is printed, because it
changes the data.

Decoding writes a `.wav` so the result can be listened to. It is not a check on
its own — a decoder that shares a bug with the encoder agrees with itself — but
it is what makes the codec's error audible instead of theoretical.

## What the encoder actually does

Each block stores four bits per sample: not the sample, but the **difference
against what the decoder predicts** from the two previous samples. Four filters
are on offer, from "no prediction" to a fairly aggressive parabola, plus a range
of 0 to 12 saying how far each stored value is shifted left.

All four filters at all thirteen ranges are tried for every block, and the pair
leaving the least squared error wins. The prediction is simulated against what
the *decoder* will have reconstructed, not against the original samples, so the
encoder sees the error it is actually causing. The filter arithmetic is integers
and shifts, exactly as the chip does it — with real fractions the encoder would
be optimising against a decoder that does not exist.

Two blocks always take filter 0: the first, and the one the loop comes back to.
Filters 1 to 3 lean on the two previous samples, and in neither of those places
is it certain what those are. It costs a little precision over sixteen samples
and avoids a click on every pass of the loop.

The search order is part of the format's output and not an implementation
detail: ties go to the lowest filter and then the lowest range. Two encoders
that disagree on ties produce different bytes from the same audio, which is a
miserable thing to debug.
