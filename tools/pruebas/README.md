# The tools' tests

    just -f tools/justfile pruebas               all of them; standing in tools/, `just pruebas`
    just -f tools/justfile pruebas -k escapes    the usual pytest arguments pass through as is

The Python ones: the converter, the assembly and the runtime, tested without
the game. The Rust projects' tests each have their own recipe
(`protocolo-pruebas`, `ditto-pruebas`…).

**A test goes here if it does not read the game** —neither `ABL_GAME_DIR`,
nor the RTP—, **nor `rom/data/`, nor `rom/parches/`, nor a built cartridge,
nor the suite**. Everything it looks at it builds inside, or reads from
`tools/` and from the runtime. The ones that need any of that belong to A
Blurred Line's tests, in `rom/pruebas/`, even if they test a tool. A file
that mixes both gets split: the two sides of the same topic can have the
same name —`test_bancos.py`— or one that says what it looks at in the game
—`test_protocolo_contra_el_juego.py`—.

They run no ROM and take less than a second, so they run serially and
without xdist. ABL's suite does not run them, and they need nothing from
ABL: that is why they do not depend on `cartuchos` either.

What they do use from outside: `test_protocolo.py` runs `protocol` from the
PATH, and `test_musica_stream.py` reads the samples' SoundFont with
`gunter`, from the PATH, from wherever `ABL_SOUNDFONT` says. The SoundFont
does not belong to the game but is material for the converter, even though
the variable still carries ABL's name. `test_protocolo.py` and
`test_sustituciones.py` also read the runtime, in `tools/runtime/`, which
travels with the tools.

## Which test covers what

Every `test_*.py` in this folder has to be named here, and everything named
has to exist: `test_indice.py` enforces it.

* `test_protocolo.py`: the bytecode: the declarations, the generated files
  up to date, that both ends say the same numbers and that the runtime does
  not use an undeclared opcode
* `test_ensamblar.py`: `ensamblado/ensamblar.py`: the checksum, the header,
  the `.dbg` symbols and which sources are included
* `test_bancos.py`: the bank packing the converter does, and the `.cfg`
  memory map
* `test_repartos.py`: the VRAM layouts, their order and the maps that
  introduced them
* `test_sustituciones.py`: the `TileSubstitution` cap, the same in the
  converter and in the runtime
* `test_textos.py`, `test_escapes.py`: the rebuilt text boxes and the `\|`
  and `\^` escapes
* `test_temas_heredados.py`: which song may be playing when each map's
  package is loaded, which is what the layout reserves for it
* `test_musica_stream.py`: the stream the converter builds: which voice each
  note goes to, when it is released and with which envelope
* `test_proyecto.py`: that where each thing is —the root, the repo's
  folders— is known only to `common/project.py`, that no tool reads the
  environment on its own, and that none knows about A Blurred Line: no
  `ABL_*` variable, no `rom/` as a path
* `test_perillas.py`: that the project file reader, `common/settings.py`,
  fails with the key's name instead of falling back to a default value
* `test_indice.py`: that this list is up to date
