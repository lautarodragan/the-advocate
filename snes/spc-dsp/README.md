# spc-dsp: the S-DSP on its own

The Super NES's sound chip, without the SPC700 that usually drives it:
64 KB of ARAM in, writes to its 128 registers, so many clocks, and the
stereo samples that come out, one pair every 32 clocks.

    let mut dsp = spc_dsp::Dsp::new(aram);
    dsp.write(0x6C, 0x20);
    let samples = dsp.run(17_040);

`cargo test`; it needs a C++ compiler, which the `cc` crate finds. It is a
library and not a command: `rm2k-snes-audio` measures each song's volume
ceiling with it, playing what the song writes to the DSP —see
`src/ceilings.rs` there—.

## What runs

blargg's `SPC_DSP`, the accurate S-DSP of **snes_spc 0.9.0** (2007, Shay
Green), in `vendor/snes_spc/` exactly as it came: `SPC_DSP.cpp`,
`SPC_DSP.h` and the four `blargg_*.h` it includes, with its licence,
`license.txt`. The rest of snes_spc —the SPC700, the `.spc` player, the
filter— is not here. `src/shim.cpp` gives it a C face of four functions,
and `src/lib.rs` wraps those in `Dsp`, guarding the three things of the
class that bite from Rust:

* `run(0)` does not return: it counts down through four billion clocks.
  `Dsp::run(0)` does not call it.
* The class brings its own `operator new`, which returns NULL instead of
  throwing, and `new (std::nothrow)` does not compile against it. `Dsp::new`
  panics on NULL.
* `reset()` loads the power-on registers measured on a console, KON among
  them, so whatever is in the registers at the first `run` plays. That one
  cannot be guarded here: whoever drives it writes its boot registers
  before the first run, as `Dsp::new` says.

It is compiled with `NDEBUG`, which turns blargg's `assert` and `require`
off, without exceptions or RTTI, and links no C++ runtime: the static
library needs only `malloc`, `free`, `memcpy`, `memset` and
`__stack_chk_fail` from the C library.

## Where the sources come from, and what was checked

blargg's site, slack.net, does not answer, and the Wayback Machine has
only 404s for `snes_spc-0.9.0.zip` since 2021, so the files come from a
third party's mirror on GitHub, `yupferris/snes_spc`, at its **first
commit, `8f0ea63`** (2013-11-12), which is snes_spc 0.9.0 with a Visual
Studio demo added beside it; the commits after it rewrite the library.
Checked on 2026-11-27, before they were taken:

* The six files carry the snes_spc 0.9.0 header and the LGPL 2.1 notice,
  Copyright 2007 Shay Green.
* `SPC_DSP.cpp` differs from the copy in bsnes only in bsnes's own known
  changes: the power-on table zeroed, cubic interpolation, a second echo
  pointer. That is what an untouched 0.9.0 would show. Against Mesen-S's
  it differs in 107 lines, and snes9x's copy is reworked.
* They include only `assert`, `limits`, `stdint`/`inttypes`, `string`,
  `stddef`, `stdlib` and `new`. Their only `asm` is PowerPC-only, behind a
  guard. They have no file, network, process or environment calls.
* The build is the `cc` crate compiling two files; it downloads nothing.

**What was not checked**: the original zip, so there is no hash to compare
the files against; the mirror is not signed, and its first commit is that
third party's import. Nobody read the DSP's algorithm line by line: it was
only searched for what it calls. And the build that checked it ran as
root. What does not depend on any of that is the comparison the model was
taken on: its output against the ROM's in an emulator, sample for sample,
until the first write that lands at a different moment inside its frame
—`tasks/the-volume-ceilings-are-measured-without-a-rom.md` in
the-advocate-work—.

## Licence

snes_spc is under the **GNU LGPL 2.1 or later**, `vendor/snes_spc/license.txt`.
The LGPL lets its code go into a work under the GPL, and the-advocate is
**GPL-3.0-or-later** (`LICENSE`, at the root), so the binaries that link
this —`advocate`— are too, and their whole source, this included, is the
repository. The releases carry the LGPL's text and a notice that they
contain snes_spc, `NOTICE` here: see `.github/workflows/release.yml`.

Rewriting it in Rust would not get out of the LGPL: a translation is a
derived work.
