"""The bank packing, which the converter decides and not the assembler.

A DMA that crosses a bank does not read the next bank's ROM: it reads the
WRAM. That is why everything the ROM uploads by DMA —a pose, a tilemap, a
block of samples— has to fit **whole** in a bank, and when it does not fit in
what is left of the current one, it has to be padded up to the next.

Until 2026-09-16 that decision was taken by the assembler, with a directive of
ours: `.bloque N` meant "what follows is N bytes long, pad if it does not
fit". It worked, but it tied the port to having an assembler of its own:
`ld65` cannot pack variable-size blocks, and that is the only reason the
directive existed. Whoever does know the sizes is the converter, because it
emits them, so the split is done here: what reaches the assembler is one
segment per bank, `BANKnn`, which is what an `ld65` `.cfg` with one area per
bank expects.

**The only thing this module assumes about the memory map is which bank the
generated data starts in**, `FIRST_BANK`. The `.cfg` knows the rest.
"""

import re

BANK_SIZE = 0x8000

# How much each operand of the byte-emitting directives takes.
WIDTHS = {".byte": 1, ".word": 2, ".addr": 2, ".dword": 4}


def _operand_count(rest):
    """How many operands a comma-separated list has.

    Commas inside a string do not separate. The converter does not emit
    strings today, but the rule is the assembler's and it is cheaper to
    respect it than to find out the day it emits them.
    """
    rest = rest.split(";")[0].strip()
    if not rest:
        return 0
    count, quoted = 1, False
    for c in rest:
        if c == '"':
            quoted = not quoted
        elif c == "," and not quoted:
            count += 1
    return count


def _size(line):
    """How many bytes a line takes, or None if it takes none."""
    parts = line.strip().split(None, 1)
    if not parts:
        return 0
    if parts[0] == ".res":
        # The ones this very module leaves, in case someone runs it twice.
        return int(parts[1].split(";")[0].strip())
    width = WIDTHS.get(parts[0])
    if width is None:
        return 0
    return width * _operand_count(parts[1] if len(parts) > 1 else "")


# The bank where the generated data starts. Bank 0 is the code and the
# tables, and bank 1 is `FAR`, the hand-written code that lives outside bank 0.
FIRST_BANK = 2


def segment_of(bank):
    """The name of the segment pinned at the start of `bank`."""
    return "BANK%02X" % bank


def _split(line, fitting):
    """Splits a data line into the first `fitting` bytes and the rest.

    It can only be done between operands: a word split across two banks is
    not a word. If the cut falls in the middle of one, it is an error.
    """
    code, _, comment = line.partition(";")
    directive, rest = code.strip().split(None, 1)
    width = WIDTHS[directive]
    if fitting % width:
        raise ValueError("the end of the bank falls in the middle of a "
                         "%d-byte operand: %r" % (width, line.strip()))
    operands = [o.strip() for o in rest.split(",")]
    count = fitting // width
    tail = ("  ; " + comment.strip()) if comment.strip() else ""
    first = ("    %s %s%s" % (directive, ", ".join(operands[:count]), tail)
             if count else None)
    second = "    %s %s" % (directive, ", ".join(operands[count:]))
    return first, second, (len(operands) - count) * width


class _Piece:
    """What the packing moves as one piece: a `.bloque`, a `.cruza` or what
    starts with neither, with all its lines up to the next one. `fit_size` is
    what it takes for the purpose of fitting —what the `.bloque` declares if
    it is more than what was emitted—, and `order` its place in the text,
    which breaks ties so that the packing always comes out the same."""

    def __init__(self, order, crosses=False, asks=0):
        self.order, self.crosses, self.asks = order, crosses, asks
        self.lines, self.size, self.align = [], 0, 1

    @property
    def fit_size(self):
        return max(self.asks, self.size)


