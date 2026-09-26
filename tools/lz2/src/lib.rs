//! LC_LZ2, the LZ format Nintendo used on its own Super NES games, with an
//! optimal parser.
//!
//! A stream is a run of commands and a terminating `$FF`. Every command starts
//! with a header that says what it is and how many output bytes it makes:
//!
//! ```text
//!   CCCLLLLL                 L+1 bytes, 1 to 32
//!   111CCCLL LLLLLLLL        L+1 bytes, 1 to 1024 (the "long" header)
//! ```
//!
//! and the commands are
//!
//! | C | name         | operand         | output                              |
//! |---|--------------|-----------------|-------------------------------------|
//! | 0 | literal      | the n bytes     | the bytes                           |
//! | 1 | byte fill    | one byte        | that byte n times                   |
//! | 2 | word fill    | two bytes       | the pair repeated, cut at n         |
//! | 3 | increasing   | one byte        | b, b+1, b+2... wrapping at 256      |
//! | 4 | repeat       | 16-bit address  | n bytes copied from that position   |
//! |   |              | **big-endian**  | of the output so far                |
//!
//! The repeat address is **absolute**: a position in the output, counted from
//! its first byte, not a distance back from the current one. That is what makes
//! the format cheap to decode on a 65816 with the output in RAM — the source
//! of a repeat is the output base plus a number, and a block-move instruction
//! does the rest — and it is also why an output can never be longer than
//! 65536 bytes. A repeat may overlap the bytes it is producing: the copy goes
//! forward one byte at a time, so a source one byte behind the destination
//! repeats that byte.
//!
//! Commands 5 and 6 do not exist, and a long header can never carry command 7:
//! `111 111 11` is the terminator.
//!
//! [`compress`] finds the shortest encoding there is for this command set —
//! it is not a greedy matcher — and, among the shortest, the one with the
//! fewest commands, because on the console each command costs a fixed
//! overhead on top of its bytes.

use std::fmt;

/// The most bytes one command can produce.
pub const MAX_RUN: usize = 1024;
/// The most bytes a short header can describe.
pub const SHORT_RUN: usize = 32;
/// The longest output a stream can have: a repeat addresses it with 16 bits.
pub const MAX_OUTPUT: usize = 0x10000;
/// The byte that ends a stream.
pub const END: u8 = 0xFF;

pub const LITERAL: u8 = 0;
pub const BYTE_FILL: u8 = 1;
pub const WORD_FILL: u8 = 2;
pub const INCREASING: u8 = 3;
pub const REPEAT: u8 = 4;

/// What can go wrong.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    /// The input to compress is longer than [`MAX_OUTPUT`].
    TooLong(usize),
    /// A stream ran out before its terminator, at this offset.
    Truncated(usize),
    /// A header at this offset names a command that does not exist.
    BadCommand { offset: usize, command: u8 },
    /// A repeat at this offset reads at or past the byte it is producing.
    BadRepeat { offset: usize, from: usize, at: usize },
    /// The output would pass [`MAX_OUTPUT`].
    Overflow(usize),
    /// There are bytes after the terminator, which ends at this offset.
    Trailing(usize),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Error::TooLong(n) => write!(
                f,
                "{} bytes do not fit: a stream addresses its output with 16 bits, {} at most",
                n, MAX_OUTPUT
            ),
            Error::Truncated(at) => write!(f, "the stream ends at byte {} without its $FF", at),
            Error::BadCommand { offset, command } => {
                write!(f, "byte {}: there is no command {}", offset, command)
            }
            Error::BadRepeat { offset, from, at } => write!(
                f,
                "byte {}: a repeat from output position {} while producing position {}",
                offset, from, at
            ),
            Error::Overflow(at) => {
                write!(f, "byte {}: the output passes {} bytes", at, MAX_OUTPUT)
            }
            Error::Trailing(at) => write!(f, "the stream ends at byte {} and the input goes on", at),
        }
    }
}

impl std::error::Error for Error {}

/// One command, as the parser chose it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Command {
    pub kind: u8,
    /// How many output bytes it makes.
    pub len: usize,
    /// For a repeat, the output position it copies from.
    pub from: usize,
}

fn header_bytes(len: usize) -> u64 {
    if len <= SHORT_RUN {
        1
    } else {
        2
    }
}

fn operand_bytes(kind: u8, len: usize) -> u64 {
    match kind {
        LITERAL => len as u64,
        BYTE_FILL | INCREASING => 1,
        WORD_FILL | REPEAT => 2,
        _ => unreachable!(),
    }
}

/// Bytes a command takes in the stream.
pub fn command_bytes(kind: u8, len: usize) -> u64 {
    header_bytes(len) + operand_bytes(kind, len)
}

