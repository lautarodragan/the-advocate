Emulators to test the ROM manually on Linux:

- Mednafen
- Ares
- Mesen

Ares and Mesen support the MSU1 chip. The higher quality music
can be heard with them.
Mednafen doesn't.

On the other hand, Mednafen is more comfortable to use under Linux.
Ares and Mesen have clunky UIs.

All of them support fast-forward. Ares supports advance-by-frame,
which is helpful when debugging issues.

Both Ares and Mednafen can run from the command line:
`ares abl.sfc` and `mednafen abl.sfc` work well.
Mesen doesn't support opening roms via command line args.

## Debugging with Mesen2

Mesen2's debugger can show our routine names and, next to the
disassembly, the assembly source. It gets both from the `.dbg` file
that `ld65` leaves next to each ROM (`rom/build/release/abl.sfc.dbg`,
`rom/build/tests/<name>/prueba.sfc.dbg`).

- **It loads by itself.** With *Options > Integration > Auto-load .DBG
  files* on (the default), opening `abl.sfc` loads `abl.sfc.dbg` from
  the same folder.
- **Names work wherever the `.dbg` sits next to the ROM**, including a
  build copied to `/shared/builds/`. Labels inside a `.proc` lose their
  scope: Mesen2 uses the bare name and numbers the repeats, so the
  many `listo` labels show up as `listo`, `listo_2`, `listo_3`… The
  macro-local `LOCAL-MACRO_SYMBOL-*` names are skipped, since Mesen2
  rejects the dash.
- **The source shows when Mesen2 finds `rom/src/` above the `.dbg`.** The
  `.dbg` names each file relative to the repo root (`rom/src/main.s`,
  `rom/build/release/mapdata.inc`) and Mesen2 looks for that path next to
  the `.dbg`, then one folder up, and so on until it finds it. That works
  opening `rom/build/release/abl.sfc` in the clone, and also from a build
  in `/shared/builds/`: `just entregar` puts the commit's `rom/src/` next to
  the ROM. The generated `mapdata.inc` and `musicdata.inc` are not copied
  (~15 MB), so code that lands in them only shows as disassembly there.
  *Ctrl+Q* in the code window switches between disassembly and source.

This was checked by reimplementing Mesen2's lookup (`DbgImporter.cs`,
commit `b9fa69d`) and running it against every cartridge. taro confirmed
the names in the Mesen2 UI on 2026-09-25 —disassembly, RAM variables and
call stack, stopped on a breakpoint in `espera_boton`—, and the source
view with the ROM opened from `rom/build/release/`. From a `/shared/builds/`
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
