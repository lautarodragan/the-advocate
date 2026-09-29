"""What the cartridge stores in the `.msu`: the MSU-1's data port.

The `.msu` is the file that turns the MSU-1 on, and until 2026-09-25 it was
empty. The MSU-1 exposes it as a stream: the ROM writes a 32-bit position to
$2000..$2003 —the write to $2003 is the one that seeks—, waits for bit 7 of
$2000 to clear and reads from $2001 byte by byte, advancing on its own; by
DMA with the source fixed at $2001 it reads at the speed of any DMA. The
mechanism on this side and on the ROM's is in docs/port/msu-datos.md.

What it carries first are **the quality battle backdrops**, 8bpp and 96
colors, and **all of the game's**, whether or not they are in the
cartridge's maps: see "Which backdrops there are" in tools/port/scene.py.
**Without MSU-1 the game has to work the same** —Mednafen does not have
it—, so the ROM carries a light fallback, 4bpp and 16 colors, of the few
that fit, and a replacement for the rest; the `.msu` replaces them when it is
there and it belongs to this cartridge. They are different on purpose: see
"The light fallback" in tools/port/scene.py.

## The format

All little-endian:

    $00     8  the signature: the first 8 bytes of the sha256 of everything
               that follows
    $08     4  the game's signature: `[rom] msu_data_signature`
    $0C     2  the format version, 2 today
    $0E     2  how many entries there are, N
    $10     8N per entry: where it starts in the file and how long it is,
               4 and 4
    ...        zeros, up to FONDOS_DESDE
    $10000     the backdrops, one every FONDO_LUGAR bytes and in order of
               number: backdrop k at `backdrop_offset(k)`
    ...        after the last one, the other entries, one after the other
               and in the order of the index

**The backdrop region is fixed.** Up to version 1 the entries all went one
after the other behind the index, so the place of a backdrop depended on how
many entries there were —and the sound effects belong to each cartridge— and
on which backdrops the cartridge carried. Since 2026-09-27 the `.msu`
carries all of the game's backdrops, each one with its number, and backdrop
k is at the same byte in the `.msu` of any cartridge:
`FONDOS_DESDE + k * FONDO_LUGAR` its tiles, and `COLORS_AT` further on its
colors. The index is still there, and says the same thing, for the tools. If
the index were ever to go past `BACKDROPS_START` —more than eight thousand
entries— `build` refuses.

Each place is 32,768 bytes of tiles, 192 of colors and padding up to the
next multiple of 512: that way the tiles of each backdrop start at a sector
of the SD card, which is where the FX Pak reads them from. It is not
measured that this makes it faster; it costs 320 bytes per backdrop.

**The signature is of the content, not of the build.** The ROM carries the
one it expects —the converter emits it in the `.inc`— and compares it with
the first 8 bytes of the `.msu` before reading anything: if they do not
match —a `.msu` from another build, an empty one, a truncated one— it uses
the ROM. That it is of the content and not of the commit means that a
`.msu` from another build **with the same data** is accepted, and that is
fine: what is protected is that the bytes are the ones the ROM expects, and
covering the index with the hash also covers where each thing is.

**The ROM reads the positions from its `.inc`, not from the index.** Once
the signature is accepted, the file's index and the `.inc` constants are the
same data by construction —they come from `build`—, and reading it on the
console would be one more seek per battle to learn nothing. The index is
there for the tools on this side (`read`) and so that adding something else
later means adding entries, without changing the format.

Each backdrop is two entries, in this order: its 512 tiles at 8bpp —32,768
bytes, exactly as they go to WRAM— and its 96 15-bit colors —192 bytes,
exactly as they go to CGRAM from entry 32—. `fondo_bytes` in
snes_convert.py builds them, and the ROM knows where each one is from
`msu_fondo_pos`, which `escribir_msu` emits.

After the backdrops come the quality sound effects, one entry per effect of
each audio pack, in BRR: `escribir_msu` in snes_convert.py orders them, and
the reason is in tools/audio/msu_effects.py.
"""

import hashlib
import struct

from common import settings

