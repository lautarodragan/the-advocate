# The tools' tests

    just test               all of them
    just test -k escapes    the usual pytest arguments pass through as is

The Python ones, and the only Python left in the repository: they look at this
tree —its layers, who reads a dump, that nothing names a game— the way a
crate's tests look at the crate. They import nothing: the repository is
the folder above this one. The Rust projects' tests run one by one with
`crate-test <project>`, or all together with `rust-test`.

**A test goes here if it does not read a game** —neither its original
files, nor the RTP—, **nor its dump, nor its patches, nor a built
cartridge, nor the suite**. Everything it looks at it builds inside, or
reads from the repository and from the runtime. The ones that need any of that
belong, until the test game exists, to A Blurred Line's tests, in its own
repo, even if they test a tool. A file
that mixes both gets split: the two sides of the same topic can have the
same name, each in its own language, or one that says what it looks at in
the game.

They run no ROM and take less than a second, so they run serially and
without xdist. ABL's suite does not run them, and they need nothing from
ABL: that is why they do not ask `rm2k-snes-cartridges` anything either.

What they do use from outside: `test_layers.py` runs `cargo metadata`,
which reads only the workspace's manifests. The music stream's tests, which
read a SoundFont, are in Rust, in `rm2k-snes/rm2k-snes-audio/`: `just
crate-test rm2k-snes-audio`. The bytecodes are checked where they are declared, in
`rm2k-snes/bytecode/`, and so is the runtime's use of them. The bank packing
and the rest of what builds a cartridge are tested in Rust, in
`rm2k-snes/cartridge/`.

## Which test covers what

Every `test_*.py` in this folder has to be named here, and everything named
has to exist: `test_index.py` enforces it.

* `test_no_game_names.py`: that no file of the tools names A Blurred Line
  —its characters, places, pictures, its name— outside a comment: a test
  uses invented names and a fixture invented content. Comments and `.md`
  files may cite it; the few lines that may too are listed with their reason
* `test_layers.py`: that the Rust projects' layers only depend downwards:
  `snes/` and `rm2k/` on nothing of the other two, `rm2k-snes/` on both;
  and that neither of the first two names `rm2k-snes.toml`
* `test_dump_readers.py`: that no Rust project but Ditto names a file of
  a Ditto dump: the others read it with `ditto::dump::Dump`
* `test_test_game_assets.py`: that every picture, song and sound in
  `test-game/` has its line in `test-game/AUTHORS.md` —author, license,
  link, changes— and that every line there is a file. The test game's own
  tests run its cartridge, so they are not here: `just test-game`
* `test_index.py`: that this list is up to date
