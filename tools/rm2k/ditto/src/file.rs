//! A whole file: the header and what comes after it.
//!
//! The header is a BER length and a name (`LcfMapUnit`, `LcfDataBase`,
//! `LcfMapTree`), and it is kept in the JSON instead of being taken for
//! granted: liblcf has an option to preserve it precisely because there are
//! games with a changed name, and rewriting it would give a different binary.

use crate::lcf::*;
use crate::schema::*;
use serde::{Deserialize, Serialize};

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

pub fn read(d: &[u8]) -> Result<Document> {
    let mut l = Reader::new(d);
    let n = l.ber()? as usize;
    let header = dec_text(l.bytes(n)?);
    match header.as_str() {
        "LcfDataBase" => Ok(Document::Ldb {
            header,
            data: read_struct(&mut l)?,
        }),
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
        Document::Ldb { data, .. } => write_struct(data, &mut e)?,
        Document::Lmu { data, .. } => write_struct(data, &mut e)?,
        Document::Lmt { data, .. } => data.write_tree(&mut e)?,
    }
    Ok(e.b)
}
