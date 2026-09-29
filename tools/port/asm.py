"""The two primitives the converter writes ca65 with: a data block with its
placement declaration, and a symbolic 24-bit pointer."""


def block(label, data, per_line=16, align=None, fit=True):
    """A data block with its placement declaration.

    Each block is declared before emitting it: almost all are uploaded by DMA,
    and a DMA that crosses a bank reads garbage from the middle onward. The
    cell grid isn't uploaded by DMA but walked with a pointer, so it doesn't
    need the whole bank: only that its words don't end up split between the
    end of one bank and the start of the next.

    The same holds for a table walked with `[ptr], y` or with
    `lda f:tabla, x`: it has to stay whole on one side, and its pointers being
    symbolic isn't enough. Split, the ROM reads the second half from `$0000`
    of the next bank, which in LoROM is the WRAM mirror. That is how the event
    page table ended up straddling `$02FFFF` the day a map's sprites grew, and
    what was seen was a background shifted six pixels: it is an error that
    appears or disappears when adding a byte anywhere else in the cartridge.

    `acomodar=False` is for what goes to TABLES: that area lives entirely
    inside bank 0 —it ends at $7FC0—, so nothing that falls there can cross,
    and declaring it emitted a computation that always came out zero.
    """
    out = ([".align %d" % align if align else ".block %d" % len(data)]
           if fit else [])
    out.append("%s:" % label)
    for i in range(0, len(data), per_line):
        out.append("    .byte " + ",".join("$%02X" % b
                                           for b in data[i:i + per_line]))
    return "\n".join(out)


def pointer(dest):
    """The three bytes of a symbolic pointer, for `.byte`."""
    return "<(%s), >(%s), ^(%s)" % (dest, dest, dest)
