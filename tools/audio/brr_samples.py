"""Where the port's samples come from, and how they get to BRR.

There is neither a codec nor a SoundFont reader here: both are Gunter
—`tools/gunter/`, the Rust binary—, and this module is the bridge between it
and the converter. What there is here is what the binary cannot have,
because it knows nothing about this game: the converter's disk cache and the
memory of what has already been asked for.

What is cached here is **the BRR**. The already prepared sample —the
resampling and normalization that come before— is cached by `snes_samples`,
in another category and with another key; the two expire together because
both carry `version()`.

**The two memories are what make one process per sample viable.** Measured
on 2026-09-15 over a whole conversion of `abl` with `NO_CACHE=1`: the
converter asks for 34,493 encodings for **608 distinct samples** and 70,279
SoundFont zones for **100 distinct selectors**. Without memory that would be
104,772 process launches; with it they are 708, and the 708 —binary,
temporary files and all— cost **1.33 s** of a 102 s conversion.

That is why **there is no batch mode**, which was the other way to do this.
Launching the binary costs 0.0005 s —0.30 s for the 608, measured one by
one—, so gathering all the samples into a single invocation would save
0.35 s, in exchange for one more mode in Gunter. And on top of that they
cannot be gathered completely: `snes_music`'s `Bank` rebuilds the samples
of a package that went over by looking at how much they took, so the jobs
never all exist together at any point.

What has changed since that measurement is what those 0.35 s are compared
against: the prepared-sample cache of 2026-09-20 took away half of the
conversion, so today it weighs quite a bit more than it did. It is still not
enough, but if anyone ever looks again at where the time goes, this is no
longer a negligible number.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import wave

from common import disk_cache

MISSING = """`gunter`, the SPC700 sample codec, is missing.

It is a Rust binary that lives in `tools/gunter/` and is installed as a system
tool, not built on every run:

    just -f tools/justfile install