def resolve(paths, segment="RODATA", first_bank=FIRST_BANK):
    """Splits into banks what those files send to `segment`.

    **It is first-fit decreasing**, since 2026-09-27: each piece goes to the
    first bank where it fits, from the largest to the smallest. Until that day
    it was sequential —each piece after the previous one, and the one that
    did not fit jumped to the next bank leaving the gap unused—, and the gaps
    added up to ten banks in `release`. The pieces are not chosen by this
    module: the converter declares them, and there are three kinds.

    * **A `.bloque N` of up to one bank** fits whole in one: almost all of
      them are uploaded by DMA, and a DMA that crosses a bank reads the WRAM.
      It is the piece that gets packed, and it carries everything that
      follows up to the next directive —the tables the `.bloque` measures
      together, and the one-byte labels after them—.
    * **One of more than a bank** —the text block— starts a bank and goes on
      into the following ones, split between operands, as the sequential
      packing used to decide: it is walked by code that jumps banks by hand.
      What is left over in its last bank is used by the others.
    * **A `.cruza`** —the SPC700 driver, its samples, the music streams— can
      be split anywhere **between two consecutive banks**: `spc_block` and
      `advance` jump from `$FFFF` to the next bank's `$8000`, not to any
      bank. First it is tried whole in a gap; the ones that do not fit go at
      the end, one after the other, as a chain that starts in whatever is
      left of the last bank and continues in new banks. It is the only thing
      that fills a bank without leaving a gap.

    **To move the pieces they have to be taken out of their place**, because
    in `ca65` a segment is filled in the order of the text: what is left of
    `segment` in each file is deleted, and all the banks are written at the
    end of the last of `paths`, in order. It can be done because
    `musicdata.inc` and `mapdata.inc` come before all the code in `main.s`,
    and nothing that moves depends on its place: there are no subtractions
    between labels of different pieces, no `*`, no constants that use them.
    The constants (`X = …`) stay where they were. If some day the ROM read a
    piece assuming it is next to another, that would have to go in a single
    `.bloque`: separate, the packing spreads them wherever they fit.

    `paths` comes in the order the assembler reads them, which is that of
    the `.include`s. What a file sends to another segment —the bank 0
    tables— does not count.

    **Every label of more than one byte has to be covered by a `.bloque`**,
    or carry `.cruza` in front if it is walked by code that jumps banks by
    hand. What is read with `lda f:tabla, x` or with `[ptr], y` does not
    jump: split, the second half is read from the next bank's `$0000`, which
    in LoROM is not ROM. The rule is enforced here, on every build, and not
    on the day the cut lands on one: see `undeclared`.

    Returns how many pieces it packed and into how many banks.
    """
    pieces, kept = [], []
    # The labels the packing could split: [name, how long it is, how much of
    # that a `.bloque` covers, whether it carries `.cruza`]. The last one is
    # the one gathering its bytes.
    labels, covers, crosses = [], 0, False
    for path in paths:
        with open(path) as handle:
            lines = handle.read().splitlines()
        own, current, piece, current_label = [], None, None, None
        for line in lines:
            directive = line.split(";")[0].strip()
            if directive.startswith(".segment"):
                current = directive.split(None, 1)[1].strip().strip('"')
                piece, current_label = None, None
                if current != segment:
                    own.append(line)
                continue
            if current != segment or _CONSTANT.match(directive):
                own.append(line)
                continue
            # An `.align` right after a `.bloque` or a `.cruza` belongs to the
            # same piece: the alignment is of what follows.
            just_opened = piece is not None and piece.align > 1 \
                and len(piece.lines) == 1
            if directive.startswith(".bloque "):
                covers = int(directive.split()[1])
                if not just_opened:
                    piece = _Piece(len(pieces))
                    pieces.append(piece)
                piece.asks = covers
                continue
            if directive == ".cruza":
                crosses = True
                if not just_opened:
                    piece = _Piece(len(pieces))
                    pieces.append(piece)
                piece.crosses = True
                continue
            if directive.startswith(".align "):
                # This one stays: aligning is not packing banks, and `ca65`
                # knows how to do it. Here it only has to be counted, and since
                # the segment is the bank, the padding depends on what comes
                # before it in the bank.
                if piece is None or piece.lines:
                    piece = _Piece(len(pieces))
                    pieces.append(piece)
                piece.align = int(directive.split()[1])
                piece.lines.append(line)
                continue
            if piece is None:
                if not directive:
                    own.append(line)
                    continue
                piece = _Piece(len(pieces))
                pieces.append(piece)
            if _LABEL.match(directive):
                current_label = [directive.split(":")[0], 0, covers, crosses]
                labels.append(current_label)
                crosses = False
            size = _size(line)
            covers = max(0, covers - size)
            if current_label:
                current_label[1] += size
            piece.lines.append(line)
            piece.size += size
        leaked = [l for l in own if l.split(";")[0].strip()
                  .startswith((".bloque", ".cruza"))]
        if leaked:
            # A `.bloque` that reaches the assembler is a `ca65` error far
            # from here, which does not say which block or why. Same for
            # `.cruza`.
            raise ValueError(
                "%s left %d `.bloque` unresolved, the first one %r: it is outside "
                "%s, and there the packing cannot be computed"
                % (path, len(leaked), leaked[0].strip(), segment))
        kept.append(own)
    loose = undeclared(labels)
    if loose:
        raise ValueError(
            "%d label(s) in %s without a `.bloque` covering them, and the packing "
            "may split them across two banks: %s. If the ROM walks one "
            "jumping banks by hand, put `.cruza` in front of it"
            % (len(loose), segment, ", ".join(loose)))

    banks = _pack(pieces)
    fitting = BANKS - RESERVED_BANKS - first_bank
    if len(banks) > fitting:
        # Without this the one complaining is `ld65`, with an "Internal error:
        # Invalid file offset for memory area HEAD", which does not say that
        # space ran out.
        raise ValueError("the data needs %d banks and %d fit: from $%02X to "
                         "$%02X" % (len(banks), fitting, first_bank,
                                    first_bank + fitting - 1))
    for k, (_used, lines) in enumerate(banks):
        kept[-1].append('.segment "%s"' % segment_of(first_bank + k))
        kept[-1].extend(lines)
    for path, own in zip(paths, kept):
        with open(path, "w") as handle:
            handle.write("\n".join(own) + "\n")
    return len(pieces), len(banks)


