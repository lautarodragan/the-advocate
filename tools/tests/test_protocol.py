"""The bytecode declarations, their generated files and the runtime agree.

There are two bytecodes in this port: the event one, which
`rm2k-snes-events` emits and the ROM interprets, and the music stream,
which `rm2k-snes-audio` writes and `irq_music` reads. They are declared by
`tools/snes/protocol/`, which belongs to neither side, and from there the
files in `GENERATED` are generated and committed, so building the ROM does
not need the generator.

What `protocol` checks about a declaration on its own —two opcodes on one
number, the sizes derived from the layout, the gaps of a jump table— is in
its own tests. What is left here is what only this tree can check: that the
committed files are what the declarations give today, that the runtime uses
only declared opcodes, and that the two declarations do not collide in the
one symbol space the assembler has. What **cannot** be generated is what
each opcode does: that is hand-written 65816.
"""

import os
import re
import subprocess
import tomllib

import pytest  # noqa: E402

from common import project  # noqa: E402

PROTOCOL = os.path.join(project.tools(), "snes", "protocol")

# Each declaration and the flags it is generated with, as in the `protocol`
# recipe of tools/justfile: with `--check`, a file the recipe writes and this
# does not name reads as stale.
GENERATED = {
    "events": ["--python", os.path.join(project.tools(), "port", "event_opcodes.py"),
               "--asm", os.path.join(project.runtime(), "event_opcodes.inc"),
               "--rust", os.path.join(project.tools(), "rm2k-snes", "events", "src",
                                      "opcodes.rs"),
               "--jump-table"],
    "music": ["--asm", os.path.join(project.runtime(), "music_opcodes.inc"),
              "--rust", os.path.join(project.tools(), "rm2k-snes", "rm2k-snes-audio",
                                     "src", "music_opcodes.rs")],
}


def declared(name):
    """The opcode names a declaration has, read from its TOML."""
    with open(os.path.join(PROTOCOL, name + ".toml"), "rb") as handle:
        return {op["name"] for op in tomllib.load(handle)["opcode"]}


@pytest.mark.parametrize("name", sorted(GENERATED))
def test_the_generated_files_are_up_to_date(name):
    """Regenerating changes nothing: otherwise the tree has two truths."""
    done = subprocess.run(
        ["protocol", os.path.join(PROTOCOL, name + ".toml"), "--check"]
        + GENERATED[name],
        capture_output=True, text=True)
    assert done.returncode != 2, (
        "the generator could not run —is `just -f tools/justfile install` missing?—:\n%s"
        % done.stderr)
    assert done.returncode == 0, (
        "a generated file is out of date:\n%s%s" % (done.stdout, done.stderr))


def test_no_opcode_in_the_rom_is_undeclared(runtime_source):
    """A `cmp #OP_X` against something nobody declares does not assemble...

    ...today. But the day someone puts equates back by hand, or in a file the
    converter generates, it would assemble again reading a number written
    twice, which is what this leaves behind. Both bytecodes together: to the
    ROM they are a single symbol space, and in fact that is why `OP_FIN` had
    to be called `OP_DONE` —`OP_END` already belonged to the music stream—.
    """
    source = runtime_source
    # Only the uses as an operand: bare names in comments do not count.
    used = set(re.findall(r"#(OP_[A-Z0-9_]+)\b", source))
    assert used, "not a single use of an opcode was found in tools/runtime/"
    everything = set()
    for name in GENERATED:
        everything |= declared(name)
    # And that no hand-written one has reappeared in the ROM itself.
    own = set(re.findall(r"^(OP_[A-Z0-9_]+)\s*=", source, re.M))
    assert not own, (
        "tools/runtime/ declares %s by hand: that goes in tools/snes/protocol/"
        % ", ".join(sorted(own)))
    undeclared = used - everything
    assert not undeclared, (
        "tools/runtime/ compares against %s, which is not declared in tools/snes/protocol/"
        % ", ".join(sorted(undeclared)))


def test_the_two_bytecodes_share_no_name():
    """Both land in the same assembler symbol space.

    The numbers may repeat —`OP_DSP` and `OP_DONE` are both $00, and they are
    different things in different streams—; the names may not.
    """
    shared = declared("events") & declared("music")
    assert not shared, (
        "%s is in both bytecodes: in the ROM they are a single symbol"
        % ", ".join(sorted(shared)))
