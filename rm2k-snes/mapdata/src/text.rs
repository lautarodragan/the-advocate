//! How a name is quoted in the `.inc`'s comments.

/// `name` between double quotes, with Rust's escapes. The comments that
/// head each map's record carry it; the console's tests read the map order
/// from those lines, by the number before it, so the quoting is free.
pub fn quoted(name: &str) -> String {
    format!("{name:?}")
}

#[cfg(test)]
mod tests {
    use super::quoted;

    #[test]
    fn a_name_is_quoted_with_its_escapes() {
        assert_eq!(quoted("Miller's Cottage"), "\"Miller's Cottage\"");
        assert_eq!(quoted("a\"b"), "\"a\\\"b\"");
        assert_eq!(quoted("año"), "\"año\"");
    }
}
