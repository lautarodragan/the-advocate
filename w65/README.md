# w65, a 65816 assembler with the linker built in

    w65 main.s -o cart.sfc
    w65 main.s -I generated/ -o cart.sfc --symbols cart.sym

One source in, one cartridge image out. There is no object file and no
separate link step: the memory map is fixed —LoROM, a handful of named
segments, a header with its checksum— so a label can carry its full 24-bit
address from the moment it is placed, which is what makes `lda f:label` and
`jml label` work without a relocation table.

It is **not** a complete 65816 assembler. It covers the subset that the
sources it is pointed at actually use, and refuses everything else with a
message naming the line. For a tool whose whole job is to be predictable that
is the right trade: an error is far better than an image that is subtly
different from the one you meant.

Exit codes: **1** the source did not assemble, **2** the call was wrong —an
unreadable source, an unwritable output, arguments that do not make sense—, so
a build script can tell "fix the program" from "fix the command".

## What it understands

Directives:

    .segment "NAME"   switch segment
    .proc NAME        open a scope; labels inside it are local to it
    .endproc          close it
    .include "F"      read another file: the -I directories first, then the
                      directory of the file doing the including
    .byte .word       emit data, little endian; .addr is .word, and a quoted
    .addr .dword      string is written one byte per character
    .res N            take up N bytes without writing them
    .alinear N        pad until the address is a multiple of N
    .bloque N         pad, if needed, so that the next N bytes do not cross a
                      bank boundary
    .controlar A = B, "note"
                      a condition that has to hold while assembling
    .a8 .a16 .i8 .i16 declare the width in force for A and for X/Y
    .p816 .smart .setcpu .feature
                      accepted and ignored

Expressions take `+ - * / & |`, parentheses, the prefixes `<` `>` `^` for the
low, high and bank byte, and the functions `.loword .hiword .bankbyte .lobyte
.hibyte`. Literals are `$hex`, `%binary` and decimal. A name is a label or a
constant declared with `NAME = expression`.

Labels are `name:`, and `:` on its own is an anonymous label that `:+` and
`:-` reach —`:++` skips one, and so on. A repeated label or a constant
redefined with a *different* value is an error: both used to be resolved by
letting the last one win, in silence.

## The two checks that earn their keep

**Widths.** The width set by `sep`/`rep` is tracked in reading order, so a
label reached by a branch that skips the width change is recorded with the
width of the fall-through path, not of the branch's. The `cmp #2` after it is
then emitted with a two byte immediate, a CPU in eight bit mode reads one, and
the other byte is executed as an instruction. This does not show in a diff and
cannot be seen in the output; every relative branch is therefore checked
against the width its target declares, and the error says which `.a8`/`.a16`
the label is missing.

**Fit.** Every area is checked against its size, the RAM included: a zero page
that grows past 256 bytes silently lands on top of the stack, and the image
still assembles and still boots.

## Building and testing

    cargo build --release
    cargo test

The tests are small sources written inside the test itself, assembled and
compared byte for byte, plus the error messages: what an unknown symbol, a
`.res` that does not fit, a missing `.include` and a branch that skips a width
change each say. They depend on nothing outside this directory.

## Why it exists at all

It replaces a full assembler and linker for one fixed map, and the reason is
not technical but one of surface: a complete toolchain that is not packaged
for the distributions in use has to be cloned and built, which puts unaudited
code inside the box where the sources and the credentials live. A thousand
reviewable lines cost less than that dependency.

The design decisions that are not obvious from the code —why the last two
banks of the file are left empty, why the tables have to share bank 0 with the
code, why the header's checksum slots hold `$FFFF` and `$0000` in the
source— are written down next to the constants in `src/layout.rs`. They were
each paid for once.
