"""The ROM's data blocks with an identity of their own, what of them goes
compressed with LZ2, in how many streams, and the WRAM caps each stream has
to fit in; and the uncompressed copies left next to the cartridge.
"""

import collections
import os
import shutil

from port import compress
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
        # {raw bytes: their LZ2 stream}, already compressed in one go: see
        # `compress_blocks`. And how much each class weighed and weighs,
        # of the blocks that were emitted.
        self.compressed = compressed or {}
        self.raw = collections.Counter()
        self.lz2 = collections.Counter()

    def store_compressed(self, kind, data):
        """Like `store`, but what goes to the cartridge is its LZ2 stream, or
        its streams stuck together if the block goes in pieces: see
        `compressed_parts`. It is deduplicated by the raw content, which is
        the same as by the stream."""
        data = bytes(data)
        stream = b"".join(self.compressed[part]
                          for part in compressed_parts(kind, data))
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

# The largest each decompressed stream can be, by where it lands in WRAM: see
# the LZ2 reservation in tools/runtime/far_ram.s, which is where they come
# from, and the `.assert` in decompress.s, which checks them against the
# ones here. The background tiles are decompressed before the animation
# drawings and can step on their place; the upper layer and the sprites go
# after and can't.
#
# The background's is **per stream**, not per block: a background of more
# than 32 KB —that of map 66, with the 544-tile layout— goes in two, and the
# ROM decompresses and uploads the first before decompressing the second on
# top of it: see `lz2_backdrop`.
LZ2_CAP_BACKDROP = 0x8000
LZ2_CAP_ABOVE_AND_SPRITES = 0x6000
LZ2_CAP_ANIM = 0x2000
LZ2_CAP_GRID = 0x10000       # two halves of HALF_GRID


# What decompressing costs in the ROM, in master cycles, **on the high side**:
# measured on 2026-09-26 over the forty maps of `release`, against loading
# uncompressed, what was measured doesn't exceed this model by more than half
# a frame. An NTSC frame is 357,954 master cycles. The boot computation uses
# it.
LZ2_CYCLES_PER_COMMAND = 700
LZ2_CYCLES_PER_BYTE = 60
CYCLES_PER_FRAME = 357954


def decompress_frames(map_info, compressed):
    """How many frames decompressing a map's blocks takes."""
    cycles = 0
    for kind, data in map_raw(map_info).items():
        if kind not in COMPRESSED_KINDS:
            continue
        for part in compressed_parts(kind, data):
            cycles += (compress.commands(compressed[part])
                       * LZ2_CYCLES_PER_COMMAND
                       + len(part) * LZ2_CYCLES_PER_BYTE)
    return cycles / float(CYCLES_PER_FRAME)


def compress_blocks(maps):
    """{raw bytes: LZ2 stream} of everything the cartridge carries
    compressed, with a single `lz2` process. Along the way it enforces the
    WRAM caps."""
    parts = []
    for map_info in maps:
        for kind, data in map_raw(map_info).items():
            if kind not in COMPRESSED_KINDS:
                continue
            check_streams(map_info["id"], kind, data)
            parts += compressed_parts(kind, data)
    parts = list(dict.fromkeys(parts))
    return dict(zip(parts, compress.compress_many(parts)))


# The grid goes to the upper half of the two WRAM banks —see `lz2_grid`—, so
# it is compressed in two streams of up to 32 KB: each one lands whole in one
# bank, and the decompressor doesn't have to know how to cross.
HALF_GRID = 0x8000


# And the background tiles, in streams of whatever fits in the load buffer:
# the ROM decompresses one, uploads it by DMA and only then decompresses the
# next in the same place —see `lz2_backdrop`—. A background that fits in one
# goes in one, and that leaves the usual maps with the usual stream.
BACKDROP_STREAMS_MAX = 2            # the ones `lz2_backdrop` reads


def compressed_parts(kind, data):
    """The pieces of a block that are each compressed in their own stream."""
    if kind == "map_cells":
        return [data[:HALF_GRID], data[HALF_GRID:]]
    if kind == "map_tiles" and len(data) > LZ2_CAP_BACKDROP:
        return [data[k:k + LZ2_CAP_BACKDROP]
                for k in range(0, len(data), LZ2_CAP_BACKDROP)]
    return [data]


# How much of each stream fits in WRAM, and how many streams the ROM reads per
# block. The grid always goes in two, one per half; the rest in one, except
# the background.
CAPS_PER_STREAM = {"map_tiles": (LZ2_CAP_BACKDROP, BACKDROP_STREAMS_MAX),
                   "above_tiles": (LZ2_CAP_ABOVE_AND_SPRITES, 1),
                   "sprite_tiles": (LZ2_CAP_ABOVE_AND_SPRITES, 1),
                   "anim_tiles": (LZ2_CAP_ANIM, 1),
                   "map_cells": (HALF_GRID, 2)}


def check_streams(map_id, kind, data):
    """That each stream of the block fits in its WRAM place, and that there
    aren't more streams than the ROM reads. A stream that goes over breaks
    nothing when building: the ROM decompresses it anyway and steps on
    whatever is behind —with map 66's background, the upper half of the
    grid—, and it shows or not depending on the map."""
    cap, count = CAPS_PER_STREAM[kind]
    parts = compressed_parts(kind, data)
    for part in parts:
        if len(part) > cap:
            raise SystemExit(
                "map %d: a stream of %s is %d bytes and %d fit in WRAM: "
                "see the LZ2 reservation in tools/runtime/far_ram.s"
                % (map_id, kind, len(part), cap))
    if len(parts) > count:
        raise SystemExit(
            "map %d: %s is %d bytes, which is %d streams, and the ROM reads %d"
            % (map_id, kind, len(data), len(parts), count))


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
