//! Expressions: the tokenizer and the parser.
//!
//! An expression is kept unevaluated until the symbols exist, because most of
//! them name a label that is defined further down the file. The original text
//! is kept alongside the tokens purely for the error messages, which without
//! it would be impossible to place.

use std::collections::HashMap;

/// Every symbol the assembler knows. `None` means "the name exists but has no
/// value here", which is how a label defined inside a `.proc` looks from
/// outside it.
pub type Symbols = HashMap<String, Option<i64>>;

#[derive(Debug)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

fn bad(message: String) -> Error {
    Error(message)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Token {
    /// A literal: `$1F`, `%1010` or `42`, already converted.
    Number(i64),
    /// A built-in, written with a leading dot: `.loword(x)`.
    Func(String),
    /// A symbol.
    Name(String),
    /// One of `-+*/()<>^~&|`.
    Op(char),
}

const OPERATORS: &str = "-+*/()<>^~&|";

pub fn tokenize(text: &str) -> Result<Vec<Token>> {
    let bytes = text.as_bytes();
    let mut tokens = Vec::new();
    let mut pos = 0usize;

    while pos < bytes.len() {
        while pos < bytes.len() && (bytes[pos] as char).is_ascii_whitespace() {
            pos += 1;
        }
        if pos == bytes.len() {
            break;
        }
        let c = bytes[pos] as char;

        if c == '$' || c == '%' || c.is_ascii_digit() {
            let (radix, start) = match c {
                '$' => (16, pos + 1),
                '%' => (2, pos + 1),
                _ => (10, pos),
            };
            let mut end = start;
            while end < bytes.len() && is_digit_of(bytes[end] as char, radix) {
                end += 1;
            }
            if end == start {
                return Err(unreadable(text));
            }
            let digits = &text[start..end];
            let value = i64::from_str_radix(digits, radix)
                .map_err(|_| bad(format!("the number {digits} does not fit in 64 bits")))?;
            tokens.push(Token::Number(value));
            pos = end;
        } else if c == '.' {
            let mut end = pos + 1;
            while end < bytes.len() && (bytes[end] as char).is_ascii_alphabetic() {
                end += 1;
            }
            if end == pos + 1 {
                return Err(unreadable(text));
            }
            tokens.push(Token::Func(text[pos..end].to_string()));
            pos = end;
        } else if c.is_ascii_alphabetic() || c == '_' {
            let mut end = pos + 1;
            while end < bytes.len() && ((bytes[end] as char).is_ascii_alphanumeric() || bytes[end] == b'_') {
                end += 1;
            }
            tokens.push(Token::Name(text[pos..end].to_string()));
            pos = end;
        } else if OPERATORS.contains(c) {
            tokens.push(Token::Op(c));
            pos += 1;
        } else {
            return Err(unreadable(text));
        }
    }
    Ok(tokens)
}

fn is_digit_of(c: char, radix: u32) -> bool {
    match radix {
        16 => c.is_ascii_hexdigit(),
        2 => c == '0' || c == '1',
        _ => c.is_ascii_digit(),
    }
}

fn unreadable(text: &str) -> Error {
    bad(format!("cannot read the expression {text:?}"))
}

/// An expression that has not been evaluated yet.
#[derive(Debug, Clone)]
pub struct Expression {
    pub text: String,
    pub tokens: Vec<Token>,
    /// The `.proc` this expression was written inside, if any. Which symbols
    /// it can see depends on it; see [`Expression::value`].
    pub scope: Option<String>,
}

impl Expression {
    pub fn new(text: &str) -> Result<Expression> {
        let text = text.trim().to_string();
        let tokens = tokenize(&text)?;
        Ok(Expression { text, tokens, scope: None })
    }

    /// An expression that is already a single literal, used for the anonymous
    /// labels once their address is known.
    pub fn number(value: i64) -> Expression {
        Expression { text: value.to_string(), tokens: vec![Token::Number(value)], scope: None }
    }

    /// The literal this expression is, if that is all it is. Lets a table of
    /// plain constants —which is what most of a data file is— be folded at
    /// parse time instead of dragging a parser around per byte.
    pub fn as_literal(&self) -> Option<i64> {
        match self.tokens.as_slice() {
            [Token::Number(n)] => Some(*n),
            _ => None,
        }
    }

    /// The first symbol that appears, which is the one that decides whether
    /// the operand is direct page. In `source + 2` the one that rules is
    /// `source`.
    pub fn base_name(&self) -> Option<&str> {
        self.tokens.iter().find_map(|t| match t {
            Token::Name(n) => Some(n.as_str()),
            _ => None,
        })
    }

    pub fn value(&self, symbols: &Symbols) -> Result<i64> {
        let (value, pos) = self.sum(symbols, 0)?;
        if pos != self.tokens.len() {
            return Err(bad(format!("trailing junk in the expression {:?}", self.text)));
        }
        Ok(value)
    }

    fn sum(&self, symbols: &Symbols, mut pos: usize) -> Result<(i64, usize)> {
        let (mut value, next) = self.product(symbols, pos)?;
        pos = next;
        while let Some(op) = self.operator(pos, "+-|&") {
            let (right, next) = self.product(symbols, pos + 1)?;
            pos = next;
            value = match op {
                '+' => value.wrapping_add(right),
                '-' => value.wrapping_sub(right),
                '|' => value | right,
                _ => value & right,
            };
        }
        Ok((value, pos))
    }

    /// Multiplication and division, which bind tighter than addition.
    fn product(&self, symbols: &Symbols, mut pos: usize) -> Result<(i64, usize)> {
        let (mut value, next) = self.term(symbols, pos)?;
        pos = next;
        while let Some(op) = self.operator(pos, "*/") {
            let (right, next) = self.term(symbols, pos + 1)?;
            pos = next;
            if op == '/' {
                if right == 0 {
                    return Err(bad(format!("division by zero in {:?}", self.text)));
                }
                // Python's floor division, which is what the reference does.
                value = value.div_euclid(right) - i64::from(value.rem_euclid(right) != 0 && right < 0);
            } else {
                value = value.wrapping_mul(right);
            }
        }
        Ok((value, pos))
    }

    fn operator(&self, pos: usize, among: &str) -> Option<char> {
        match self.tokens.get(pos) {
            Some(Token::Op(c)) if among.contains(*c) => Some(*c),
            _ => None,
        }
    }

    fn term(&self, symbols: &Symbols, pos: usize) -> Result<(i64, usize)> {
        let token = self
            .tokens
            .get(pos)
            .ok_or_else(|| bad(format!("unfinished expression: {:?}", self.text)))?;

        match token {
            Token::Number(n) => Ok((*n, pos + 1)),
            Token::Name(name) => Ok((self.lookup(symbols, name)?, pos + 1)),
            Token::Func(name) => {
                if self.tokens.get(pos + 1) != Some(&Token::Op('(')) {
                    return Err(bad(format!("{name} needs parentheses")));
                }
                let (inner, pos) = self.sum(symbols, pos + 2)?;
                if self.tokens.get(pos) != Some(&Token::Op(')')) {
                    return Err(bad(format!("unclosed parenthesis in {:?}", self.text)));
                }
                let pos = pos + 1;
                let lowered = name.to_ascii_lowercase();
                match lowered.as_str() {
                    ".loword" => Ok((inner & 0xFFFF, pos)),
                    ".hiword" => Ok(((inner >> 16) & 0xFFFF, pos)),
                    ".bankbyte" => Ok(((inner >> 16) & 0xFF, pos)),
                    ".lobyte" => Ok((inner & 0xFF, pos)),
                    ".hibyte" => Ok(((inner >> 8) & 0xFF, pos)),
                    _ => Err(bad(format!("there is no function {name}"))),
                }
            }
            Token::Op('(') => {
                let (inner, pos) = self.sum(symbols, pos + 1)?;
                if self.tokens.get(pos) != Some(&Token::Op(')')) {
                    return Err(bad(format!("unclosed parenthesis in {:?}", self.text)));
                }
                Ok((inner, pos + 1))
            }
            // The three prefixes: low byte, high byte and bank byte.
            Token::Op(c @ ('<' | '>' | '^')) => {
                let shift = match c {
                    '<' => 0,
                    '>' => 8,
                    _ => 16,
                };
                let (inner, pos) = self.term(symbols, pos + 1)?;
                Ok(((inner >> shift) & 0xFF, pos))
            }
            Token::Op('-') => {
                let (inner, pos) = self.term(symbols, pos + 1)?;
                Ok((-inner, pos))
            }
            other => Err(bad(format!("did not expect {} in {:?}", shown(other), self.text))),
        }
    }

    /// A name, resolved through the scope of the `.proc` it was written in: a
    /// label local to the procedure wins over a global one of the same name.
    fn lookup(&self, symbols: &Symbols, name: &str) -> Result<i64> {
        if let Some(scope) = &self.scope {
            let qualified = format!("{scope}{name}");
            if let Some(found) = symbols.get(&qualified) {
                return match found {
                    Some(value) => Ok(*value),
                    None => Err(out_of_scope(name)),
                };
            }
        }
        match symbols.get(name) {
            None => Err(bad(format!("unknown symbol: {name}"))),
            // The name exists but has no value, which is how a label from
            // inside a `.proc` looks from outside it. Without this check the
            // missing value travelled on and blew up somewhere with neither a
            // line nor a name, which is one of the worst ways to find out.
            Some(None) => Err(out_of_scope(name)),
            Some(Some(value)) => Ok(*value),
        }
    }
}

fn out_of_scope(name: &str) -> Error {
    bad(format!(
        "symbol out of scope: {name}. If it is a label of another .proc, it cannot be reached from here"
    ))
}

fn shown(token: &Token) -> String {
    match token {
        Token::Number(n) => n.to_string(),
        Token::Func(s) | Token::Name(s) => format!("{s:?}"),
        Token::Op(c) => format!("{c:?}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn symbols(pairs: &[(&str, Option<i64>)]) -> Symbols {
        pairs.iter().map(|(n, v)| (n.to_string(), *v)).collect()
    }

    fn eval(text: &str) -> i64 {
        Expression::new(text).unwrap().value(&Symbols::new()).unwrap()
    }

    #[test]
    fn the_three_literal_bases() {
        assert_eq!(eval("$1F"), 31);
        assert_eq!(eval("%1011"), 11);
        assert_eq!(eval("42"), 42);
    }

    #[test]
    fn multiplication_binds_tighter_than_addition() {
        assert_eq!(eval("1 + 2 * 3"), 7);
        assert_eq!(eval("(1 + 2) * 3"), 9);
    }

    #[test]
    fn the_prefixes_take_a_byte_out_of_an_address() {
        assert_eq!(eval("<$7E30A0"), 0xA0);
        assert_eq!(eval(">$7E30A0"), 0x30);
        assert_eq!(eval("^$7E30A0"), 0x7E);
    }

    #[test]
    fn the_functions_take_a_word_or_a_byte_out_of_one() {
        assert_eq!(eval(".loword($7E30A0)"), 0x30A0);
        assert_eq!(eval(".hiword($7E30A0)"), 0x7E);
        assert_eq!(eval(".bankbyte($7E30A0)"), 0x7E);
        assert_eq!(eval(".lobyte($7E30A0)"), 0xA0);
        assert_eq!(eval(".hibyte($7E30A0)"), 0x30);
    }

    #[test]
    fn a_symbol_is_read_from_the_table() {
        let table = symbols(&[("source", Some(0x1234))]);
        let e = Expression::new("source + 2").unwrap();
        assert_eq!(e.value(&table).unwrap(), 0x1236);
        assert_eq!(e.base_name(), Some("source"));
    }

    #[test]
    fn a_symbol_that_does_not_exist_is_named_in_the_error() {
        let e = Expression::new("nowhere + 1").unwrap();
        let err = e.value(&Symbols::new()).unwrap_err();
        assert!(err.0.contains("unknown symbol: nowhere"), "{err}");
    }

    /// A label of another `.proc`: the name is there, the value is not.
    #[test]
    fn a_symbol_with_no_value_says_it_is_out_of_scope() {
        let table = symbols(&[("loop", None)]);
        let err = Expression::new("loop").unwrap().value(&table).unwrap_err();
        assert!(err.0.contains("out of scope: loop"), "{err}");
    }

    #[test]
    fn a_scope_makes_the_local_label_win_over_the_global_one() {
        let table = symbols(&[("loop", None), ("draw::loop", Some(0x8100))]);
        let mut e = Expression::new("loop").unwrap();
        e.scope = Some("draw::".to_string());
        assert_eq!(e.value(&table).unwrap(), 0x8100);
    }

    #[test]
    fn division_by_zero_is_an_error_and_not_a_crash() {
        let err = Expression::new("4 / 0").unwrap().value(&Symbols::new()).unwrap_err();
        assert!(err.0.contains("division by zero"), "{err}");
    }

    #[test]
    fn a_character_that_is_not_part_of_the_grammar_quotes_the_expression() {
        let err = tokenize("1 ? 2").unwrap_err();
        assert!(err.0.contains("cannot read the expression"), "{err}");
    }

    #[test]
    fn an_unclosed_parenthesis_says_so() {
        let err = Expression::new("(1 + 2").unwrap().value(&Symbols::new()).unwrap_err();
        assert!(err.0.contains("unclosed parenthesis"), "{err}");
    }

    #[test]
    fn a_function_without_parentheses_says_so() {
        let err = Expression::new(".loword 3").unwrap().value(&Symbols::new()).unwrap_err();
        assert!(err.0.contains("needs parentheses"), "{err}");
    }

    #[test]
    fn an_unknown_function_is_refused() {
        let err = Expression::new(".midword(3)").unwrap().value(&Symbols::new()).unwrap_err();
        assert!(err.0.contains("there is no function"), "{err}");
    }

    #[test]
    fn negatives_are_kept_as_negatives() {
        assert_eq!(eval("-3"), -3);
        assert_eq!(eval("8 - 12"), -4);
    }

    /// Floor division, so that a negative quotient rounds the same way the
    /// reference implementation rounds it.
    #[test]
    fn division_rounds_towards_minus_infinity() {
        assert_eq!(eval("7 / 2"), 3);
        assert_eq!(eval("-7 / 2"), -4);
    }

    #[test]
    fn a_plain_literal_is_recognised_as_one() {
        assert_eq!(Expression::new("$20").unwrap().as_literal(), Some(0x20));
        assert_eq!(Expression::new("$20 + 1").unwrap().as_literal(), None);
    }
}
