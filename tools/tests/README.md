# The tools' tests

    just -f tools/justfile test               all of them; standing in tools/, `just test`
    just -f tools/justfile test -k escapes    the usual pytest arguments pass through as is

The Python ones: the converter, the assembly and the runtime, tested without
the game. The Rust projects' tests each have their own recipe
(`protocol-test`, `ditto-test`…).

**A test goes here if it does not read the game** —neither `ABL_GAME_DIR`,
nor the RTP—, **nor `rom/data/`, nor `rom/parches/`, nor a built cartridge,
nor the suite**. Everything it looks at it builds inside, or reads from
`tools/` and from the runtime. The ones that need any of that belong to A
Blurred Line's tests, in `rom/pruebas/`, even if they test a tool. A file
that mixes both gets split: the two sides of the same topic can have the
same name, each in its own language, or one that says what it looks at in
the game —`test_protocol.py` here and `test_protocolo_contra_el_juego.py` in
ABL's—.

They run no ROM and take less than a second, so they run serially and
without xdist. ABL's suite does not run them, and they need nothing from
ABL: that is why they do not ask `rm2k-snes-cartridges` anything either.

What they do use from outside: `test_protocol.py` runs `protocol` from the
PATH, and `test_layers.py` runs `cargo metadata`, which reads only the
workspace's manifests. The music stream's tests, which read a SoundFont, are
in Rust, in `rm2k-snes/rm2k-snes-audio/`: `just audio-test`.
`test_protocol.py` and `test_substitutions.py` also read the runtime, in `tools/runtime/`, which
travels with the tools: the files it is made of are the ones
`rm2k-snes-assemble --sources` lists, from the PATH, glued together by the
`runtime_source` fixture of `conftest.py`. The bank packing and the rest of
what builds a cartridge are tested in Rust, in `rm2k-snes/cartridge/`.

## Which test covers what

Every `test_*.py` in this folder has to be named here, and everything named
has to exist: `test_index.py` enforces it.

* `test_protocol.py`: the bytecode: the generated files up to date, that
  the runtime does not use an undeclared opcode, and that the two
  declarations share no name; what a declaration checks on its own is in
  `protocol`'s tests
* `test_vram_layouts.py`: the VRAM layouts, their order and the maps that
  introduced them
* `test_substitutions.py`: the `TileSubstitution` cap, the same in the
  converter and in the runtime
* `test_texts.py`, `test_escapes.py`: the rebuilt text boxes and the `\|`
  and `\^` escapes
* `test_inherited_songs.py`: which song may be playing when each map's
  package is loaded, which is what the layout reserves for it
* `test_project.py`: that where each thing is —the root, the repo's
  folders— is known only to `common/project.py`, that no tool reads the
  environment on its own, and that none knows about A Blurred Line: no
  `ABL_*` variable, no `rom/` as a path
* `test_settings.py`: that the project file reader, `common/settings.py`,
  fails with the key's name instead of falling back to a default value
* `test_layers.py`: that the Rust projects' layers only depend downwards:
  `snes/` and `rm2k/` on nothing of the other two, `rm2k-snes/` on both;
  and that neither of the first two names `rm2k-snes.toml`
* `test_dump_readers.py`: that no Rust project but Ditto names a file of
  a Ditto dump: the others read it with `ditto::dump::Dump`
* `test_rm2k_rules.py`: that the RPG Maker rules the converter uses in
  Python —`rpgmaker/rm2k.py` and the few in `lcf.py`, `render_map.py` and
  `experience.py`— still answer what `rm2k-rules`, their Rust copy, is
  held to, in `rm2k/rules/tests/python.json`
* `test_index.py`: that this list is up to date
