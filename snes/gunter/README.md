# Gunter: BRR, and where samples come from

Gunter is the library; **BRR is the format it writes**, the one the SPC700
plays. The name of the format stays wherever it names the format — the nine-byte
blocks, the codec — and `gunter` is the crate.

Two jobs that always turn up together:

* **`gunter::codec`** — PCM into BRR, the compressed sample format the SNES
  sound chip plays, and back. Nine bytes per sixteen samples, take it or leave
  it.
* **`gunter::sf2`** and **`gunter::extract`** — read a SoundFont and find the
  sample a selector picks, which is how you get PCM worth encoding in the first
  place.

    let mut font = SoundFont::open(path)?;
    let contract = extract::contract(&font, &Selector::Program { program: 0, bank: 0, key: 60 }).unwrap();
    let pcm = font.pcm(contract.sample.start, contract.sample.end)?;
    let brr = codec::encode(&pcm, Some(loop_block));

It is a library and not a command: the music stage calls it in its own
process. `cargo test` tests it; the tests are samples generated inside the
test —silence, a ramp, a square, an impulse, clipping— and fonts written by
the test, so they need neither a game nor a SoundFont.

Nothing here knows what the samples are for. What a sample is called, how loud
it should be and at what rate to store it are the caller's decisions; this only
does the two conversions.

## A sample is not just its bytes

BRR carries the audio and almost nothing else: **no sample rate and no loop
point**. Both live in the DSP's registers, set by whatever plays the sample, so
BRR blocks on their own are not playable — somebody has to remember two more
numbers. Losing them is the classic way a sample ends up an octave off or
clicking once a second.

So what a selector finds is a **contract**, not only the audio: where the
sample's audio is in the font, its rate, which key sounds at that rate, its
tuning, and its loop relative to the extracted audio.

## The envelope comes with the sample

A SoundFont zone says how loud its sample is over time, and a player that
plays the audio without that envelope plays a different instrument: a piano
that never decays, a bass that rings for seconds after it is let go. So the
contract also carries the zone's **volume envelope**, generators 33 to 40:
delay, attack, hold, decay, sustain, release, and the two key scalings.

The values are resolved and nothing more. A preset zone's generators **add**
to the instrument zone's rather than replace them, generators nobody sets
take the specification's defaults, and the sum is clamped to the ranges the
specification allows —two legal amounts can add up to an illegal one—. They
stay in the file's units: timecents for times (1200 per doubling, 0 is one
second, -12000 is none), centibels of attenuation for the sustain level, and
timecents per key for the two key scalings, which apply around key 60.
Turning that into seconds, or into what some chip's envelope can do, is the
caller's business. Nothing is read but the font's headers, so asking for the
envelope of every key a piece plays is cheap.

A selector by a sample's name has no zone, so it has no envelope.

## The loop has to fall on a block

The DSP comes back to the **start of a nine-byte block**, so a loop point is a
multiple of sixteen samples and there is no rounding to be had: `encode` takes
the block to loop back to.

That constraint belongs to whoever picks the loop, not here: a sample whose
loop does not land on a block has to be resampled until it does, and resampling
is not this library's business.

## Decoding

`decode` turns BRR back into PCM, and `error` says the worst sample of an
encoding as a percentage of the peak. Decoding is not a check on its own — a
decoder that shares a bug with the encoder agrees with itself — but it is what
makes the codec's error measurable instead of theoretical.

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
