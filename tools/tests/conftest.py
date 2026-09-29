"""What more than one of the tools' tests uses."""

import os
import subprocess

import pytest

from common import project


@pytest.fixture(scope="session")
def runtime_source():
    """The runtime's hand-written source glued together, as if it were a
    single file: `main.s` and the `.s` files it includes, in the order `ca65`
    reads them. The list is `rm2k-snes-assemble --sources`, from the PATH
    like `protocol`: which files the ROM is made of is the assembler's
    answer, and nobody else's."""
    main = os.path.join(project.runtime(), "main.s")
    paths = subprocess.run(["rm2k-snes-assemble", "--sources", main],
                           check=True, capture_output=True,
                           text=True).stdout.splitlines()
    parts = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            parts.append(handle.read())
    return "".join(parts)