/// A key orders encodings by size first and command count second. Both fit
/// comfortably: a stream is under 2^17 bytes and has fewer commands than that.
const SHIFT: u32 = 24;

fn key(size: u64, commands: u64) -> u64 {
    (size << SHIFT) | commands
}

/// A segment tree of `(key, position)` answering "the smallest key in this
/// range of positions". The parser fills it from the end of the input
/// backwards, so every position it asks about is already final.
struct MinTree {
    size: usize,
    nodes: Vec<(u64, usize)>,
}

impl MinTree {
    fn new(n: usize) -> MinTree {
        let mut size = 1;
        while size < n {
            size <<= 1;
        }
        MinTree { size, nodes: vec![(u64::MAX, usize::MAX); 2 * size] }
    }

    fn set(&mut self, at: usize, value: u64) {
        let mut i = at + self.size;
        self.nodes[i] = (value, at);
        while i > 1 {
            i >>= 1;
            let (a, b) = (self.nodes[2 * i], self.nodes[2 * i + 1]);
            self.nodes[i] = if b.0 < a.0 { b } else { a };
        }
    }

    /// The smallest over `[lo, hi]`, both inclusive; ties go to the lower
    /// position.
    fn min(&self, lo: usize, hi: usize) -> (u64, usize) {
        let mut best = (u64::MAX, usize::MAX);
        let (mut l, mut r) = (lo + self.size, hi + self.size + 1);
        while l < r {
            if l & 1 == 1 {
                best = pick(best, self.nodes[l]);
                l += 1;
            }
            if r & 1 == 1 {
                r -= 1;
                best = pick(best, self.nodes[r]);
            }
            l >>= 1;
            r >>= 1;
        }
        best
    }
}

fn pick(a: (u64, usize), b: (u64, usize)) -> (u64, usize) {
    if b.0 < a.0 || (b.0 == a.0 && b.1 < a.1) {
        b
    } else {
        a
    }
}

/// The suffix array of `data`: the start of every suffix, in sorted order.
/// Prefix doubling; plenty for inputs of at most 64 KB.
fn suffix_array(data: &[u8]) -> Vec<usize> {
    let n = data.len();
    let mut sa: Vec<usize> = (0..n).collect();
    let mut rank: Vec<usize> = data.iter().map(|&b| b as usize).collect();
    let mut next = vec![0usize; n];
    let mut k = 1;
    loop {
        // The pair (rank of i, rank of i + k), with "past the end" smallest.
        let key = |i: usize, rank: &Vec<usize>| (rank[i], if i + k < n { rank[i + k] + 1 } else { 0 });
        sa.sort_unstable_by_key(|&i| key(i, &rank));
        next[sa[0]] = 0;
        for w in 1..n {
            next[sa[w]] = next[sa[w - 1]] + (key(sa[w - 1], &rank) < key(sa[w], &rank)) as usize;
        }
        std::mem::swap(&mut rank, &mut next);
        if rank[sa[n - 1]] == n - 1 {
            return sa;
        }
        k <<= 1;
    }
}

/// The longest match at every position, and where it starts: the longest
/// previous factor, over any earlier start, overlap allowed, capped at
/// [`MAX_RUN`]. Exact: the suffix array puts the best earlier start at the
/// nearest rank on either side with a smaller position (Crochemore and
/// Ilie), and the common prefix of two ranks is the least LCP between them.
fn longest_matches(data: &[u8]) -> Vec<(usize, usize)> {
    let n = data.len();
    let mut best = vec![(0usize, 0usize); n];
    if n < 2 {
        return best;
    }
    let sa = suffix_array(data);
    let mut rank = vec![0usize; n];
    for (r, &i) in sa.iter().enumerate() {
        rank[i] = r;
    }
    // Kasai: lcp[r] is the common prefix of the suffixes at ranks r-1 and r.
    let mut lcp = vec![0usize; n];
    let mut h = 0usize;
    for i in 0..n {
        if rank[i] > 0 {
            let j = sa[rank[i] - 1];
            while i + h < n && j + h < n && data[i + h] == data[j + h] {
                h += 1;
            }
            lcp[rank[i]] = h;
            h = h.saturating_sub(1);
        } else {
            h = 0;
        }
    }
    // A sparse table for the least LCP over a range of ranks.
    let mut table = vec![lcp.clone()];
    let mut width = 1;
    while 2 * width <= n {
        let last = table.last().unwrap();
        let row: Vec<usize> = (0..n)
            .map(|r| if r + width < n { last[r].min(last[r + width]) } else { last[r] })
            .collect();
        table.push(row);
        width *= 2;
    }
    // The common prefix of the suffixes at ranks a < b.
    let common = |a: usize, b: usize| -> usize {
        let (lo, hi) = (a + 1, b);
        let level = (usize::BITS - 1 - (hi - lo + 1).leading_zeros()) as usize;
        table[level][lo].min(table[level][hi + 1 - (1 << level)])
    };
    // Nearest rank on each side whose suffix starts earlier in the input.
    let mut left = vec![usize::MAX; n];
    let mut right = vec![usize::MAX; n];
    let mut stack: Vec<usize> = Vec::new();
    for r in 0..n {
        while let Some(&top) = stack.last() {
            if sa[top] > sa[r] {
                right[top] = r;
                stack.pop();
            } else {
                break;
            }
        }
        left[r] = stack.last().copied().unwrap_or(usize::MAX);
        stack.push(r);
    }
    for r in 0..n {
        let i = sa[r];
        let mut here = (0usize, 0usize);
        if left[r] != usize::MAX {
            here = (common(left[r], r), sa[left[r]]);
        }
        if right[r] != usize::MAX {
            let len = common(r, right[r]);
            if len > here.0 || (len == here.0 && len > 0 && sa[right[r]] < here.1) {
                here = (len, sa[right[r]]);
            }
        }
        best[i] = (here.0.min(MAX_RUN), here.1);
    }
    best
}

