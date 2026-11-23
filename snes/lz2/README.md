# lz2: LC_LZ2 with an optimal parser

LC_LZ2 is the LZ format Nintendo used in its own Super NES games. This
library writes it and reads it back.

    let stream = lz2::compress(&tiles)?;
    let stream = lz2::compress_with(&tiles, Options { increasing: false })?;
    let tiles = lz2::decompress(&stream)?;

It is a library and not a command: the emission and the converter compress with
it. `cargo test --release` tests it. There are no dependencies. The tests build
their streams inside the test, so they need nothing else.

## The format

A stream is a run of commands ended by `$FF`. A command starts with a header
that says which command it is and how many output bytes it makes:

    CCCLLLLL                  L+1 bytes, 1 to 32
    111CCCLL LLLLLLLL         L+1 bytes, 1 to 1024

| C | command    | operand                    | output                         |
|---|------------|----------------------------|--------------------------------|
| 0 | literal    | the n bytes                | those bytes                    |
| 1 | byte fill  | one byte                   | it, n times                    |
| 2 | word fill  | two bytes                  | the pair over and over, cut at n |
| 3 | increasing | one byte                   | b, b+1, b+2..., wrapping at 256 |
| 4 | repeat     | a 16-bit address, **big-endian** | n bytes copied from that position of the output |

Commands 5 and 6 do not exist, and a long header never carries command 7,
because `111 111 11` is the terminator.

**The repeat address is absolute.** It is a position in the output counted
from its first byte, not a distance back from the current one. That is what
makes the format cheap on a 65816 with the output in RAM: the source of a
repeat is the output's base plus a number, and one block-move instruction does
the copy. It is also why no output can be longer than 65536 bytes, and why
this library refuses a longer input instead of splitting it: where to split, and
where each part goes, is a decision about the consumer's memory.

A repeat may overlap the bytes it produces. The copy goes forward one byte at a
time, so a repeat from one byte back fills with that byte; a block move that
copies upwards does exactly that.

## What `compress` promises

**The shortest stream the format allows** for the input, and among those of
that size, **the one with the fewest commands**. The decoder spends a fixed
time per command on top of its time per byte, so fewer commands decode faster
at no cost in size.

`Options { increasing: false }` leaves command 3 out, for decoders that do not implement
it: the increasing fill is the one command a block move cannot do. The stream
is then the shortest without it.

It is not a greedy matcher. It is a shortest path over the input: from every
position, every command that fits and every length that command could take.
The longest earlier match at each position comes from a suffix array — the
longest previous factor — so the search is exact, not a hash chain with a
cutoff.

## What `decompress` refuses

Anything a correct encoder cannot produce: a stream cut before its terminator,
bytes after it, a command that does not exist, a repeat from a position not yet
written, and an output past 65536 bytes. `decompress_prefix` reads a stream that
has more after its terminator, and says where it ended.
