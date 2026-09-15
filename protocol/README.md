# The event bytecode, declared once

`events.toml` says what every opcode of the event bytecode is: its number and
the bytes that follow it. Both ends of that contract are generated from here:

    tools/opcodes.py      the compiler's constants, sizes and layout
    rom/src/opcodes.inc   the interpreter's equates, for the 65816 assembler

Both are **committed**. Neither side parses this file at run time, and a test
fails if regenerating would change either of them. That way a changed opcode is
a readable diff on both ends at once.

## Why this file exists

The number used to be declared by the compiler and reach the interpreter
**inside a map's data file**: the side that emits the bytes was telling the
side that implements them what they mean. Three things followed from that, and
all three actually happened:

* three branches each took "the next free number" from their own copy, and two
  picked the same one — a merge with no conflict and a bytecode that could no
  longer be walked;
* the size of an instruction was written down three times, and one copy kept
  the old layout of an opcode that had grown an argument. Nothing failed: the
  interpreter simply carried on reading from the middle of the next
  instruction.

An opcode is small enough that nobody feels the need to look it up, which is
exactly why it has to have one owner.

The ROM's code still needs the converter's output for other things — the map
tables, and the constants that describe them. What moved out is the bytecode.

## The grammar

An instruction is its opcode byte followed by `args`, in declaration order.

```toml
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
answer is to change the opcode, not to grow the grammar: **the moment this file
can describe behaviour, it stopped being a declaration and became a second
compiler**, and the complexity moved instead of going away. What an opcode
*does* is hand-written 65816 and always will be.

## Running it

    just protocolo              # regenerate both files
    just protocolo --check      # fail if either is out of date

The language here is English, like `ditto/`, because nothing in this directory
knows anything about the game it is used by. The two generated files land in a
tree written in Spanish and carry that tree's language; they say at the top
that they are generated and where from.