/// The shortest command sequence for `data`, fewest commands among the
/// shortest.
pub fn parse(data: &[u8]) -> Result<Vec<Command>, Error> {
    let n = data.len();
    if n > MAX_OUTPUT {
        return Err(Error::TooLong(n));
    }
    if n == 0 {
        return Ok(Vec::new());
    }
    let matches = longest_matches(data);

    // Runs that start at each position, capped at MAX_RUN.
    let mut byte_run = vec![0usize; n + 1];
    let mut word_run = vec![0usize; n + 2];
    let mut inc_run = vec![0usize; n + 1];
    for i in (0..n).rev() {
        byte_run[i] = if i + 1 < n && data[i + 1] == data[i] {
            (byte_run[i + 1] + 1).min(MAX_RUN)
        } else {
            1
        };
        inc_run[i] = if i + 1 < n && data[i + 1] == data[i].wrapping_add(1) {
            (inc_run[i + 1] + 1).min(MAX_RUN)
        } else {
            1
        };
    }
    // A word fill from i covers i and i+1 freely and then every byte equal to
    // the one two before it: `same2[k]` counts how many in a row from k on.
    let mut same2 = vec![0usize; n + 2];
    for k in (2..n).rev() {
        same2[k] = if data[k] == data[k - 2] { same2[k + 1] + 1 } else { 0 };
    }
    for i in 0..n {
        word_run[i] = if i + 1 >= n { 1 } else { (2 + same2[i + 2]).min(MAX_RUN) };
    }

    // cost[i] = (size, commands) of the best encoding of data[i..].
    let mut size = vec![0u64; n + 1];
    let mut count = vec![0u64; n + 1];
    let mut choice = vec![Command { kind: 0, len: 0, from: 0 }; n];
    // Tree A: key of the suffix at j. Tree B: the same with j added to the
    // size, for literals, whose cost grows by one per byte covered.
    let mut tree_a = MinTree::new(n + 1);
    let mut tree_b = MinTree::new(n + 1);
    tree_a.set(n, key(0, 0));
    tree_b.set(n, key(n as u64, 0));

    for i in (0..n).rev() {
        let mut best = u64::MAX;
        let mut best_cmd = Command { kind: 0, len: 0, from: 0 };
        let remaining = n - i;

        // A command of `kind` whose operand cost does not depend on its
        // length, usable for any length in 1..=run.
        let mut try_run = |kind: u8, run: usize, from: usize, best: &mut u64, best_cmd: &mut Command| {
            let run = run.min(remaining);
            if run == 0 {
                return;
            }
            for &(lo, hi) in &[(1usize, SHORT_RUN), (SHORT_RUN + 1, MAX_RUN)] {
                if lo > run {
                    break;
                }
                let hi = hi.min(run);
                let (k, j) = tree_a.min(i + lo, i + hi);
                if k == u64::MAX {
                    continue;
                }
                let len = j - i;
                let total = k + key(command_bytes(kind, len), 1);
                if total < *best {
                    *best = total;
                    *best_cmd = Command { kind, len, from };
                }
            }
        };

        try_run(BYTE_FILL, byte_run[i], 0, &mut best, &mut best_cmd);
        if remaining >= 2 {
            try_run(WORD_FILL, word_run[i], 0, &mut best, &mut best_cmd);
        }
        try_run(INCREASING, inc_run[i], 0, &mut best, &mut best_cmd);
        let (mlen, mfrom) = matches[i];
        if mlen > 0 {
            try_run(REPEAT, mlen, mfrom, &mut best, &mut best_cmd);
        }

        // Literals: the size is header + len + size[j], and len = j - i, so
        // the smallest (size[j] + j) over the range wins.
        for &(lo, hi, header) in &[(1usize, SHORT_RUN, 1u64), (SHORT_RUN + 1, MAX_RUN, 2u64)] {
            if lo > remaining {
                break;
            }
            let hi = hi.min(remaining);
            let (k, j) = tree_b.min(i + lo, i + hi);
            if k == u64::MAX {
                continue;
            }
            let total = k - key(i as u64, 0) + key(header, 1);
            // On a tie a literal wins: it says plainly what the bytes are.
            if total <= best {
                best = total;
                best_cmd = Command { kind: LITERAL, len: j - i, from: 0 };
            }
        }

        size[i] = best >> SHIFT;
        count[i] = best & ((1 << SHIFT) - 1);
        choice[i] = best_cmd;
        tree_a.set(i, best);
        tree_b.set(i, key(size[i] + i as u64, count[i]));
    }

    let mut out = Vec::new();
    let mut i = 0;
    while i < n {
        let c = choice[i];
        out.push(c);
        i += c.len;
    }
    Ok(out)
}