def _padding(used, align):
    return (align - used % align) % align


def _pack(pieces):
    """The banks, as [used, lines], with the pieces inside. See `resolve`,
    which says what each kind is."""
    banks = []
    large = [u for u in pieces if not u.crosses and u.fit_size > BANK_SIZE]
    whole = [u for u in pieces if not u.crosses and u.fit_size <= BANK_SIZE]
    crossing = [u for u in pieces if u.crosses]

    def fits(bank, u):
        # A lone label takes space too: at the end of a bank it would point
        # to the address after `$FFFF`, which is not the ROM.
        return (bank[0] + _padding(bank[0], u.align) + max(1, u.fit_size)
                <= BANK_SIZE)

    def place(u):
        for bank in banks:
            if fits(bank, u):
                bank[0] += _padding(bank[0], u.align) + u.size
                bank[1].extend(u.lines)
                return True
        return False

    # The large ones first, each from a new bank: what is left over in their
    # last bank is used by the others.
    for u in large:
        banks.append([0, []])
        _spill(banks, u.lines)
    by_size = lambda u: (-u.fit_size, u.order)
    for u in sorted(whole, key=by_size):
        if not place(u):
            banks.append([0, []])
            place(u)
    chain = [u for u in sorted(crossing, key=by_size)
             if u.fit_size > BANK_SIZE or not place(u)]
    if chain and not banks:
        banks.append([0, []])
    for u in sorted(chain, key=lambda u: u.order):
        _spill(banks, u.lines)
    return banks


def _spill(banks, lines):
    """Writes `lines` from the end of the last bank, splitting between
    operands and continuing in new banks: it is the old sequential packing,
    for what can or has to cross."""
    for line in lines:
        bank = banks[-1]
        directive = line.split(";")[0].strip()
        # A full bank is left behind before writing anything else, labels
        # included: a label at the end of a bank would point to the address
        # after `$FFFF`, which is not the ROM.
        if bank[0] == BANK_SIZE and directive:
            banks.append([0, []])
            bank = banks[-1]
        if directive.startswith(".align "):
            bank[0] += _padding(bank[0], int(directive.split()[1]))
            bank[1].append(line)
            continue
        size = _size(line)
        while bank[0] + size > BANK_SIZE:
            first, line, size = _split(line, BANK_SIZE - bank[0])
            if first:
                bank[1].append(first)
            banks.append([0, []])
            bank = banks[-1]
        bank[0] += size
        bank[1].append(line)


_CONSTANT = re.compile(r"^[A-Za-z_]\w*\s*=")


_LABEL = re.compile(r"^[A-Za-z_]\w*:")