VERSION = 2
SIGNATURE_SIZE = 8
HEADER_SIZE = 16
ENTRY_SIZE = 8

# The backdrop region: see "The format".
BACKDROPS_START = 0x10000
COLORS_AT = 0x8000                 # 512 tiles at 8bpp
BACKDROP_SPAN = 0x8200                # and the 192 bytes of colors, to the sector
SECTOR = 512
assert BACKDROP_SPAN % SECTOR == 0 and BACKDROP_SPAN >= COLORS_AT + 96 * 2


def backdrop_offset(k):
    """Where the tiles of backdrop number `k` are; its colors, `COLORS_AT`
    further on."""
    return BACKDROPS_START + k * BACKDROP_SPAN


def build(entries, backdrops=0):
    """The `.msu` with these entries, and where each one ended up.

    `entries` are the bytes of each one, in order. The first `2 * fondos`
    are the backdrops —tiles and colors of each— and go in their fixed
    place, `backdrop_offset`; the rest after the backdrop region, one after the
    other. Without backdrops, all of them in a row after the index. Returns
    `(archivo, posiciones)`, with `posiciones[k]` the offset of entry `k`
    from the start of the file.
    """
    offsets = []
    offset = HEADER_SIZE + ENTRY_SIZE * len(entries)
    if backdrops:
        if offset > BACKDROPS_START:
            raise ValueError("the .msu index is %d B long and overlaps the "
                             "backdrop region, at $%X" % (offset, BACKDROPS_START))
        for k in range(backdrops):
            tiles, colors = entries[2 * k], entries[2 * k + 1]
            if len(tiles) > COLORS_AT or \
                    COLORS_AT + len(colors) > BACKDROP_SPAN:
                raise ValueError("backdrop %d does not fit in its place in the .msu"
                                 % k)
            offsets += [backdrop_offset(k), backdrop_offset(k) + COLORS_AT]
        # What follows goes after the whole region, not after the last byte
        # written: that way it does not depend on the size of the last
        # backdrop either.
        offset = backdrop_offset(backdrops)
    for data in entries[2 * backdrops:]:
        offsets.append(offset)
        offset += len(data)
    index = b"".join(struct.pack("<II", p, len(d))
                     for p, d in zip(offsets, entries))
    body = bytearray(magic() + struct.pack("<HH", VERSION, len(entries))
                     + index)
    for p, data in zip(offsets, entries):
        # Zero padding up to where it goes: the signature covers it like
        # everything else.
        body += bytes(p - SIGNATURE_SIZE - len(body))
        body += data
    body = bytes(body)
    return signature_of(body) + body, offsets


def magic():
    """The four bytes that say which game the `.msu` belongs to: those of
    the project file, `[rom] msu_data_signature`. The ROM does not compare
    them: it compares the signature at the front, which covers them. They are
    read when used and not on import, so the converter can be imported
    without a game."""
    return settings.ascii("rom", "msu_data_signature", length=4).encode()


def signature_of(body):
    """The 8 bytes that go at the start: from the sha256 of what follows."""
    return hashlib.sha256(body).digest()[:SIGNATURE_SIZE]


def index(blob):
    """The index of a `.msu`: `(donde, largo)` per entry, or `ValueError` if
    it is not a valid one."""
    if len(blob) < HEADER_SIZE or blob[SIGNATURE_SIZE:SIGNATURE_SIZE + 4] != magic():
        raise ValueError("not a .msu with data from this port")
    if signature_of(blob[SIGNATURE_SIZE:]) != blob[:SIGNATURE_SIZE]:
        raise ValueError("the signature does not match the content")
    version, n = struct.unpack_from("<HH", blob, SIGNATURE_SIZE + 4)
    if version != VERSION:
        raise ValueError("version %d, and this reads %d" % (version, VERSION))
    return [struct.unpack_from("<II", blob, HEADER_SIZE + ENTRY_SIZE * k)
            for k in range(n)]


def read(blob):
    """The entries of a `.msu`, or `ValueError` if it is not a valid one."""
    return [blob[offset:offset + length] for offset, length in index(blob)]
