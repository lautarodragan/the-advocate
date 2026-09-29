Emulators to test the ROM manually on Linux:

- Mednafen
- Ares
- Mesen

Ares and Mesen support the MSU1 chip. The higher quality music
can be heard with them.
So does Mednafen, but **only with the `snes_faust` module**: its default
`snes` module has no MSU-1. With `abl.msu` and the `abl-N.pcm` tracks next
to the ROM, same base name:

    mednafen -force_module snes_faust abl.sfc

Confirmed by taro on 2026-09-26: tracks and the data port both work.

On the other hand, Mednafen is more comfortable to use under Linux.
Ares and Mesen have clunky UIs.

All of them support fast-forward. Ares supports advance-by-frame,
which is helpful when debugging issues.

Both Ares and Mednafen can run from the command line:
`ares abl.sfc` and `mednafen abl.sfc` work well.
Mesen doesn't support opening roms via command line args.

## The MSU-1 data port

Besides audio tracks, the MSU-1 serves `<rom>.msu` as a byte stream: write
a 32-bit offset to `$2000..$2003` (the write to `$2003` seeks), wait for
bit 7 of `$2000` to clear, then read `$2001`, which auto-increments. DMA
with a fixed A-bus source of `$00:2001` works. Checked in the sources of the
libretro cores installed here, and by running the ROM on each:

- **bsnes** (`sfc/coprocessor/msu1/msu1.cpp`): `readIO` serves `$2001`,
  and DMA only refuses `$2100-$21FF` and the CPU registers (`validA` in
  `sfc/cpu/dma.cpp`). The libretro target maps `msu1/data.rom` to
  `<rom>.msu` and only enables the MSU-1 when that file exists.
- **snes9x** (`msu1.c`): `S9xMSU1ReadPort`. Page `$2000` is `MAP_PPU`, with
  no direct pointer, so DMA takes the slow path through `S9xGetPPU`, which
  routes `$2000-$2007` to the MSU-1.
- **mesen-s** (`Core/Msu1.cpp`): same registers; also only with a `.msu`.
- **Mednafen**: the default `snes` module has no MSU-1; `snes_faust` does
  (`-force_module snes_faust`), confirmed by taro playing the ROM.
- **ares** (`ares/sfc/coprocessor/msu1/msu1.cpp`): same registers. The
  frontend enables the MSU-1 only if a `*.msu` sits next to the ROM
  (`mia/medium/super-famicom.cpp`), so without it the tracks don't play
  either.

**Mednafen's `snes_faust` is the only one that makes seeks take time**, and
the only emulator here that exercises the ROM's waits. A write to `$2003`
sets the data-busy bit for 400,000 master cycles (`MSU1_WriteDataSeek` in
`snes_faust/msu1.cpp`), and selecting a track does the same with the
audio-busy bit. Reading `$2000` doesn't bring the MSU-1 up to date, so in
practice the bit clears at the end of the frame in which those cycles run
out: every seek costs one or two frames. bsnes, snes9x, mesen-s, Mesen2
and ares never set either bit. On the FX Pak Pro a seek outside its 16 KB
buffer reads the SD card (`prepare_data` in `src/msu1.c` of sd2snes, its
firmware).

The data port running in Mednafen was checked on 2026-09-26 by saving a
Mednafen state (F5) in the droid fight and reading the WRAM out of the
`.mc0` file: the backdrop came from the `.msu`.

## Debugging with Mesen2

Mesen2's debugger can show our routine names and, next to the
disassembly, the assembly source. It gets both from the `.dbg` file
that `ld65` leaves next to each ROM (`rom/build/release/abl.sfc.dbg`,
`rom/build/tests/<name>/prueba.sfc.dbg`).

- **It loads by itself.** With *Options > Integration > Auto-load .DBG
  files* on (the default), opening `abl.sfc` loads `abl.sfc.dbg` from
  the same folder.
- **Names work wherever the `.dbg` sits next to the ROM**, including a
  build handed over with `just entregar`. Labels inside a `.proc` lose their
  scope: Mesen2 uses the bare name and numbers the repeats, so the
  many `ready` labels show up as `ready`, `ready_2`, `ready_3`… The
  macro-local `LOCAL-MACRO_SYMBOL-*` names are skipped, since Mesen2
  rejects the dash.
- **The source shows when Mesen2 finds `tools/runtime/` above the `.dbg`.** The
  `.dbg` names each file relative to the repo root (`tools/runtime/main.s`,
  `rom/build/release/mapdata.inc`) and Mesen2 looks for that path next to
  the `.dbg`, then one folder up, and so on until it finds it. That works
  opening `rom/build/release/abl.sfc` in the clone, and also from a build
  handed over with `just entregar`, which puts the commit's `tools/runtime/` next
  to the ROM. The generated `mapdata.inc` and `musicdata.inc` are not copied
  (~15 MB), so code that lands in them only shows as disassembly there.
  *Ctrl+Q* in the code window switches between disassembly and source.

This was checked by reimplementing Mesen2's lookup (`DbgImporter.cs`,
commit `b9fa69d`) and running it against every cartridge. taro confirmed
the names in the Mesen2 UI on 2026-09-25 —disassembly, RAM variables and
call stack, stopped on a breakpoint in `wait_button`—, and the source
view with the ROM opened from `rom/build/release/`. From a `just entregar`
build the lookup finds every `.s` and misses only the two generated `.inc`
files; that was checked with the same reimplementation, not yet in the UI.

## Reporting a bug

What helps most is the **in-game save (`.srm`) made right before the
bug**, plus the steps from there. It is the cartridge's 32 KB of SRAM,
raw, so it loads anywhere: any emulator (some call it `.ram` instead of
`.srm`; it is the same content), the FX Pak, and the test harness: the
SRAM that snes9x exposes through libretro is writable, although no
helper loads a `.srm` into it yet.
Emulator savestates don't help: the harness runs snes9x through
libretro and can't load a Mednafen savestate.