/// Writes the commands for `data` as a stream, terminator included.
pub fn encode(data: &[u8], commands: &[Command]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut i = 0;
    for c in commands {
        let n = c.len - 1;
        if c.len <= SHORT_RUN {
            out.push((c.kind << 5) | n as u8);
        } else {
            out.push(0xE0 | (c.kind << 2) | (n >> 8) as u8);
            out.push((n & 0xFF) as u8);
        }
        match c.kind {
            LITERAL => out.extend_from_slice(&data[i..i + c.len]),
            BYTE_FILL | INCREASING => out.push(data[i]),
            WORD_FILL => {
                out.push(data[i]);
                // A word fill of one byte still carries its two operand bytes;
                // the second is never output, so any value does.
                out.push(if i + 1 < data.len() { data[i + 1] } else { 0 });
            }
            REPEAT => {
                out.push((c.from >> 8) as u8);
                out.push((c.from & 0xFF) as u8);
            }
            _ => unreachable!(),
        }
        i += c.len;
    }
    out.push(END);
    out
}

/// `data` as an LC_LZ2 stream.
pub fn compress(data: &[u8]) -> Result<Vec<u8>, Error> {
    let commands = parse(data)?;
    Ok(encode(data, &commands))
}

/// A stream back into its bytes, and how many stream bytes it took, the
/// terminator included. Refuses anything a correct encoder cannot produce.
pub fn decompress_prefix(stream: &[u8]) -> Result<(Vec<u8>, usize), Error> {
    let mut out: Vec<u8> = Vec::new();
    let mut i = 0;
    let byte = |i: usize| stream.get(i).copied().ok_or(Error::Truncated(i));
    loop {
        let at = i;
        let h = byte(i)?;
        i += 1;
        if h == END {
            return Ok((out, i));
        }
        let (kind, len) = if h >> 5 == 7 {
            let low = byte(i)? as usize;
            i += 1;
            ((h >> 2) & 7, (((h as usize) & 3) << 8 | low) + 1)
        } else {
            (h >> 5, (h as usize & 31) + 1)
        };
        if out.len() + len > MAX_OUTPUT {
            return Err(Error::Overflow(at));
        }
        match kind {
            LITERAL => {
                if i + len > stream.len() {
                    return Err(Error::Truncated(stream.len()));
                }
                out.extend_from_slice(&stream[i..i + len]);
                i += len;
            }
            BYTE_FILL => {
                let b = byte(i)?;
                i += 1;
                out.extend(std::iter::repeat(b).take(len));
            }
            WORD_FILL => {
                let pair = [byte(i)?, byte(i + 1)?];
                i += 2;
                out.extend((0..len).map(|k| pair[k & 1]));
            }
            INCREASING => {
                let b = byte(i)?;
                i += 1;
                out.extend((0..len).map(|k| b.wrapping_add(k as u8)));
            }
            REPEAT => {
                let from = (byte(i)? as usize) << 8 | byte(i + 1)? as usize;
                i += 2;
                if from >= out.len() {
                    return Err(Error::BadRepeat { offset: at, from, at: out.len() });
                }
                for k in 0..len {
                    let b = out[from + k];
                    out.push(b);
                }
            }
            command => return Err(Error::BadCommand { offset: at, command }),
        }
    }
}

/// A stream back into its bytes. Bytes after the terminator are an error: a
/// file holds one stream.
pub fn decompress(stream: &[u8]) -> Result<Vec<u8>, Error> {
    let (out, used) = decompress_prefix(stream)?;
    if used != stream.len() {
        return Err(Error::Trailing(used));
    }
    Ok(out)
}