That does `cargo install --locked --path tools/gunter`. If cargo is missing, on
Arch it is `pacman -S rust`."""

# Properties of the format, not ours: the DSP reads nine-byte blocks that
# hold sixteen samples, and loops back to the start of one.
BLOCK_SAMPLES = 16
BLOCK_BYTES = 9


class Error(Exception):
    """The binary said no, or the call was wrong."""


_version = None
_encoded = {}
_extracted = {}


def binary():
    """The path of the `gunter` on the PATH, like `assemble.binaries()`.

    Raises `SystemExit` if it is not there: a missing system tool is not a
    program error, and a twenty-line traceback buries the only line that says
    how to get it.
    """
    path = shutil.which("gunter")
    if path is None:
        raise SystemExit(MISSING)
    return path


def version():
    """Which version of "the encoder" produced what is in the cache.

    It covers this file and **the installed binary**, not the sources in
    `tools/gunter/`: the binary on the PATH is installed separately, so a tree
    with `tools/gunter/src` touched and without `just install` run keeps
    encoding with the old one. What the key has to describe is what produced
    the bytes.

    It is public because `snes_samples` caches **the already prepared
    sample** —the resampling and normalization that come before encoding— and
    that also comes out of this binary: its key has to expire when this one's
    does.
    """
    global _version
    if _version is None:
        h = hashlib.sha256()
        for path in (os.path.abspath(__file__), binary()):
            with open(path, "rb") as f:
                h.update(f.read())
        _version = h.hexdigest()
    return _version


def _run(args):
    """The binary, with its two exit codes kept apart from the rest.

    1 and 2 are its own answers —"nothing matches" and "the call is wrong"—;
    anything else means it could not be run.
    """
    try:
        result = subprocess.run([binary()] + args, capture_output=True)
    except OSError as e:
        raise SystemExit("could not run `gunter`: %s\n\n%s" % (e, MISSING))
    if result.returncode:
        raise Error("gunter %s exited with %d: %s"
                    % (" ".join(args), result.returncode,
                       result.stderr.decode("utf-8", "replace").strip()))
    return result.stdout.decode("utf-8", "replace")


def _json(text):
    """The last line the binary printed with `--json`.

    It is an object of scalars and nothing else —that is how `gunter` emits
    it—, so the `json` module is more than enough.
    """
    import json
    for line in reversed(text.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise Error("the binary printed no JSON: %r" % text[:200])


def encode(samples, loop_block=None):
    """A whole sample to BRR, with the loop point at the given block.

    The input goes raw —signed 16-bit integers, no header—, which is what the
    binary reads when the file does not start with `RIFF`: writing a WAV for
    something already in memory would be a needless header.
    """
    if not samples:
        # The converter asks for this when an instrument was left without an
        # attack, and the honest answer is zero blocks; the binary, on the
        # other hand, rejects an empty input, which is correct for someone
        # passing it a file.
        return b""

    key = (tuple(samples), loop_block)
    encoded = _encoded.get(key)
    if encoded is not None:
        return encoded

    on_disk = disk_cache.key(version(), str(loop_block),
                             " ".join(str(x) for x in key[0]))
    encoded = disk_cache.read("brr", on_disk)
    if encoded is None:
        encoded = _encode(samples, loop_block)
        disk_cache.write("brr", on_disk, encoded)
    _encoded[key] = encoded
    return encoded


def _encode(samples, loop_block):
    with tempfile.TemporaryDirectory(prefix="abl-gunter-") as tmp:
        in_path = os.path.join(tmp, "pcm")
        out_path = os.path.join(tmp, "brr")
        with open(in_path, "wb") as f:
            for s in samples:
                f.write(int(s).to_bytes(2, "little", signed=True))
        args = [in_path, "-o", out_path]
        if loop_block is not None:
            args += ["--loop-block", str(loop_block)]
        _run(["encode"] + args)
        with open(out_path, "rb") as f:
            return f.read()


class Sample:
    """What the SoundFont has for an instrument, already extracted.

    `pcm` are the raw frames, and `loop_start`/`loop_end` are in frames and
    relative to them: outside the file the loop means nothing in the
    coordinates inside it.
    """

    def __init__(self, fields, pcm):
        self.name = fields["name"]
        self.frames = fields["frames"]
        self.rate = fields["rate"]
        self.root_key = fields["root_key"]
        self.cents = fields["tuning_cents"]
        self.loop = bool(fields["loops"])
        self.loop_start = fields["loop_start"] or 0
        self.loop_end = fields["loop_end"] or 0
        self.pcm = pcm

    def __repr__(self):
        return "<Sample %r %d frames at %d Hz>" % (self.name, self.frames,
                                                    self.rate)


_envelopes = {}
# The volume envelope fields `gunter sf2 --json` returns, generators 33 to 40
# already resolved —the instrument zone plus the preset's, with the
# specification's defaults and caps—. In SoundFont units: timecents, and
# centibels for the sustain.
ENVELOPE_FIELDS = ("env_delay_timecents", "env_attack_timecents",
                   "env_hold_timecents", "env_decay_timecents",
                   "env_sustain_centibels", "env_release_timecents",
                   "env_key_to_hold", "env_key_to_decay")


def _contract(selector, soundfont):
    """What `gunter sf2 --extract --json` says about the zone the selector
    picks, without extracting the PCM, or None if the bank has nothing there.

    It is one call per zone and is not cached on disk: without `-o` the
    binary writes nothing and answers in under a millisecond.
    """
    key = (selector, soundfont)
    if key not in _contracts:
        try:
            _contracts[key] = _json(_run(["sf2", soundfont, "--extract",
                                          selector, "--json"]))
        except Error as e:
            if "exited with 1" not in str(e):
                raise
            _contracts[key] = None
    return _contracts[key]


_contracts = {}


def preload(selectors, soundfont):
    """Asks at once for the contracts of those selectors not yet asked for.

    It is the same call as `_contract`, one per zone, but in threads: each one
    is a process of under a millisecond and the converter asks for one per
    program and key that plays, so serially what was being paid for was
    waiting for the binary to start.
    """
    import concurrent.futures
    missing = [s for s in dict.fromkeys(selectors)
               if (s, soundfont) not in _contracts]
    if len(missing) < 2:
        return
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 1) as pool:
        for _result in pool.map(lambda s: _contract(s, soundfont), missing):
            pass


def zone(selector, soundfont):
    """(sample name, its root key) of the zone the selector picks, or None.
    It is what tells one zone from another without extracting it."""
    fields = _contract(selector, soundfont)
    return (fields["name"], fields["root_key"]) if fields else None


def envelope(selector, soundfont):
    """The volume envelope of the zone the selector picks, as a dict with
    `ENVELOPE_FIELDS`, or None if the bank has nothing there."""
    key = (selector, soundfont)
    if key not in _envelopes:
        fields = _contract(selector, soundfont)
        if fields is not None:
            if any(c not in fields for c in ENVELOPE_FIELDS):
                raise SystemExit("the `gunter` on the PATH (%s) does not "
                                 "return the SoundFont envelope: it predates "
                                 "2026-09-25. Reinstall it with `just "
                                 "herramientas`." % binary())
            fields = {c: fields[c] for c in ENVELOPE_FIELDS}
        _envelopes[key] = fields
    return _envelopes[key]


def extract(selector, soundfont):
    """An instrument from the SoundFont, or None if the bank does not have it.

    The selector is the binary's: `program:N`, `program:N@NOTE` or `drum:N`.
    Nothing being there is an answer and not an error —the binary exits with
    1— and here it becomes a None, which is what the converter already knew
    how to handle.
    """
    key = (selector, soundfont)
    if key in _extracted:
        return _extracted[key]

    with tempfile.TemporaryDirectory(prefix="abl-sf2-") as tmp:
        out_path = os.path.join(tmp, "pcm.wav")
        try:
            text = _run(["sf2", soundfont, "--extract", selector,
                         "-o", out_path, "--json"])
        except Error as e:
            if "exited with 1" in str(e):
                _extracted[key] = None
                return None
            raise
        fields = _json(text)
        with wave.open(out_path, "rb") as w:
            raw = w.readframes(w.getnframes())
        pcm = [int.from_bytes(raw[i:i + 2], "little", signed=True)
               for i in range(0, len(raw), 2)]

    sample = Sample(fields, pcm)
    _extracted[key] = sample
    return sample
