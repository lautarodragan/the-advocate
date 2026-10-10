"""Only Ditto reads a Ditto dump; the other Rust projects ask its library.

A dump is a directory laid out by Ditto: `ditto.json` says it is one,
`maps.json` is the tree, `db/` holds the database's sections and
`database.json` the rest, and `maps/` holds one `MapNNNN.json` per map with
its layers in a `.tiles` beside it. `ditto::dump::Dump` is the one place
that knows that layout and reads it into the schema's types. A crate that
opens one of those files itself has a second model of the format, which
goes on reading the old shape when Ditto changes it: until 2026-09-29
`rm2k-snes-cartridge` read `maps.json` by hand for the type of each node.

**The criterion is that no crate's `src/` but Ditto's names the layout**:
none of those file names as a string literal, nor `.join("db")` or
`.join("maps")`. A crate cannot open a dump's file without naming it, so
this catches every reader by hand whatever it parses the file with, and
also a crate that builds the path and hands it to Ditto's `read_map`,
which is the same layout copied —`Dump::map` is there for that—.

What it leaves out, on purpose:

* **The tests' own directories.** A test builds a small dump to read, and
  has to name its files to write them: writing a fixture is not reading.
* **What is not the dump.** The requests the Python hands a stage
  (`--request`) are JSON of their own, and may carry pieces in the dump's
  shape —a tree node, a map a project patched—; the project's patches
  (`nuevos/MapNNNN.json`) are the project's files. Neither is named by the
  layout's names, and both are read into Ditto's types
  (`serde_json::from_value` into `MapInfo`, `read_map`), which is the part
  that matters.
* **Comments**, which may name the files to explain them.

It is a grep and not a proof: a name built from pieces
(`format!("{}.json", "maps")`) goes through. It is here to stop the obvious
way, which is the one that happened.
"""

import os
import re

# `tools/`, the folder above this one: what these tests look at.
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Ditto itself: the one that may know its layout.
DITTO = os.path.join("rm2k", "ditto")

# The layout's names, as they would be written to open one of its files.
LAYOUT = re.compile(
    r'"(ditto|maps|database)\.json"'   # the manifest, the tree, the rest
    r'|\.join\("(db|maps)"\)'          # the sections' and the maps' folders
    r'|"Map[^"]*\.json"'               # a map, by number or by format!
    r'|\.tiles"'                       # a map's layers
)


def _sources():
    """Every `.rs` under a Rust project's `src/`, but Ditto's."""
    for layer in ("snes", "rm2k", "rm2k-snes"):
        top = os.path.join(TOOLS, layer)
        for crate in sorted(os.listdir(top)):
            if os.path.join(layer, crate) == DITTO:
                continue
            src = os.path.join(top, crate, "src")
            for root, dirs, files in os.walk(src):
                dirs.sort()
                for name in sorted(files):
                    if name.endswith(".rs"):
                        yield os.path.join(root, name)


def test_only_ditto_names_the_dump_layout():
    found = []
    for path in _sources():
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if line.lstrip().startswith("//"):
                    continue
                if LAYOUT.search(line):
                    found.append("%s:%d: %s" % (
                        os.path.relpath(path, TOOLS), number,
                        line.strip()))
    assert not found, (
        "these name a file of a Ditto dump, which only Ditto may open: "
        "read it with ditto::dump::Dump instead\n" + "\n".join(found))


def test_the_sources_are_found():
    """A walk that finds nothing passes the test above without looking."""
    names = {os.path.relpath(p, TOOLS) for p in _sources()}
    assert os.path.join("rm2k-snes", "cartridge", "src", "cartridges.rs") in names
    assert not any(n.startswith(DITTO + os.sep) for n in names)
