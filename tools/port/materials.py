"""The ROM's data blocks with an identity of their own, what of them goes
compressed with LZ2, and the uncompressed copies left next to the
cartridge. How each block is cut into streams, whether each stream fits its
place in WRAM and the compression itself are `rm2k-snes-mapdata`'s: see
`compress_blocks`.
"""

import collections
import json
import os
import shutil

from port import stage
from port.asm import block


class Materials:
    """The ROM's data blocks, with an identity of their own and not the map's.

    Each map used to emit its blocks with its number attached —`map_tiles_0`,
    `map_tiles_1`— and the map record built the pointer's name with that same
    computation. That is, a block's identity **was** the map that asked for
    it, and two maps with the same tiles paid for them twice without anywhere
    to notice.

    Here the block has a name of its own and the map stores which one it
    points to, which is what is needed before anything can be shared. The
    numbering is still per class and in map order, so without deduplicating
    the names are the usual ones and the ROM comes out byte for byte the
    same: it is on purpose, so that this step can be verified without
    depending on the suite.

    The poses already worked this way from before —`global_index` in `emit`—
    and that is where the shape comes from.
    """

    def __init__(self, dedupe=False, compressed=None):
        self.dedupe = dedupe
        self.where = {}
        self.counts = collections.Counter()
        self.saved = collections.Counter()
        self.repeated = collections.Counter()
        # {(class, raw bytes): their LZ2 stream}, already compressed in one
        # go: see `compress_blocks`. And how much each class weighed and
        # weighs, of the blocks that were emitted.
        self.compressed = compressed or {}
        self.raw = collections.Counter()
        self.lz2 = collections.Counter()

    def store_compressed(self, kind, data):
        """Like `store`, but what goes to the cartridge is its LZ2 stream, or
        its streams stuck together if the block goes in pieces, as
        `compress_blocks` answered it. It is deduplicated by the stream,
        which is the same as by the raw content."""
        data = bytes(data)
        stream = self.compressed[(kind, data)]
        label, text = self.store(kind, stream)
        if text:
            self.raw[kind] += len(data)
            self.lz2[kind] += len(stream)
        return label, text

    def store(self, kind, data, align=None):
        """(label, the asm to emit). The asm is empty if the block was already
        there.

        The key includes the class and the placement, not only the content:
        two blocks with the same bytes but a different `.block` or `.align`
        aren't the same block for the linker.
        """
        data = bytes(data)
        key = (kind, align, data)
        if key in self.where:
            if self.dedupe:
                self.saved[kind] += len(data)
                self.repeated[kind] += 1
                return self.where[key], ""
        label = "%s_%d" % (kind, self.counts[kind])
        self.counts[kind] += 1
        self.where.setdefault(key, label)
        return label, block(label, data, align=align)

    def report(self):
        """What was shared and how much was compressed, so that the saving is a
        number and not an idea."""
        lines = ["  %-14s %6.1f KB in LZ2, was %6.1f"
                 % (kind, self.lz2[kind] / 1024.0,
                    self.raw[kind] / 1024.0)
                 for kind in COMPRESSED_KINDS if self.raw[kind]]
        if self.raw:
            lines.append("  %-14s %6.1f KB in LZ2, was %6.1f: %.1f KB less"
                         % ("", sum(self.lz2.values()) / 1024.0,
                            sum(self.raw.values()) / 1024.0,
                            (sum(self.raw.values())
                             - sum(self.lz2.values())) / 1024.0))
        if not self.dedupe or not self.saved:
            return lines
        return lines + ["  %-14s %2d shared block(s), %6.1f KB"
                % (kind, self.repeated[kind], self.saved[kind] / 1024.0)
                for kind, _ in self.saved.most_common()] + [
            "  %-14s %2d              %6.1f KB in total"
            % ("", sum(self.repeated.values()),
               sum(self.saved.values()) / 1024.0)]


# What the ROM decompresses when loading a map, per block class. See
# `lz2_decompress` in tools/runtime/decompress.s.
COMPRESSED_KINDS = ("map_tiles", "above_tiles", "sprite_tiles", "anim_tiles",
                    "map_cells")

# The LZ2 caps the `.inc` carries for `decompress.s` to enforce. Which block
# goes in how many streams and whether each fits its place in WRAM is
# `materials.rs`'s, in `rm2k-snes-mapdata`: see `compress_blocks`.
LZ2_CAP_BACKDROP = 0x8000
LZ2_CAP_ABOVE_AND_SPRITES = 0x6000
LZ2_CAP_ANIM = 0x2000
LZ2_CAP_GRID = 0x10000       # the grid's two halves


def compress_blocks(maps):
    """Everything the cartridge carries compressed, as `rm2k-snes-mapdata
    compress` answers it: `{(class, raw bytes): its LZ2 stream}` —a block
    that goes in pieces, its streams stuck together— and, per map in the
    same order, how many frames the console takes to decompress it. The
    stage cuts the blocks into streams, enforces the WRAM caps and
    compresses each distinct part once, with `lz2` as a library."""
    request = {"maps": [dict({kind: data.hex()
                              for kind, data in map_raw(m).items()},
                             id=m["id"]) for m in maps]}
    written = stage.run("rm2k-snes-mapdata", "mapdata", "compress", request)
    answer = json.loads(written["compress.json"])["maps"]
    streams, frames = {}, []
    for map_info, theirs in zip(maps, answer):
        for kind, data in map_raw(map_info).items():
            streams[(kind, data)] = bytes.fromhex(theirs[kind])
        frames.append(theirs["frames"])
    return streams, frames


def map_raw(map_info):
    """{class: the uncompressed bytes} of a map, for `COMPRESSED_KINDS`."""
    above, sprite = map_info["above"], map_info["sprite"]
    return {"map_tiles": bytes(map_info["tiles"]),
            "above_tiles": bytes(above[0]),
            "sprite_tiles": bytes(sprite[0]) if sprite else b"",
            "anim_tiles": bytes(map_info["anim"]),
            "map_cells": bytes(map_info["celdas"])}


def write_raw(directory, maps):
    """Leaves in `directorio/crudos/` what the ROM has to have in VRAM and in
    WRAM after loading each map, uncompressed: `<index>.<class>.bin`, with the
    map's index in the ROM.

    It is the other end of the compression tests: `test_lz2.py` does the round
    trip of each block, and `test_carga_descomprimida.py` compares what the
    ROM decompressed against this. It comes from the converter and not from
    the ROM precisely so that it isn't the ROM answering itself.

    It is deleted entirely before writing: a map that left the cartridge would
    leave its file, and a test that walks the directory would look at it.
    """
    offset = os.path.join(directory, "crudos")
    if os.path.isdir(offset):
        shutil.rmtree(offset)
    os.makedirs(offset)
    for number, map_info in enumerate(maps):
        for kind, data in map_raw(map_info).items():
            with open(os.path.join(offset, "%d.%s.bin" % (number, kind)),
                      "wb") as f:
                f.write(data)
