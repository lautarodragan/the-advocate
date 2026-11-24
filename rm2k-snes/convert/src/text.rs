//! Small text helpers: bytes as hex, and a name quoted for the log.

/// Bytes as lowercase hex, which is how the requests carry them.
pub fn hex(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len() * 2);
    for b in data {
        out.push_str(&format!("{b:02x}"));
    }
    out
}

/// A name quoted for the log: between double quotes, with Rust's escapes.
pub fn quoted(text: &str) -> String {
    format!("{text:?}")
}
