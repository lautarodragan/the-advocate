//! Bytes as hex text, which is how a request carries them in JSON.

use crate::fail::{Bad, Result};

pub fn encode(data: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(data.len() * 2);
    for b in data {
        out.push(DIGITS[usize::from(b >> 4)] as char);
        out.push(DIGITS[usize::from(b & 15)] as char);
    }
    out
}

pub fn decode(text: &str) -> Result<Vec<u8>> {
    let digit = |c: u8| match c {
        b'0'..=b'9' => Ok(c - b'0'),
        b'a'..=b'f' => Ok(c - b'a' + 10),
        b'A'..=b'F' => Ok(c - b'A' + 10),
        _ => Err(Bad::answer(format!("{:?} is not hex", c as char))),
    };
    let bytes = text.as_bytes();
    if !bytes.len().is_multiple_of(2) {
        return Err(Bad::answer("hex text of an odd length"));
    }
    bytes
        .chunks(2)
        .map(|p| Ok((digit(p[0])? << 4) | digit(p[1])?))
        .collect()
}

/// For `#[serde(deserialize_with = "hex::bytes")]`: a request's bytes.
pub fn bytes<'de, D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Vec<u8>, D::Error> {
    let text: String = serde::Deserialize::deserialize(d)?;
    decode(&text).map_err(|bad| serde::de::Error::custom(bad.message()))
}

#[cfg(test)]
mod tests {
    #[test]
    fn hex_goes_and_comes_back() {
        assert_eq!(super::encode(&[0, 0xAB, 0x10]), "00ab10");
        assert_eq!(super::decode("00AB10").unwrap(), vec![0, 0xAB, 0x10]);
        assert!(super::decode("0").is_err());
    }
}
