//! `%`-formatting as the converter wrote the `.inc` with until 2026-10-01:
//! the templates of the long blocks of constants are kept as they were, so
//! that their text is the same character by character, and this fills them.
//!
//! It knows what those templates use: `%d`, `%s`, `%X` and `%f`, with the
//! `-` and `0` flags, a width and a precision; and `%%`.

/// A value for a `%` conversion.
#[derive(Clone, Debug, PartialEq)]
pub enum Arg {
    Int(i64),
    Str(String),
    Float(f64),
}

impl From<i64> for Arg {
    fn from(v: i64) -> Self {
        Arg::Int(v)
    }
}

impl From<i32> for Arg {
    fn from(v: i32) -> Self {
        Arg::Int(v.into())
    }
}

impl From<u32> for Arg {
    fn from(v: u32) -> Self {
        Arg::Int(v.into())
    }
}

impl From<u8> for Arg {
    fn from(v: u8) -> Self {
        Arg::Int(v.into())
    }
}

impl From<usize> for Arg {
    fn from(v: usize) -> Self {
        Arg::Int(v as i64)
    }
}

impl From<bool> for Arg {
    fn from(v: bool) -> Self {
        Arg::Int(v.into())
    }
}

impl From<&str> for Arg {
    fn from(v: &str) -> Self {
        Arg::Str(v.to_string())
    }
}

impl From<String> for Arg {
    fn from(v: String) -> Self {
        Arg::Str(v)
    }
}

impl From<f64> for Arg {
    fn from(v: f64) -> Self {
        Arg::Float(v)
    }
}

/// `template % args`. Panics on a template that does not match its
/// arguments: that is a mistake in this crate, not in its input.
pub fn format(template: &str, args: &[Arg]) -> String {
    let mut out = String::with_capacity(template.len() + 8 * args.len());
    let mut next = args.iter();
    let mut chars = template.chars().peekable();
    while let Some(c) = chars.next() {
        if c != '%' {
            out.push(c);
            continue;
        }
        if chars.peek() == Some(&'%') {
            chars.next();
            out.push('%');
            continue;
        }
        let (mut left, mut zero) = (false, false);
        while let Some(&f) = chars.peek() {
            match f {
                '-' => left = true,
                '0' => zero = true,
                _ => break,
            }
            chars.next();
        }
        let mut width = 0usize;
        while let Some(d) = chars.peek().and_then(|c| c.to_digit(10)) {
            width = width * 10 + d as usize;
            chars.next();
        }
        let mut precision = None;
        if chars.peek() == Some(&'.') {
            chars.next();
            let mut p = 0usize;
            while let Some(d) = chars.peek().and_then(|c| c.to_digit(10)) {
                p = p * 10 + d as usize;
                chars.next();
            }
            precision = Some(p);
        }
        let conversion = chars.next().expect("a % at the end of a template");
        let arg = next
            .next()
            .unwrap_or_else(|| panic!("too few arguments for {template:?}"));
        let body = match (conversion, arg) {
            ('d', Arg::Int(v)) => v.to_string(),
            ('X', Arg::Int(v)) => {
                if *v < 0 {
                    format!("-{:X}", -v)
                } else {
                    format!("{v:X}")
                }
            }
            ('x', Arg::Int(v)) => format!("{v:x}"),
            ('s', Arg::Str(s)) => s.clone(),
            ('s', Arg::Int(v)) => v.to_string(),
            ('f', Arg::Float(v)) => format!("{v:.*}", precision.unwrap_or(6)),
            (c, a) => panic!("%{c} with {a:?} in {template:?}"),
        };
        let pad = width.saturating_sub(body.chars().count());
        if left {
            out.push_str(&body);
            out.extend(std::iter::repeat_n(' ', pad));
        } else if zero && conversion != 's' {
            let (sign, digits) = match body.strip_prefix('-') {
                Some(d) => ("-", d),
                None => ("", body.as_str()),
            };
            out.push_str(sign);
            out.extend(std::iter::repeat_n('0', pad));
            out.push_str(digits);
        } else {
            out.extend(std::iter::repeat_n(' ', pad));
            out.push_str(&body);
        }
    }
    assert!(next.next().is_none(), "too many arguments for {template:?}");
    out
}

/// `format!`-like sugar: `pyf!("%d and %s", 3, "x")`.
#[macro_export]
macro_rules! pyf {
    ($template:expr $(, $arg:expr)* $(,)?) => {
        $crate::pyfmt::format($template, &[$($crate::pyfmt::Arg::from($arg)),*])
    };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_conversions_the_templates_use_come_out_as_python_wrote_them() {
        assert_eq!(
            format("%d|%-6d|%4d", &[1.into(), 23.into(), 5.into()]),
            "1|23    |   5"
        );
        assert_eq!(
            format(
                "$%04X $%02X $%05X",
                &[0x7800.into(), 0xFF.into(), 0x10000.into()]
            ),
            "$7800 $FF $10000"
        );
        assert_eq!(format("%s:%d %%", &["a".into(), (-3).into()]), "a:-3 %");
        assert_eq!(
            format("%6.1f|%.1f", &[1.25.into(), 0.05.into()]),
            "   1.2|0.1"
        );
        assert_eq!(
            format("%-18s= $%04X", &["BA_SE".into(), 0xFFFF.into()]),
            "BA_SE             = $FFFF"
        );
        assert_eq!(crate::pyf!("%d %s", 2, "x"), "2 x");
    }
}
