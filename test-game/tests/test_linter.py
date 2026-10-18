"""Goombario over the runtime: the traps that assemble fine and are wrong.

`goombario` —from the PATH, like any tool— reads the built cartridge, its
`.dbg` and the source, and flags four things: a conditional branch on a
flag a `pl*` left (the trap of AGENTS.md that bit four times), a routine
entered with `jsl` that returns with `rts` or the other way round, a path
that leaves bytes on the stack or pulls too many, and a width of A or of
X/Y that is not the one the source declares. Its README, in
`snes/goombario/`, says how it looks at each one and what it does not see.

What is fine and gets flagged anyway goes in `linter-exceptions.txt`, next
to `rm2k-snes.toml`, each thing with its why; an exception that no longer
covers anything also makes it fail, so that the list does not grow on its
own. Only the runtime is looked at: what the converter generates is data.

A Blurred Line's `tests/tooling/test_linter.py`, in the ports' repo, does
the same over that game's cartridges, and this one comes from it.
"""

import os
import re
import subprocess

from game import ROOT, cartridge, listing

EXCEPTIONS = os.path.join(ROOT, "linter-exceptions.txt")


def test_the_runtime_falls_in_no_trap():
    # Where `ca65` ran: the source paths in the `.dbg` are relative to it.
    root = listing()["root"]
    runtime = os.path.relpath(listing()["runtime"], root) + "/"
    done = subprocess.run(
        ["goombario", cartridge().rom, "--root", root, "--only", runtime,
         "--allow", EXCEPTIONS, "--stats"],
        capture_output=True, text=True)
    assert done.returncode != 2, done.stderr
    assert done.returncode == 0, "\n" + done.stdout
    # And that it looked at something: a badly read `.dbg` gives zero
    # without checking anything, which is what happened to the first
    # version of the banks' guard, in that game.
    seen = {k: int(v) for k, v in re.findall(
        r"(instructions|pulls|entries|returns reached) (\d+)", done.stderr)}
    assert all(seen.get(k, 0) > 100 for k in
               ("instructions", "pulls", "entries", "returns reached")), (
        done.stderr)
