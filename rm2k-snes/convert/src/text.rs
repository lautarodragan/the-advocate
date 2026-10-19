//! Small text helpers: bytes as hex, a name quoted for the log, and a
//! percentage rounded the way the log always printed it.

/// Bytes as lowercase hex, which is how the requests carry them.
pub fn hex(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len() * 2);
    for b in data {
        out.push_str(&format!("{b:02x}"));
    }
    out
}

/// Hex back to bytes.
pub fn unhex(text: &str) -> Vec<u8> {
    (0..text.len() / 2)
        .map(|i| u8::from_str_radix(&text[2 * i..2 * i + 2], 16).unwrap_or(0))
        .collect()
}

/// A name quoted as the log quotes it: between single quotes, or double
/// ones if it has a single quote and no double one.
pub fn repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::new();
    out.push(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => {
                out.push_str(&format!("\\x{:02x}", c as u32))
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// A float with no decimals, rounding half to even, as `%.0f` does.
// Two branches give `floor` and two `floor + 1.0`: they are the rule's four
// cases —below half, above, and half on an even or an odd floor—, spelled as
// it reads.
#[allow(clippy::if_same_then_else)]
pub fn round0(value: f64) -> String {
    let floor = value.floor();
    let diff = value - floor;
    let rounded = if diff > 0.5 {
        floor + 1.0
    } else if diff < 0.5 {
        floor
    } else if floor % 2.0 == 0.0 {
        floor
    } else {
        floor + 1.0
    };
    format!("{rounded:.0}")
}
