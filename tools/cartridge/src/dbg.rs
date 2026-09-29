//! What `ld65` writes in its debug file, read back.
//!
//! One record per line: its kind, a tab, and `key=value` pairs separated by
//! commas, with the strings between double quotes.

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

/// One record's fields. Quoted values come back without their quotes.
pub type Record = HashMap<String, String>;

/// The records of kind `kind`, in file order.
pub fn records(text: &str, kind: &str) -> Vec<Record> {
    let prefix = format!("{kind}\t");
    text.lines()
        .filter(|l| l.starts_with(&prefix))
        .map(|l| fields(&l[prefix.len()..]))
        .collect()
}

/// `id=0,name="x, y",val=0x1` → {id: 0, name: "x, y", val: 0x1}.
fn fields(text: &str) -> Record {
    let mut out = Record::new();
    let mut rest = text;
    while !rest.is_empty() {
        let Some(eq) = rest.find('=') else { break };
        let key = rest[..eq].trim_start_matches(',').trim().to_string();
        let after = &rest[eq + 1..];
        let (value, next) = if let Some(quoted) = after.strip_prefix('"') {
            match quoted.find('"') {
                Some(end) => (&quoted[..end], &quoted[end + 1..]),
                None => (quoted, ""),
            }
        } else {
            let end = after
                .find(|c: char| c == ',' || c.is_whitespace())
                .unwrap_or(after.len());
            (&after[..end], &after[end..])
        };
        out.insert(key, value.to_string());
        rest = next.trim_start_matches(|c: char| c == ',' || c.is_whitespace());
    }
    out
}

/// An integer the way the debug file writes it: `0x…` or decimal.
pub fn number(text: &str) -> Option<i64> {
    match text.strip_prefix("0x").or_else(|| text.strip_prefix("0X")) {
        Some(hex) => i64::from_str_radix(hex, 16).ok(),
        None => text.parse().ok(),
    }
}

/// The symbols in the debug file, as {name: value}.
///
/// Labels inside a `.proc` come out as `proc::label`. `ld65` writes the
/// values as unsigned 32 bits, so a negative constant is given back its sign.
pub fn symbols(text: &str) -> BTreeMap<String, i64> {
    let mut scopes: HashMap<String, (String, Option<String>)> = HashMap::new();
    for c in records(text, "scope") {
        if let Some(id) = c.get("id") {
            scopes.insert(
                id.clone(),
                (c.get("name").cloned().unwrap_or_default(), c.get("parent").cloned()),
            );
        }
    }
    let mut table = BTreeMap::new();
    for c in records(text, "sym") {
        let kind = c.get("type").map(String::as_str);
        if !matches!(kind, Some("lab") | Some("equ")) {
            continue;
        }
        let (Some(name), Some(val)) = (c.get("name"), c.get("val")) else {
            continue;
        };
        let mut parts = vec![name.clone()];
        let mut scope = c.get("scope").cloned();
        while let Some((name, parent)) = scope.as_ref().and_then(|s| scopes.get(s)) {
            if !name.is_empty() {
                parts.insert(0, name.clone());
            }
            scope = parent.clone();
        }
        let Some(mut value) = number(val) else { continue };
        if value >= 1 << 31 {
            value -= 1 << 32;
        }
        table.insert(parts.join("::"), value);
    }
    table
}

/// [`symbols`] from a file.
pub fn symbols_of(path: &Path) -> Result<BTreeMap<String, i64>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(symbols(&text))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quoted_values_keep_their_commas() {
        let r = &records("file\tid=3,name=\"a, b.s\",size=10\n", "file")[0];
        assert_eq!(r["name"], "a, b.s");
        assert_eq!(r["size"], "10");
        assert_eq!(r["id"], "3");
    }

    #[test]
    fn symbols_come_out_with_their_scope_and_sign() {
        let text = "scope\tid=0,name=\"\",mod=0,size=10\n\
            scope\tid=1,name=\"battle_run\",mod=0,type=scope,size=5,parent=0\n\
            sym\tid=0,name=\"enc_random\",addrsize=absolute,scope=0,val=0x19FDD,seg=1,type=lab\n\
            sym\tid=1,name=\"espera\",addrsize=absolute,scope=1,val=0x1993E,seg=1,type=lab\n\
            sym\tid=2,name=\"PICTURE_X\",addrsize=absolute,scope=0,val=0xFFFFFFF3,type=equ\n\
            sym\tid=3,name=\"afuera\",addrsize=absolute,scope=0,type=imp\n";
        let table = symbols(text);
        assert_eq!(table.len(), 3);
        assert_eq!(table["enc_random"], 0x19FDD);
        assert_eq!(table["battle_run::espera"], 0x1993E);
        assert_eq!(table["PICTURE_X"], -13);
    }
}
