# Goombario: static checks for 65816 code

Goombario looks at a Super NES program assembled with `ca65` and linked with
`ld65`, and points at the mistakes that assemble and link fine and are wrong:
a branch on a flag a pull left, a routine entered with `jsl` that comes back
with `rts`, a path that leaves something on the stack, an instruction run
with a register width other than the one the source declares.

    goombario game.sfc --only src/
    goombario game.sfc --dbg build/game.dbg --root .. --stats

`cargo build --release`, or `cargo test`. `goombario --help` prints the
usage. There are no dependencies. The tests assemble toy programs, so they
need `ca65` and `ld65` on the PATH; without them they are skipped, saying so.

## What it reads

**The ROM and the debug file `ld65 --dbgfile` writes, and the sources.** The
debug file says, for each source line, where its bytes went: so an
instruction is read from the ROM where its line put it, and nothing is
disassembled by guessing where instructions start. A span with a type is
data, and so is one from a line with a data directive —`.res`, `.align`
and `.dword`, among others, get no type—; a macro's expansion comes with a line per instruction; a `.repeat`,
which has no lines of its own, is decoded from the start of its span with the
widths that make it end exactly where the span ends. A span that cannot be
read that way is reported, and counts as a finding: the checks would be
standing on something wrong.

**The sources give the declared widths.** `ca65` keeps the width of A and
of X/Y as state while it reads the text —`.a8`, `.a16`, `.i8`, `.i16`, and
under `.smart` every `rep`/`sep` with a constant operand— and assembles each
immediate with it. Goombario reads the text the same way, from each module's
main file following its `.include`s, and replays a macro's body where it is
used. The immediates check that reading: `--stats` counts the ones whose
size it does not explain, and on a real program it should be zero.

`--root` is the directory the debug file's paths are relative to: where
`ca65` ran. `--only` keeps the findings to the files under a prefix —a
program's own code, not the data a converter generated—.

## The checks

Each finding says file, line, routine and why, and the annotation that would
allow it.

### `pull-branch`: a branch on what a pull left

`pla`, `plx`, `ply`, `plb` and `pld` set N and Z from the value they pull,
and `plp` sets every flag. `sep` and `rep` set only the bits of their
operand, and a store sets nothing. So in

    lda count
    cmp #3
    ply
    sep #$20
    beq done

the `beq` is looking at what `ply` pulled, not at the comparison. From every
pull, the check follows each path —through branches and jumps, not into
calls, which set the flags anew— until each flag the pull set has been set
again, and flags a conditional branch on one that has not: `beq`/`bne` on Z,
`bpl`/`bmi` on N, and after a `plp` also `bcc`/`bcs` and `bvc`/`bvs`.

**Some of these are right**: `pla` then `beq` is also the shortest way to
ask whether the pulled value is zero. The trap is when the branch wanted to
look at what was there before the pull; when it asks about what was pulled,
the line says so with an annotation, and says what it is that was pulled.

### `call-return`: `jsr` with `rts`, `jsl` with `rtl`

A `jsr` pushes two bytes of return address and `rts` pulls two; `jsl` and
`rtl`, three. A routine entered one way and left the other returns to a
wrong address. The check walks each routine from its entry —every target of
a `jsr`, `jsl` or `jsr (table, x)`— through every branch and every jump,
including into other routines (a tail jump ends in the other routine's
return), and flags each `rts`, `rtl` or `rti` that does not match how some
caller entered it. The interrupt vectors are entries too, and come back with
`rti`.

The finding goes on the return, and names the entry and one caller.

### `stack`: what a routine pushes, it pulls

The same walk counts the bytes each path has pushed since the entry: `pha`
and `pla` by the width of A, `phx`/`phy`/`plx`/`ply` by the width of X/Y,
`php`, `phb`, `phk`, `plp` and `plb` one, `phd`, `pea`, `pei`, `per` and
`pld` two. A return with bytes still pushed is a finding, and so is a pull
of more than was pushed, which takes bytes of the return address. A call is
taken to leave the stack as it found it: the callee's own walk checks that.

What it does not follow, and so does not report:

* **a loop that pushes**: `ldx #3`, a `pha` per turn and four pulls after.
  How many bytes there are depends on data, and every count but the right
  one would be a finding. The whole routine's stack goes unchecked, and
  `--unfollowed` lists it;
* `tcs` and `txs`: the stack is somewhere else after them;
* a jump through a pointer —`jmp (abs)`, `jml [abs]`— and a call outside the
  ROM. A `jmp (table, x)` or `jsr (table, x)` is followed when its table is
  in the ROM: the words from the table's label to the next label.

A routine that pulls its caller's bytes on purpose —a shared exit that drops
the return address to get at what is under it— is an exception, annotated
on the pull and on the return.

### `width`: the widths on each path against the declared ones

The walk also carries the width of A and of X/Y: `rep` and `sep` set them, a
`plp` restores the ones its `php` saved, and a call comes back with the ones
the callee leaves —or the caller's own, if the callee does not change them—.
At the entry they are the ones the source declares there. Then:

* **an immediate assembled for one width and run with the other**. The CPU
  reads it with a different length: the byte left over runs as an opcode, or
  the next opcode is eaten as an operand. The declaration here is in the
  ROM itself —how many bytes `ca65` emitted—;
* **any other instruction whose behaviour depends on a width** —loads,
  stores, arithmetic, shifts, pushes, transfers— run with a width other than
  the one the source declares on its line. It runs as the code means more
  often than not; what is wrong is the declaration, and the next immediate
  added there will be assembled wrong;
* **a call with a width other than the one the callee declares at its
  entry**, for the registers the callee uses before setting them —or passes
  on, unset, to a callee that uses them—.

A width the walk cannot decide —after an `xce`, a `plp` without its `php`,
a call to a routine that comes back in different widths on different paths—
is not a finding. `--stats` says how many it decided and how many it could
not.

## The exceptions

A finding that is what the code means is allowed on its own line, with a
comment that starts with `goombario:`, the check, and why it is right:

    pla
    beq off             ; goombario: pull-branch: the value to write, 0 is off

A line that has no room for it takes it on a line of its own right above,
which covers the next line with code; the comment lines in between carry on
the why, and a blank line in between is an error:

    ; goombario: stack: the shared exit, which pulls its own return address
    ; and the two bytes under it, and puts the address back
    plx

The annotation covers that line and that check: not the routine, not
another check. **The why is required**, and an annotation without one is an
error; so is one that allows nothing on its line —a list of exceptions that
only grows stops saying anything, and one spread over the source too—.
There is no file of exceptions: the why stays on the line it protects, where
whoever edits it sees it, and an exception is reviewed in the same diff as
the code.

Only the source files `--only` keeps are read for annotations, so with
`--only` an annotation in a file it leaves out is neither applied nor
reported.

## What it assumes

* **Banks `$80-$BF` mirror `$00-$3F` from `$8000` up.** A `jsl` to `$80xxxx`
  is taken to land where the debug file has `$00xxxx`. Every Super NES memory
  map has the system area that way; on ExHiROM it holds for what the
  cartridge puts in both places.
* **The labels outside any `.proc` are routines**, for naming where a
  finding is; labels a macro makes with `.local` are not.
* **`.if` is not evaluated**: both branches are read as if they came one
  after the other. If a width directive sits inside one, the immediates
  count in `--stats` says so.

Exit codes: 0 nothing found; 1 findings, annotations that are wrong or allow
nothing, or something the checks cannot stand on; 2 the call itself is wrong.
