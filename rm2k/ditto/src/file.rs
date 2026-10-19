//! A whole file: the header and what comes after it.
//!
//! The header is a BER length and a name (`LcfMapUnit`, `LcfDataBase`,
//! `LcfMapTree`), and it is kept in the JSON instead of being taken for
//! granted: liblcf has an option to preserve it precisely because there are
//! games with a changed name, and rewriting it would give a different binary.

use crate::lcf::*;
use crate::schema::*;
use serde::{Deserialize, Serialize};

// The database is much bigger than a map or the tree, and clippy would box
// it; but a document is read or written one at a time, so there is no array
// of them for the size to waste, and boxing would only add a `*` to every
// match on it here and in whoever reads one.
#[allow(clippy::large_enum_variant)]
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "format")]
pub enum Document {
    #[serde(rename = "ldb")]
    Ldb { header: String, data: Database },
    #[serde(rename = "lmu")]
    Lmu { header: String, data: Map },
    #[serde(rename = "lmt")]
    Lmt { header: String, data: TreeMap },
}

impl Document {
    pub fn extension(&self) -> &'static str {
        match self {
            Document::Ldb { .. } => "ldb",
            Document::Lmu { .. } => "lmu",
            Document::Lmt { .. } => "lmt",
        }
    }
}

/// Whether a database is RPG Maker 2003's: `System.ldb_id == 2003`, the way
/// liblcf's `GetEngineVersion` tells. The version decides the defaults of
/// `Actor`, which comes **before** `System` in the file, so it is looked up
/// first, walking the top-level chunks without decoding anything but the
/// `System` one. See `Writer::is2k3` for what depends on it.
fn ldb_is_2k3(d: &[u8], start: usize) -> Result<bool> {
    const SYSTEM: u32 = 0x16;
    let mut l = Reader::new(d);
    l.pos = start;
    while !l.eof() {
        let id = l.ber()? as u32;
        if id == 0 {
            break;
        }
        let length = l.ber()? as usize;
        let body = l.bytes(length)?;
        if id == SYSTEM {
            let system: System = dec_struct(body, false)?;
            return Ok(system.ldb_id == 2003);
        }
    }
    Ok(false)
}

pub fn read(d: &[u8]) -> Result<Document> {
    let mut l = Reader::new(d);
    let n = l.ber()? as usize;
    let header = dec_text(l.bytes(n)?);
    match header.as_str() {
        "LcfDataBase" => {
            let is2k3 = ldb_is_2k3(d, l.pos)?;
            Ok(Document::Ldb {
                header,
                data: read_struct(&mut l.version(is2k3))?,
            })
        }
        "LcfMapUnit" => Ok(Document::Lmu {
            header,
            data: read_struct(&mut l)?,
        }),
        "LcfMapTree" => Ok(Document::Lmt {
            header,
            data: TreeMap::read_tree(&mut l)?,
        }),
        other => error(format!("unknown header: {other:?}")),
    }
}

pub fn write(doc: &Document) -> Result<Vec<u8>> {
    let mut e = Writer::new();
    let head = match doc {
        Document::Ldb { header, .. }
        | Document::Lmu { header, .. }
        | Document::Lmt { header, .. } => enc_text(header),
    };
    e.ber(head.len() as i32);
    e.bytes(&head);
    match doc {
        Document::Ldb { data, .. } => {
            e.is2k3 = data.system.ldb_id == 2003;
            write_struct(data, &mut e)?
        }
        Document::Lmu { data, .. } => write_struct(data, &mut e)?,
        Document::Lmt { data, .. } => data.write_tree(&mut e)?,
    }
    Ok(e.b)
}
