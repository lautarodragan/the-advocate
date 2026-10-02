#!/usr/bin/env python3
"""Prints the directory the suite's Python packages —`common` and
`emulator`— are imported from, for a game to put on its `sys.path`.

A game's tests import those packages, and the game does not know where the
tools live: it lives in its own repo and knows executables on the PATH. So
it asks this one, installed as `rm2k-snes-python-path` like the rest of the
suite. `install` puts it on the PATH as a symlink, so it answers for the
checkout it was installed from: the same one the Rust binaries take the
runtime from.
"""

import os

# `realpath` and not `abspath`: what is executed is the symlink in `bin/`,
# and what matters is where the real file is. This file lives in `common/`,
# and the packages are imported from the directory above it.
print(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
