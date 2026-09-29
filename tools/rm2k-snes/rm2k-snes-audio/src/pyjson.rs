//! JSON written the way Python's `json.dump(obj, f, indent=1)` writes it:
//! one space of indent per level, `", "` never, `": "` between a key and
//! its value, everything outside ASCII escaped, and no newline at the end.
//!
//! `musica.json` was written that way until 2026-09-29, and the tools that
//! read it compare it whole; so it keeps being written the same.

use serde_json::Value;

fn string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0C}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 || (c as u32) > 0x7E => {
                let mut units = [0u16; 2];
                for u in c.encode_utf16(&mut units) {
                    out.push_str(&format!("\\u{u:04x}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

fn write(out: &mut String, value: &Value, level: usize) {
    let indent = |out: &mut String, level: usize| {
        out.push('\n');
        out.push_str(&" ".repeat(level));
    };
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(&n.to_string()),
        Value::String(s) => string(out, s),
        Value::Array(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                indent(out, level + 1);
                write(out, item, level + 1);
            }
            indent(out, level);
            out.push(']');
        }
        Value::Object(map) => {
            if map.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push('{');
            for (i, (k, v)) in map.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                indent(out, level + 1);
                string(out, k);
                out.push_str(": ");
                write(out, v, level + 1);
            }
            indent(out, level);
            out.push('}');
        }
    }
}

/// The text Python would write for `value`. Only integers are written as
/// numbers the same way Python does; a float would need its `repr`.
pub fn to_string(value: &Value) -> String {
    let mut out = String::new();
    write(&mut out, value, 0);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn it_indents_like_python() {
        let v = json!({"temas": [{"nombre": "a\u{f1}", "pista": null}], "vacio": []});
        assert_eq!(
            to_string(&v),
            "{\n \"temas\": [\n  {\n   \"nombre\": \"a\\u00f1\",\n   \"pista\": null\n  }\n ],\n \"vacio\": []\n}"
        );
    }
}
