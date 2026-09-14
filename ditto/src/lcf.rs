//! The RPG Maker 2000 binary format, from both sides.
//!
//! A file is a header —a length and a name— and then a struct. A struct is a
//! run of *chunks* `(id, length, bytes)` closed by an id 0; an array of structs
//! is a count and, per element, its id and its struct. Integers are BER: seven
//! bits per byte, the high bit says it continues.
//!
//! What makes the exact round trip hard is not that, but the omission rule:
//! **a field holding its default is not written**, except for the ones
//! `fields.csv` marks with `PersistIfDefault`. So reading and writing are not
//! symmetric by construction: they are symmetric because the default that
//! fills a field in when reading is the same one that decides to omit it when
//! writing, and both come from the same table. See `src/schema/mod.rs`.

use serde::{Deserialize, Serialize};
use std::fmt;

/// The crate's result type. It shadows the prelude's `Result` inside the
/// modules that glob-import this one, which is deliberate: every fallible
/// operation here fails with the same `Error`.
pub type Result<T, E = Error> = std::result::Result<T, E>;

#[derive(Debug)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Error {}

pub fn error<T>(m: impl Into<String>) -> Result<T> {
    Err(Error(m.into()))
}

/// A chunk the schema does not name. It is kept as is and goes back to the
/// file in its place, so a field liblcf does not know about cannot break the
/// round trip.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RawChunk {
    pub id: u32,
    pub bytes: Vec<u8>,
}

// --- Reader ---------------------------------------------------------------

pub struct Reader<'a> {
    d: &'a [u8],
    pub pos: usize,
}

impl<'a> Reader<'a> {
    pub fn new(d: &'a [u8]) -> Self {
        Reader { d, pos: 0 }
    }

    pub fn eof(&self) -> bool {
        self.pos >= self.d.len()
    }

    pub fn remaining(&self) -> usize {
        self.d.len() - self.pos
    }

    pub fn peek(&self) -> Result<u8> {
        self.d
            .get(self.pos)
            .copied()
            .ok_or_else(|| Error("read past the end".into()))
    }

    pub fn byte(&mut self) -> Result<u8> {
        let b = self.peek()?;
        self.pos += 1;
        Ok(b)
    }

    pub fn bytes(&mut self, n: usize) -> Result<&'a [u8]> {
        if self.pos + n > self.d.len() {
            return error(format!(
                "asked for {n} bytes at {} and {} are left",
                self.pos,
                self.remaining()
            ));
        }
        let t = &self.d[self.pos..self.pos + n];
        self.pos += n;
        Ok(t)
    }

    /// A BER integer. It is unsigned: negatives arrive in two's complement.
    pub fn ber(&mut self) -> Result<i32> {
        let mut v: u32 = 0;
        loop {
            let b = self.byte()?;
            v = (v << 7) | (b & 0x7F) as u32;
            if b & 0x80 == 0 {
                return Ok(v as i32);
            }
        }
    }
}

// --- Writer ---------------------------------------------------------------

#[derive(Default)]
pub struct Writer {
    pub b: Vec<u8>,
}

impl Writer {
    pub fn new() -> Self {
        Writer { b: Vec::new() }
    }

    pub fn bytes(&mut self, s: &[u8]) {
        self.b.extend_from_slice(s);
    }

    pub fn ber(&mut self, v: i32) {
        self.bytes(&enc_ber(v));
    }

    /// Writes the chunks of a struct: the ones the schema knows and the ones it
    /// does not, merged by id. The schema's order is already ascending —the
    /// liblcf CSV guarantees it— so a stable sort by id leaves every unknown
    /// chunk where it was.
    pub fn dump(&mut self, known: Vec<(u32, Vec<u8>)>, extra: &[RawChunk]) {
        let mut all = known;
        if !extra.is_empty() {
            for e in extra {
                all.push((e.id, e.bytes.clone()));
            }
            all.sort_by_key(|c| c.0);
        }
        for (id, body) in all {
            self.ber(id as i32);
            self.ber(body.len() as i32);
            self.bytes(&body);
        }
    }
}

/// Canonical BER: the same shape as `LcfWriter::WriteInt`, the fewest bytes.
pub fn enc_ber(v: i32) -> Vec<u8> {
    let v = v as u32;
    let mut out = Vec::new();
    let mut i = 28i32;
    while i >= 0 {
        if v >= (1u32 << i) || i == 0 {
            out.push(((v >> i) & 0x7F) as u8 | if i > 0 { 0x80 } else { 0 });
        }
        i -= 7;
    }
    out
}

// --- The default, written once ---------------------------------------------

