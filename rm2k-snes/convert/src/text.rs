//! Small text helpers: bytes as hex, and a name quoted for the log.

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

/// A name quoted for the log: between double quotes, with Rust's escapes.
pub fn quoted(text: &str) -> String {
    format!("{text:?}")
}
