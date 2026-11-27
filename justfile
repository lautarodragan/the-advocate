# The tools' recipes: running their tests —the Python ones, which look at
# this tree, and each Rust project's— and installing the suite. A Blurred
# Line's are in its own `justfile`, which does not know this directory exists.
#
# It is called with `just <recipe>` from anywhere in the repository, and the
# recipes run standing in its root. Until 2026-10-10 the tools lived in a
# `tools/` folder and this was called with `just -f tools/justfile`.

# Where `just install` installs: `/usr/local` unless `CARGO_ROOT` says
# otherwise.
cargo_root := env_var_or_default("CARGO_ROOT", "/usr/local")

# A worktree's tools, used by the recipes in this file: they run the
# worktree's if the agent is modifying one and installed it here, with
# `just install-local <this directory>/.local-tools <project>`. Each game
# puts its own wherever
# it wants and tells `install-local` where: this file does not know where
# any of them lives.
local_tools := justfile_directory() / ".local-tools"
export PATH := if path_exists(local_tools / "bin") == "true" { local_tools / "bin" + ":" + env_var("PATH") } else { env_var("PATH") }

# The Rust projects, in the order they are installed. `project`, `rules`,
# `gunter`, `adeleine`, `voodoo`, `lz2`, `rm2k-render`, `bytecode` and
# `text` are libraries, and they go into the binaries that use them, which
# are compiled with them. So a branch that changes a library reinstalls the
# binaries that link it, not the library —its dependents in `cargo
# metadata`: `gunter`'s is `rm2k-snes-audio`, `rm2k-render`'s are most of
# the stages—; one that changes `project` reinstalls everything. `project`,
# `cartridge` and `patches` had a binary each until 2026-11-25
# —`rm2k-snes-project`, `rm2k-snes-cartridges`, `rm2k-snes-patches`—, which
# `advocate` replaced, and `images` until 2026-11-27, when the tests
# stopped asking it: installing does not remove them, `cargo uninstall
# rm2k-project rm2k-snes-cartridge rm2k-snes-patches rm2k-snes-images
# --root <root>` does.
#
# They are one Cargo workspace —`Cargo.toml`, here—, with one `Cargo.lock`
# and one `target/`, but each is still tested and installed on its own:
# `crate-test` runs `cargo test` standing in the project, which tests only
# that one, and `cargo install --locked --path` takes the workspace's lock.
rust_projects := "gunter goombario ditto rules sketch adeleine voodoo lz2 fxpak rm2k-render project bytecode cartridge patches rm2k-snes-audio battle events wally text screens images mapdata convert advocate"

# The directories the projects live in, one per layer: each project is
# `<layer>/<name>`, and the recipes find it by its name.
rust_layers := "snes rm2k rm2k-snes"

# The tools' Python tests, the ones in `tests/`: they look at this tree —the
# layers, who reads a dump, that nothing names a game— and need neither a
# game, nor its data, nor a built cartridge. Those that do are among A
# Blurred Line's. They are fast, so they run serially and without xdist.
#
# None reads a SoundFont any more: the music's that do are in Rust, in
# `crate-test rm2k-snes-audio`, and get it the same way, in `SOUNDFONT`.
# `pytest` takes `tests/` from `pytest.ini`, so whatever is passed to it —a
# file, `-k`— works the same as in a plain `pytest`.
#
# The tools' Python tests, the ones that look at this tree.
test *args:
  pytest {{args}}

# The test game's: it makes the game out of its text, builds its cartridge
# with the installed tools and runs it in an emulator. Not inside `test`,
# which runs no ROM and needs nothing from the machine: this one needs a
# libretro core and a SoundFont, in `SOUNDFONT`, like the audio tests. Its
# recipes are in `test-game/justfile`.
#
# The test game: build it and run its tests in an emulator.
test-game *args:
  just -f test-game/justfile test {{args}}

