//! JSON written the way Python's `json.dump(obj, f, indent=1)` writes it:
//! one space of indent per level, `": "` between a key and its value,
//! everything outside ASCII escaped, and no newline at the end.
//!
//! The patches' uses file, `parches/usos.json`, was written that way, and
//! is written the same: it is part of the build that is compared byte by
//! byte.

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
            c if (c as u32) < 0x20 || (c as u32) > 0x7F => {
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

/// The text Python would write for `value`, which holds no floats.
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
    fn it_writes_what_python_writes_with_one_space_of_indent() {
        let value = json!({"a": {"12": [3, "caso"]}, "b": {}, "c": [], "d": "ñ\u{7f}"});
        assert_eq!(
            to_string(&value),
            "{\n \"a\": {\n  \"12\": [\n   3,\n   \"caso\"\n  ]\n },\n \"b\": {},\n \"c\": [],\n \"d\": \"\\u00f1\u{7f}\"\n}"
        );
    }
}