def undeclared(labels):
    """The ones that can be split without anyone having asked for it.

    A single-byte one is never split, and that is why it is let through: the
    converter emits empty tables with one byte of padding, and one that grows
    is caught the day it grows.
    """
    return [name for name, length, covered, crosses in labels
            if length > 1 and covered < length and not crosses]


# --- the memory map, for `ld65` ----------------------------------------------
#
# 4 MB LoROM: 128 banks of 32 KB, each seen at `$8000-$FFFF` of its number.
# The last two in the file are not used: on the console, banks `$7E` and `$7F`
# **are** the WRAM, and data there would be read as RAM.
BANKS = 128
RESERVED_BANKS = 2

# The stack starts at `$1FFF` and grows downwards, towards the BSS: the two
# share the low 8 KB. This is what it is given, and the lowest byte it gets is
# `$2000 - PILA`.
#
# **It went down from 256 to 128 on 2026-09-20, by taro's decision**, to give
# those 128 bytes to the BSS, which is full. What keeps the margin from being
# blind is `rom/pruebas/rpgmaker/test_pila.py`: it marks the stack area
# **before the first frame** and measures how far down it really went on the
# deepest paths, with the threshold at half of this value. Without that test,
# lowering the number would be spending a margin nobody sees —the failure mode
# is the stack eating into the BSS, and the goldens do not tell it apart, nor
# does `test_cores.py`, because both emulators would get corrupted the same
# way—.
#
# How much is used **is not written here**: that test prints it, and the
# number that was written went stale twice (it said 24 when it was already
# 49). What does belong here is where the cap comes from: the deepest chain is
# the battles, which cross into bank 1 with `jsl` and come back through the
# bridges.
STACK = 128


def cfg():
    """The `ld65` `.cfg`: one area per bank, and each segment in its own.

    An area with `fill = yes` is padded to the end, so each bank takes its
    32 KB in the file even if its segment does not fill them, and a segment
    that overflows makes the link fail instead of spilling into the next one.
    The `BANKnn` are optional because how many are used depends on the
    cartridge.

    The `align = $8000` moves nothing —each segment starts at the beginning
    of its area, which is already aligned to that—, but `ld65` requires a
    segment to declare at least the alignment of the `.align`s it carries.
    """
    memory = [
        # The RAM does not go into the file: it is laid out by address, not
        # by offset.
        'ZP:   start = $0000, size = $0100, type = rw, file = "";',
        'RAM:  start = $0100, size = $%04X, type = rw, file = "";'
        % (0x1F00 - STACK),
        # Bank 0: the code and the tables, and the header and the vectors at
        # the end, where the console looks for them.
        "ROM:  start = $008000, size = $7FC0, fill = yes;",
        "HEAD: start = $00FFC0, size = $0020, fill = yes;",
        "VECT: start = $00FFE0, size = $0020, fill = yes;",
    ]
    segments = [
        "ZEROPAGE: load = ZP,   type = zp;",
        "BSS:      load = RAM,  type = bss;",
        "CODE:     load = ROM,  type = ro;",
        "TABLAS:   load = ROM,  type = ro;",
        "HEADER:   load = HEAD, type = ro;",
        "VECTORS:  load = VECT, type = ro;",
        # The hand-written code that lives outside bank 0.
        "FAR:      load = %s, type = ro, align = $8000;" % segment_of(1),
    ]
    for bank in range(1, BANKS - RESERVED_BANKS):
        memory.append("%s: start = $%02X8000, size = $8000, fill = yes;"
                      % (segment_of(bank), bank))
        if bank >= FIRST_BANK:
            segments.append("%s: load = %s, type = ro, align = $8000, "
                            "optional = yes;"
                            % (segment_of(bank), segment_of(bank)))
    # The two reserved ones go into the file anyway, as zeros: the cartridge
    # is 4 MB, which is what the header says and what flash carts expect.
    memory.append("RESERVADO: start = $%02X8000, size = $%X, fill = yes;"
                  % (BANKS - RESERVED_BANKS, 0x8000 * RESERVED_BANKS))
    return ("# Generated by tools/assembly/banks.py: the ROM's memory map.\n"
            "MEMORY {\n%s\n}\nSEGMENTS {\n%s\n}\n"
            % ("\n".join("    " + m for m in memory),
               "\n".join("    " + s for s in segments)))