# Every Rust project's tests at once, the whole workspace, in the debug
# profile: the release one is `lto` and a single codegen unit, and compiling
# every test binary that way costs more than the tests save. The ones that
# need a game or a SoundFont are skipped the same way as in `crate-test`,
# unless `DITTO_CORPUS` or `SOUNDFONT` are set.
#
# Every Rust project's tests, the whole workspace.
rust-test *args:
  cargo test --workspace {{args}}

# What CI checks of the Rust before building it: the formatting, with the
# default rustfmt config —there is no rustfmt.toml, on purpose—, and clippy
# over every target with its warnings as errors. The lints the workspace
# does not follow are in `[workspace.lints.clippy]` of `Cargo.toml`, each
# with its why; an exception for one item goes on the item, with its own.
# `cargo fmt --all` fixes the first.
#
# rustfmt and clippy over the workspace.
lint-rust:
  cargo fmt --all --check
  cargo clippy --workspace --all-targets -- -D warnings

# Goombario over the runtime, which needs it assembled: over every cartridge
# of the test game, built with the installed tools —`lint` in
# `test-game/justfile` says why every one, and which runtime—. So it needs
# what the test game needs to build, `ca65`, `ld65` and a SoundFont in
# `SOUNDFONT`, and no core. With the cache, after a change to the runtime it
# is little more than assembling.
#
# Goombario over the runtime, in the test game's cartridges.
lint-runtime:
  just -f test-game/justfile lint

# Both, before pushing. In CI `lint-rust` is a job of its own and
# `lint-runtime` goes in the test game's, which has cc65 and the tools.
#
# rustfmt, clippy and Goombario.
lint: lint-rust lint-runtime

# One Rust project's tests, by its name in `rust_projects` —`just
# crate-test lz2`—, standing in its directory, which tests only that one;
# whatever follows the name goes to `cargo test`. What each one's tests need
# is in its README or its `lib.rs`: none needs a game, and the ones that
# can use one —Ditto's corpus, a real SoundFont for `rm2k-snes-audio`— get
# it in `DITTO_CORPUS` and `SOUNDFONT`, and skip without it.
#
# In the debug profile, like `rust-test`: the three whose recipes used to
# run in release —`lz2`, `rm2k-render`, `rm2k-snes-audio`— take a second or
# two in debug too.
#
# One Rust project's tests, by its name.
crate-test project *args:
  #!/usr/bin/env sh
  set -eu
  for layer in {{rust_layers}}; do
    if [ -f "$layer/{{project}}/Cargo.toml" ]; then
      cd "$layer/{{project}}"
      exec cargo test {{args}}
    fi
  done
  echo "'{{project}}' is not a Rust project: they are {{rust_projects}}." >&2
  exit 1

# --- Installation ----------------------------------------------------------
# The Rust projects, in `snes/`, `rm2k/` and `rm2k-snes/`, are separate
# projects, and the port consumes them **from the PATH**, the way it
# consumes a libretro core: no script or test of the game calls `cargo`.
# They are installed once and stay. Nothing else is installed: since
# 2026-10-02 the suite has no Python scripts.
#
# With Rust project names —`just install wally`— it installs only those: that
# is what whoever merges a branch runs, with the Rust the branch touched.
# Without names, all of them.
#
# The suite's programs that are not a project of their own are called
# `rm2k-snes-<something>`: `bin/` is shared, and a bare `events` or `images`
# does not say what it is and can clash with anything. `advocate` is the
# exception, on purpose: it is the one a person types, named after the
# project and its `advocate.toml`.
#
# **And the games' test harness**, the Python package `rm2k_snes_harness`
# (`rm2k-snes/harness/`), whatever the names: `_install` links it beside
# `bin/`, and this puts that link on Python's import path with a `.pth` in
# its `site-packages`, so a game's tests and scripts `import` it as they
# import any package, and ask no binary where it is. taro's, 2026-11-25:
# the tests never call a binary of ours. It is a link to this checkout, the
# same one whose runtime the cartridges carry, so the harness and the
# symbols it reads always come from one checkout.
#
# `(cargo_root)` goes in parentheses because, stuck to the parenthesis that
# follows, `just` would read it as a call to a function `cargo_root`.
#
# Installs the named Rust projects, or all of them, into CARGO_ROOT.
install *projects: (_install (cargo_root) (if projects == "" { rust_projects } else { projects })) && _harness_on_python_path

