"""Running a stage of the converter, for a test that asks it something.

Each domain of the conversion is an executable on the PATH that
`rm2k-snes-convert` calls: it reads the game from the dump itself, gets a
JSON request, and writes what it made into a directory —pieces of the
`.inc` and a JSON with what it answers—. This runs one of those and hands
back what it wrote. It was the converter's `port/stage.py` until the
converter moved to Rust on 2026-10-02.

The first one was `rm2k-snes-battle`; see its README, "One stage of a
converter", for the shape.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

MISSING = """`%s` is missing, one of the converter's stages.

It is a Rust binary of the suite, and is installed as a system tool,
with the suite's `install`: its project is `%s`."""


def run(binary, project, command, request, *flags, raw=False):
    """`binary command --request <request> --out <dir> *flags`, and
    `{name: text}` of every file it wrote —`{name: bytes}` with `raw`, for a
    stage that writes tiles and pictures—. `project` is the name `install`
    knows it by, for the message when it is not on the PATH.

    What it answers no to stops the conversion with its message."""
    path = shutil.which(binary)
    if path is None:
        raise SystemExit(MISSING % (binary, project))
    with tempfile.TemporaryDirectory(prefix=binary + "-") as directory:
        request_path = os.path.join(directory, "request.json")
        with open(request_path, "w") as handle:
            json.dump(request, handle)
        out = os.path.join(directory, "out")
        # What this printed goes before what the binary prints.
        sys.stdout.flush()
        done = subprocess.run([path, command, "--request", request_path,
                               "--out", out] + list(flags),
                              capture_output=True, text=True)
        if done.returncode:
            # The binary's message already starts with its name.
            raise SystemExit(done.stderr.strip()
                             or "%s %s exited with %d"
                             % (binary, command, done.returncode))
        written = {}
        for name in sorted(os.listdir(out)):
            with open(os.path.join(out, name), "rb" if raw else "r") as handle:
                written[name] = handle.read()
        return written