/// Declares a schema struct with **the default of every field next to the
/// field**, and builds the `Default` out of that.
///
/// The point is not aesthetics. The default is what fills a field in when
/// reading *and* what decides to omit it when writing, and those two have to be
/// the same thing or the round trip stops being byte for byte. Written twice
/// —a comment and an `impl Default`, which is how it used to be— the two can
/// drift apart with nothing warning about it.
///
/// The `= expr` is **mandatory on every field**, even on the ones `fields.csv`
/// declares no default for: if it were optional, a field without a default
/// would fall back to the zero of its type through the back door, which is
/// exactly the bug that started Ditto (`max_hp` at 0 where the format says 10).
///
/// Nothing is needed for serde: the struct's `#[serde(default)]` already takes
/// its values from this `Default`, so a field missing from the JSON holds the
/// format's default and not the type's.
macro_rules! schema_struct {
    (
        $(#[$meta:meta])*
        pub struct $name:ident {
            $(
                $(#[$field_meta:meta])*
                pub $field:ident : $ty:ty = $value:expr
            ),* $(,)?
        }
    ) => {
        $(#[$meta])*
        pub struct $name {
            $(
                $(#[$field_meta])*
                pub $field: $ty,
            )*
        }

        impl Default for $name {
            fn default() -> Self {
                Self { $($field: $value,)* }
            }
        }
    };
}
pub(crate) use schema_struct;

// --- Chunk-based structs ---------------------------------------------------

pub trait Chunked: Default + Sized {
    const NAME: &'static str;
    /// The 0 that closes the struct. `Database` and `Save` go without it:
    /// liblcf warns that adding it breaks RPG_RT's parser.
    const TERMINATOR: bool;
    /// Whether, inside an array, each element carries its id in front.
    const WITH_ID: bool;

    fn id(&self) -> i32;
    fn set_id(&mut self, v: i32);
    fn unknown_mut(&mut self) -> &mut Vec<RawChunk>;
    /// Returns `false` if the id does not belong to this struct: the chunk is
    /// then kept raw.
    fn read_chunk(&mut self, id: u32, d: &[u8]) -> Result<bool>;
    fn write_chunks(&self, e: &mut Writer) -> Result<()>;
}

pub fn read_struct<T: Chunked>(l: &mut Reader) -> Result<T> {
    let mut o = T::default();
    while !l.eof() {
        let id = l.ber()? as u32;
        if id == 0 {
            break;
        }
        let length = l.ber()? as usize;
        let d = l.bytes(length)?;
        if !o.read_chunk(id, d)? {
            o.unknown_mut().push(RawChunk {
                id,
                bytes: d.to_vec(),
            });
        }
    }
    Ok(o)
}

pub fn write_struct<T: Chunked>(o: &T, e: &mut Writer) -> Result<()> {
    o.write_chunks(e)?;
    if T::TERMINATOR {
        e.ber(0);
    }
    Ok(())
}

pub fn dec_struct<T: Chunked>(d: &[u8]) -> Result<T> {
    read_struct(&mut Reader::new(d))
}

pub fn enc_struct<T: Chunked>(o: &T) -> Result<Vec<u8>> {
    let mut e = Writer::new();
    write_struct(o, &mut e)?;
    Ok(e.b)
}

pub fn read_array<T: Chunked>(l: &mut Reader) -> Result<Vec<T>> {
    let n = l.ber()? as usize;
    let mut v = Vec::with_capacity(n.min(4096));
    for _ in 0..n {
        let id = if T::WITH_ID { l.ber()? } else { 0 };
        let mut o: T = read_struct(l)?;
        o.set_id(id);
        v.push(o);
    }
    Ok(v)
}

pub fn write_array<T: Chunked>(v: &[T], e: &mut Writer) -> Result<()> {
    e.ber(v.len() as i32);
    for o in v {
        if T::WITH_ID {
            e.ber(o.id());
        }
        write_struct(o, e)?;
    }
    Ok(())
}

pub fn dec_array<T: Chunked>(d: &[u8]) -> Result<Vec<T>> {
    read_array(&mut Reader::new(d))
}

pub fn enc_array<T: Chunked>(v: &[T]) -> Result<Vec<u8>> {
    let mut e = Writer::new();
    write_array(v, &mut e)?;
    Ok(e.b)
}

// --- Scalar types ----------------------------------------------------------

pub fn dec_ber(d: &[u8]) -> i32 {
    if d.is_empty() {
        return 0;
    }
    Reader::new(d).ber().unwrap_or(0)
}

pub fn dec_bool(d: &[u8]) -> bool {
    d.first().map_or(false, |b| *b != 0)
}

pub fn enc_bool(v: bool) -> Vec<u8> {
    vec![v as u8]
}

pub fn dec_u8(d: &[u8]) -> u8 {
    d.first().copied().unwrap_or(0)
}

pub fn dec_i8(d: &[u8]) -> i8 {
    dec_u8(d) as i8
}

pub fn dec_u32(d: &[u8]) -> u32 {
    let mut b = [0u8; 4];
    b[..d.len().min(4)].copy_from_slice(&d[..d.len().min(4)]);
    u32::from_le_bytes(b)
}

pub fn enc_u32(v: u32) -> Vec<u8> {
    v.to_le_bytes().to_vec()
}

pub fn dec_f64(d: &[u8]) -> f64 {
    let mut b = [0u8; 8];
    b[..d.len().min(8)].copy_from_slice(&d[..d.len().min(8)]);
    f64::from_le_bytes(b)
}

pub fn enc_f64(v: f64) -> Vec<u8> {
    v.to_le_bytes().to_vec()
}

pub fn dec_vec_i16(d: &[u8]) -> Vec<i16> {
    d.chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect()
}

pub fn enc_vec_i16(v: &[i16]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 2);
    for x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

pub fn dec_vec_i32(d: &[u8]) -> Vec<i32> {
    d.chunks_exact(4)
        .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

pub fn enc_vec_i32(v: &[i32]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 4);
    for x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

pub fn dec_vec_u32(d: &[u8]) -> Vec<u32> {
    d.chunks_exact(4)
        .map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

pub fn enc_vec_u32(v: &[u32]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 4);
    for x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

/// `Vector<Boolean>` and `DBBitArray`: a whole byte per value, not a bit.
pub fn dec_vec_bool(d: &[u8]) -> Vec<bool> {
    d.iter().map(|b| *b != 0).collect()
}

pub fn enc_vec_bool(v: &[bool]) -> Vec<u8> {
    v.iter().map(|b| *b as u8).collect()
}

/// One bit of a `*_Flags` field, from the least significant one of the first
/// byte.
pub fn bit(d: &[u8], i: usize) -> bool {
    d.get(i / 8).map_or(false, |b| (b >> (i % 8)) & 1 == 1)
}

// --- Text ------------------------------------------------------------------

/// The 32 characters where cp1252 departs from Latin-1 (0x80..0x9F).
const CP1252_HIGH: [char; 32] = [
    '\u{20AC}', '\u{0081}', '\u{201A}', '\u{0192}', '\u{201E}', '\u{2026}', '\u{2020}', '\u{2021}',
    '\u{02C6}', '\u{2030}', '\u{0160}', '\u{2039}', '\u{0152}', '\u{008D}', '\u{017D}', '\u{008F}',
    '\u{0090}', '\u{2018}', '\u{2019}', '\u{201C}', '\u{201D}', '\u{2022}', '\u{2013}', '\u{2014}',
    '\u{02DC}', '\u{2122}', '\u{0161}', '\u{203A}', '\u{0153}', '\u{009D}', '\u{017E}', '\u{0178}',
];

/// **Complete** cp1252, with the five bytes the official table leaves
/// undefined (0x81, 0x8D, 0x8F, 0x90, 0x9D) mapped to their C1 control. That
/// way the table is a byte ⇄ character bijection and no text is lost on the way
/// back.
///
/// Some games carry messages in other encodings —Shift-JIS, for instance— that
/// their author never touched: those come out as odd characters here and go
/// back to the binary identical. Decoding them properly would mean guessing the
/// encoding field by field, and the price would be the exact round trip, which
/// is the only thing that makes this tool useful.
pub fn dec_text(d: &[u8]) -> String {
    d.iter()
        .map(|b| match b {
            0x80..=0x9F => CP1252_HIGH[(b - 0x80) as usize],
            other => *other as char,
        })
        .collect()
}

pub fn enc_text(s: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(s.len());
    for c in s.chars() {
        if (c as u32) < 0x80 || (0xA0..=0xFF).contains(&(c as u32)) {
            out.push(c as u8);
        } else if let Some(i) = CP1252_HIGH.iter().position(|x| *x == c) {
            out.push(0x80 + i as u8);
        } else {
            // A character cp1252 does not have: it can only come from a
            // hand-edited JSON. It is flagged instead of writing garbage.
            out.push(b'?');
        }
    }
    out
}

// The hand-written codecs of the structs that are not chunk-based live next
// door, but the generated schema only imports this module.
pub use crate::raw::*;