# The `.pth` that puts `CARGO_ROOT`'s harness on every Python's import path:
# `site-packages` reads it when Python starts.
_harness_on_python_path:
  #!/usr/bin/env sh
  set -eu
  site=$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
  echo "{{cargo_root}}/lib/advocate/harness" >"$site/rm2k_snes_harness.pth"
  echo "the games' harness, rm2k_snes_harness, on Python's path: $site/rm2k_snes_harness.pth"

# **A worktree's tools**, for the sub-agent that modifies them. The global
# install was built from a single checkout —the main one—, so a worktree
# that changes a Rust project would not run its change. This builds
# `<dest>/bin/` with the Rust projects it is given, **only those**:
# compiling Rust costs, and only makes sense if the agent is going to
# modify that project. Without names it compiles nothing. From taro,
# 2026-09-29. It always links the worktree's harness, `rm2k_snes_harness`,
# in `<dest>/lib/advocate/harness`, as `install` does in the global root:
# a game's tests take the one beside the first `advocate` of their PATH
# (Python's own path does not follow the PATH, and only the global one is
# in its `site-packages`).
#
# **The destination is set by the consumer**, and it is mandatory: this file
# does not know where the game lives, and the game does not know where this
# one lives. A game either puts the `bin/` first on its PATH or has its
# `justfile` look for it in a directory of its own. A relative destination
# is relative to where `just` was run, not to the repository.
#
# It only applies to what runs through `just`, which is what puts the `bin/`
# first on the PATH: a plain command uses the global one. It refuses in the
# main checkout, where it would shadow the global install with the same
# thing.
#
# Installs the named Rust projects into <dest>/bin, for a worktree.
install-local dest *projects: _not_in_main_checkout (_install (join(invocation_directory(), dest)) projects)

_not_in_main_checkout:
  #!/usr/bin/env sh
  [ "$(git rev-parse --path-format=absolute --git-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ] && exit 0
  echo "this is the main checkout: here the tools are the global ones, from 'just install'." >&2
  exit 1

# Installs into `root`: `cargo install` of the named Rust projects. A name
# that is not a project stops before compiling anything.
_install root *projects:
  #!/usr/bin/env sh
  set -eu
  for p in {{projects}}; do
    case " {{rust_projects}} " in
      *" $p "*) ;;
      *) echo "'$p' is not a Rust project: they are {{rust_projects}}." >&2; exit 1 ;;
    esac
  done
  mkdir -p "{{root}}/bin"
  for p in {{projects}}; do
    dir=""
    for layer in {{rust_layers}}; do
      if [ -f "$layer/$p/Cargo.toml" ]; then dir="$layer/$p"; fi
    done
    # A library has nothing to install: it goes into the binaries that use it.
    if [ ! -f "$dir/src/main.rs" ] && [ ! -d "$dir/src/bin" ] && ! grep -q '^\[\[bin\]\]' "$dir/Cargo.toml"; then
      echo "$p is a library: it is compiled into the binaries that use it"
      continue
    fi
    cargo install --locked --path "$dir" --root "{{root}}"
  done
  echo "in {{root}}/bin, from Rust: {{ if projects == "" { "none" } else { projects } }}"
  # The games' test harness: a link, so the checkout's Python is what runs,
  # as it is edited. See `install`.
  mkdir -p "{{root}}/lib/advocate"
  ln -sfn "{{justfile_directory()}}/rm2k-snes/harness" "{{root}}/lib/advocate/harness"
  echo "in {{root}}/lib/advocate/harness, the games' test harness: this checkout's"
