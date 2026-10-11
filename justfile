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

# The Rust projects, in the order they are installed. `project` and `rules`
# are libraries, and they go into the binaries that use them —`project`
# into `cartridge`'s and the others', `rules` into `rm2k-render` and
# `battle`—, which are compiled with them. So a branch that changes `rules`
# reinstalls those two, not `rules`; one that changes `project` reinstalls
# everything, and `project` too, for its one binary, `rm2k-snes-project`,
# which answers what a game's tests ask about the project.
#
# They are one Cargo workspace —`Cargo.toml`, here—, with one `Cargo.lock`
# and one `target/`, but each is still tested and installed on its own:
# `crate-test` runs `cargo test` standing in the project, which tests only
# that one, and `cargo install --locked --path` takes the workspace's lock.
rust_projects := "gunter goombario ditto rules adeleine voodoo lz2 rm2k-render project bytecode cartridge patches rm2k-snes-audio battle events wally text screens images mapdata convert"

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

# Every Rust project's tests at once, the whole workspace, in the debug
# profile: the release one is `lto` and a single codegen unit, and compiling
# every test binary that way costs more than the tests save. The ones that
# need a game or a SoundFont are skipped the same way as in `crate-test`,
# unless `DITTO_CORPUS` or `SOUNDFONT` are set.
#
# Every Rust project's tests, the whole workspace.
rust-test *args:
  cargo test --workspace {{args}}

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

# Ditto's short suite runs over a sample of maps; this is every map, the LDB
# and the tree, and measures the only thing that makes the tool useful: that
# the binary comes back **byte for byte**. It is separate because it is the
# one you want to see with the number, not the one that runs quietly; and
# without a corpus it measures nothing, so instead of skipping it refuses.
#
# Every file of DITTO_CORPUS back to binary, byte for byte.
ditto-round-trip:
  #!/usr/bin/env sh
  set -eu
  if [ -z "${DITTO_CORPUS:-}" ]; then
    echo "ditto-round-trip needs a game: DITTO_CORPUS=<folder with RPG_RT.ldb, RPG_RT.lmt and the Map*.lmu>." >&2
    exit 1
  fi
  cd rm2k/ditto
  cargo test --release -- --include-ignored --nocapture

# --- Installation ----------------------------------------------------------
# The Rust projects, in `snes/`, `rm2k/` and `rm2k-snes/`, are separate
# projects, and the port consumes them **from the PATH**, the way it
# consumes a libretro core: no script or test of the game calls `cargo`.
# They are installed once and stay. Nothing else is installed: since
# 2026-10-02 the suite has no Python scripts.
#
# With Rust project names —`just install lz2`— it installs only those: that
# is what whoever merges a branch runs, with the Rust the branch touched.
# Without names, all of them.
#
# The suite's programs that are not a project of their own are called
# `rm2k-snes-<something>`: `bin/` is shared, and a bare `space` or `patches`
# does not say what it is and can clash with anything.
#
# `(cargo_root)` goes in parentheses because, stuck to the parenthesis that
# follows, `just` would read it as a call to a function `cargo_root`.
#
# Installs the named Rust projects, or all of them, into CARGO_ROOT.
install *projects: (_install (cargo_root) (if projects == "" { rust_projects } else { projects }))

# **A worktree's tools**, for the sub-agent that modifies them. The global
# install was built from a single checkout —the main one—, so a worktree
# that changes a Rust project would not run its change. This builds
# `<dest>/bin/` with the Rust projects it is given, **only those**:
# compiling Rust costs, and only makes sense if the agent is going to
# modify that project. Without names it compiles nothing. From taro,
# 2026-09-29.
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

# Which executable this checkout resolves for each tool: the one in
# `.local-tools/bin/` if it is there, otherwise the global one.
#
# Which executable this checkout resolves for each tool.
which:
  #!/usr/bin/env sh
  for x in gunter goombario ditto adeleine voodoo lz2 rm2k-render rm2k-snes-cartridges rm2k-snes-assemble rm2k-snes-space rm2k-snes-convert rm2k-snes-patches rm2k-snes-audio rm2k-snes-msu rm2k-snes-volume-ceilings rm2k-snes-battle rm2k-snes-events wally rm2k-snes-screens rm2k-snes-images rm2k-snes-mapdata rm2k-snes-project; do
    printf '%-26s %s\n' "$x" "$(command -v "$x" || echo missing)"
  done
