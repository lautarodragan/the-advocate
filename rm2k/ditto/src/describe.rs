//! The schema, published as JSON: what `ditto schema` writes.
//!
//! Ditto's JSON is not self-describing, and on purpose: it **omits every
//! field that holds its default** —the same rule the binary follows, and what
//! keeps the dump from being a third larger— and it stores enums **by name**.
//! So a reader that is not Ditto cannot know what an absent field holds, nor
//! what number `"auto_start"` is. It needs the schema.
//!
//! That is what this writes out. The data comes from
//! `schema::description`, which `cargo xtask generate` emits in the same run
//! that emits the structs themselves, so the two say the same thing by
//! construction.
//!
//! The order is the schema's: structs alphabetically —which is how the
//! generator holds them— and fields in the order of their chunks, which is
//! the order the binary has them in. It is written out by hand instead of
//! through `serde_json::Value` for exactly that: a `Value` map sorts its keys
//! and would turn the chunk order into an alphabetical one.

use crate::schema::description::{ENUMS, STRUCTS};

/// The whole schema as a JSON document.
pub fn to_json() -> String {
    let mut out = String::from("{\n  \"fields\": {\n");
    for (n, (name, fields)) in STRUCTS.iter().enumerate() {
        out.push_str(&format!("    {}: {{\n", quote(name)));
        for (m, f) in fields.iter().enumerate() {
            out.push_str(&format!(
                "      {}: {{\"chunk\": {}, \"default\": {}, \"enum\": {}, \
                 \"persist\": {}, \"nested\": {}}}{}\n",
                quote(f.name),
                match f.chunk {
                    Some(c) => c.to_string(),
                    None => "null".to_string(),
                },
                f.default.unwrap_or("null"),
                option(f.enumeration),
                f.persist,
                option(f.nested),
                comma(m, fields.len()),
            ));
        }
        out.push_str(&format!("    }}{}\n", comma(n, STRUCTS.len())));
    }
    out.push_str("  },\n  \"enums\": {\n");
    for (n, (name, variants)) in ENUMS.iter().enumerate() {
        out.push_str(&format!("    {}: {{\n", quote(name)));
        for (m, (variant, value)) in variants.iter().enumerate() {
            out.push_str(&format!(
                "      {}: {}{}\n",
                quote(variant),
                value,
                comma(m, variants.len())
            ));
        }
        out.push_str(&format!("    }}{}\n", comma(n, ENUMS.len())));
    }
    out.push_str("  }\n}\n");
    out
}

fn comma(n: usize, len: usize) -> &'static str {
    if n + 1 == len {
        ""
    } else {
        ","
    }
}

fn option(v: Option<&str>) -> String {
    match v {
        Some(s) => quote(s),
        None => "null".to_string(),
    }
}

/// A JSON string. The names here are identifiers out of the CSV, so there is
/// nothing to escape in practice, but escaping it properly costs four lines
/// and not doing it would make the day one of them carries a quote a silently
/// broken file.
fn quote(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}
