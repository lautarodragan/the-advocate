# Bytecodes, declared once

A bytecode has two sides that have to agree byte for byte: whatever emits the
bytes and whatever reads them. When each side writes the numbers down for
itself, they drift, and a bytecode whose two sides disagree **does not fail** —
it reads from the middle of the next instruction and carries on.

So the opcodes are declared once, in a file owned by neither side, and each
side's constants are generated from it:

    generate.py events.toml --python <module>.py --asm <equates>.inc
    generate.py events.toml --python <module>.py --asm <equates>.inc --check

There is one declaration per bytecode. **Where the generated files go is the
caller's business**, not this directory's — that is what keeps this independent
of whatever project uses it.

The generated files are meant to be **committed**, and `--check` is meant to run
in a test suite: it writes nothing, names what is stale, and exits non-zero.
Nothing parses a declaration at run time.

## What is here

    events.toml   the event bytecode: 40 opcodes, the interpreted one
    music.toml    the music stream the sound chip's driver reads: 3 opcodes

## Why this exists

Both of these were already being paid for.

In the event bytecode, the number was decided by the compiler and reached the
interpreter **inside a map's data file**: the side that emits the bytes was
telling the side that implements them what they mean. Two things followed, and
both happened. Two branches each took "the next free number" from their own
copy and picked the same one — a merge with no conflict and a bytecode that
could no longer be walked. And the size of an instruction was written down
three times; one copy kept the old layout of an opcode that had grown an
argument, which took a day to find.

The music stream had it plainer: three numbers, written by hand on **both**
sides, in two files with nothing connecting them.

An opcode is small enough that nobody feels the need to look it up, which is
exactly why it has to have one owner.

## The grammar

An instruction is its opcode byte followed by `args`, in declaration order.

```toml
name = "event"

[[opcode]]
name = "OP_SWITCH"
code = 0x01
args = [
  { name = "id", type = "word" },
  { name = "value", type = "byte" },
]
```

Types are `byte` (1), `word` (2, little endian) and `long` (3, little endian);
`signed = true` says how to read a value back and changes nothing about how it
is written.

An opcode that ends in a variable number of entries declares `repeated`, and
the argument holding how many follow carries `count`:

```toml
[[opcode]]
name = "OP_CHOICE"
code = 0x14
args = [
  { name = "length", type = "byte", count = "options" },
  { name = "on_cancel", type = "byte" },
]
repeated = { name = "options", args = [
  { name = "window", type = "word" },
  { name = "destination", type = "word" },
] }
```

Those are the only two shapes there are. If a new opcode does not fit, the
answer is to change the opcode, not to grow the grammar: **the moment a
declaration can describe behaviour, it stopped being a declaration and became a
second compiler**, and the complexity moved instead of going away. What an
opcode *does* is hand-written and stays hand-written.

## What gets generated

The Python module carries the constants, `OPCODE_SIZE` and `VARIABLE_SIZE`
—derived from the declared arguments, never written down—, `LAYOUT` with each
argument's name, size and signedness, and `opcode_size(code, i)` to walk a
compiled stream. The assembler output is the equates and nothing else.

The language here is English because nothing in this directory knows anything
about the project that uses it, and that includes the generated files: they are
this tool's output, not the host tree's source.
