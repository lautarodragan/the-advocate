//! JSON written the way Python's `json.dump(obj, f, indent=1)` writes it:
//! one space of indent per level, `", "` never, `": "` between a key and
//! its value, everything outside ASCII escaped, and no newline at the end.
//!
//! `music.json` was written that way until 2026-09-29, and the tools that
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
        Value::Number(n) => match n.as_f64() {
            Some(x) if n.is_f64() => out.push_str(&float(x)),
            _ => out.push_str(&n.to_string()),
        },
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

/// A float as Python's `repr` writes it: the shortest digits that read back
/// the same —Rust finds those too—, positional from 1e-4 up to 1e16 and with
/// at least one decimal, and scientific outside, with a sign and at least
/// two digits of exponent: `1e-05`, `1.5e+16`.
pub fn float(x: f64) -> String {
    if x.is_nan() {
        return "NaN".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "Infinity" } else { "-Infinity" }.into();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0" } else { "0.0" }.into();
    }
    let scientific = format!("{:e}", x.abs());
    let (mantissa, exponent) = scientific.split_once('e').unwrap();
    let exponent: i32 = exponent.parse().unwrap();
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let sign = if x < 0.0 { "-" } else { "" };
    if (-4..16).contains(&exponent) {
        let text = if exponent >= 0 {
            let point = exponent as usize + 1;
            let whole = format!("{digits:0<point$}");
            let (int, frac) = whole.split_at(point);
            format!("{int}.{}", if frac.is_empty() { "0" } else { frac })
        } else {
            format!("0.{}{digits}", "0".repeat((-exponent - 1) as usize))
        };
        return format!("{sign}{text}");
    }
    let (first, rest) = digits.split_at(1);
    let rest = if rest.is_empty() { String::new() } else { format!(".{rest}") };
    format!("{sign}{first}{rest}e{}{:02}", if exponent < 0 { '-' } else { '+' }, exponent.abs())
}

/// The text Python would write for `value`.
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
    fn floats_are_written_like_repr() {
        for (x, text) in [
            (2.542840700201702, "2.542840700201702"),
            (3.0, "3.0"),
            (0.5, "0.5"),
            (1e-5, "1e-05"),
            (0.0001, "0.0001"),
            (1.5e16, "1.5e+16"),
            (1e15, "1000000000000000.0"),
            (-12.25, "-12.25"),
            (0.1 + 0.2, "0.30000000000000004"),
        ] {
            assert_eq!(float(x), text);
        }
    }

    #[test]
    fn it_indents_like_python() {
        let v = json!({"songs": [{"name": "a\u{f1}", "track": null}], "empty": []});
        assert_eq!(
            to_string(&v),
            "{\n \"songs\": [\n  {\n   \"name\": \"a\\u00f1\",\n   \"track\": null\n  }\n ],\n \"empty\": []\n}"
        );
    }
}
