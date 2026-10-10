//! Error messages put together inside a `const fn`.
//!
//! A broken declaration has to stop the compilation **naming the opcode**:
//! this crate's whole job is to be the one place a number is written, so
//! the moment one is wrong it has to say exactly where. `panic!` in a
//! constant takes a single `&str` and nothing to format, so the message is
//! built here first, by hand, in a fixed buffer.

/// Long enough for any message here; what does not fit is cut.
const CAPACITY: usize = 256;

#[derive(Clone, Copy)]
pub struct Message {
    bytes: [u8; CAPACITY],
    len: usize,
}

impl Message {
    pub const fn new() -> Self {
        Message {
            bytes: [0; CAPACITY],
            len: 0,
        }
    }

    pub const fn push(mut self, text: &str) -> Self {
        let text = text.as_bytes();
        let mut i = 0;
        // A cut in the middle of a character would leave invalid UTF-8; the
        // texts here are ASCII, and `fail` says so if one is not.
        while i < text.len() && self.len < CAPACITY {
            self.bytes[self.len] = text[i];
            self.len += 1;
            i += 1;
        }
        self
    }

    /// `0x` and two hexadecimal digits.
    pub const fn hex(self, value: u8) -> Self {
        const DIGITS: &[u8; 16] = b"0123456789ABCDEF";
        let digits = [b'0', b'x', DIGITS[(value >> 4) as usize], DIGITS[(value & 15) as usize]];
        match core::str::from_utf8(&digits) {
            Ok(text) => self.push(text),
            Err(_) => self,
        }
    }

    pub const fn number(mut self, mut value: usize) -> Self {
        let mut digits = [0u8; 20];
        let mut n = 0;
        loop {
            digits[n] = b'0' + (value % 10) as u8;
            n += 1;
            value /= 10;
            if value == 0 {
                break;
            }
        }
        while n > 0 && self.len < CAPACITY {
            n -= 1;
            self.bytes[self.len] = digits[n];
            self.len += 1;
        }
        self
    }

    pub const fn fail(&self) -> ! {
        let (text, _) = self.bytes.split_at(self.len);
        match core::str::from_utf8(text) {
            Ok(text) => panic!("{}", text),
            Err(_) => panic!("a declaration is wrong, and its message is not ASCII"),
        }
    }
}

/// `a == b`, which `&str` does not have in a `const fn`.
pub const fn same(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    let mut i = 0;
    while i < a.len() {
        if a[i] != b[i] {
            return false;
        }
        i += 1;
    }
    true
}
