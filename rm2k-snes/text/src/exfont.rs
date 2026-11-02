//! RPG_RT's ExFont icons in a text: a `$` and a letter, `$A` to `$Z` and
//! `$a` to `$z`, is one of 52 icons twelve pixels wide —easyrpg's
//! `Utils::ExFontNext`—, in a name, a description or a message alike. Any
//! other `$` is a `$`.
//!
//! **An icon travels as two characters**, its left half and its right
//! half, each six pixels wide, from Unicode's private use area: the
//! console's composer takes glyphs at most [`crate::font::INK_MAX`] wide,
//! and two halves drawn one after the other, each with its shadow, are the
//! icon drawn whole —the right half's ink covers the left half's shadow
//! where they meet, as one glyph's ink covers its own—. A font draws them
//! when it was given the game's icons —see `Font::with_exfont`—; one that
//! was not drops them, which is what [`crate::plain`] stands in for a half:
//! nothing.
//!
//! The icons themselves come from a sheet the project names: see
//! `rm2k_render::exfont`.

/// Where the halves start: icon `i`'s left half is this plus `2 * i`, its
/// right half the one after.
pub const HALF_FIRST: u32 = 0xE000;

/// How many icons there are, and how many halves.
pub const ICONS: usize = 52;
pub const HALVES: usize = 2 * ICONS;

/// How many columns a half moves the line: six, so an icon is RM2k's
/// twelve. Letter spacing does not widen it —see `Font::with_spacing`—.
pub const HALF_ADVANCE: u8 = 6;

/// The icon a code's letter names: `A` to `Z` are 0 to 25, `a` to `z` 26
/// to 51.
pub fn icon_of_letter(c: char) -> Option<usize> {
    match c {
        'A'..='Z' => Some(c as usize - 'A' as usize),
        'a'..='z' => Some(c as usize - 'a' as usize + 26),
        _ => None,
    }
}

/// The letter of icon `icon`'s code.
pub fn letter_of_icon(icon: usize) -> char {
    let base = if icon < 26 { b'A' } else { b'a' - 26 };
    (base + icon as u8) as char
}

/// Icon `icon`'s two halves, left and right.
pub fn halves(icon: usize) -> [char; 2] {
    let left = HALF_FIRST + 2 * icon as u32;
    [
        char::from_u32(left).expect("private use"),
        char::from_u32(left + 1).expect("private use"),
    ]
}

/// Which half `c` is, as `(icon, side)` with side 0 the left one; `None`
/// if it is not a half.
pub fn half_of(c: char) -> Option<(usize, usize)> {
    let i = (c as u32).checked_sub(HALF_FIRST)? as usize;
    (i < HALVES).then_some((i / 2, i % 2))
}

/// Whether `c` is a half of an icon.
pub fn is_half(c: char) -> bool {
    half_of(c).is_some()
}

/// `text` with every code as its icon's two halves: a database text, a
/// name or a description, where RPG_RT reads no escape.
pub fn with_icons(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < chars.len() {
        match (chars[i], chars.get(i + 1).copied().and_then(icon_of_letter)) {
            ('$', Some(icon)) => {
                out.extend(halves(icon));
                i += 2;
            }
            (c, _) => {
                out.push(c);
                i += 1;
            }
        }
    }
    out
}

/// `text` with its halves written back as codes: a left half as its `$`
/// and letter, a right half as nothing.
pub fn with_codes(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match half_of(c) {
            Some((icon, 0)) => {
                out.push('$');
                out.push(letter_of_icon(icon));
            }
            Some(_) => {}
            None => out.push(c),
        }
    }
    out
}

/// `text` without its icons: the codes and the halves gone, for what is
/// written where no icon can be drawn.
pub fn without_icons(text: &str) -> String {
    with_icons(text).chars().filter(|&c| !is_half(c)).collect()
}

/// The icons `text` draws, as halves already, in order and once each.
pub fn icons_in(text: &str) -> Vec<usize> {
    let mut out = Vec::new();
    for c in text.chars() {
        if let Some((icon, _)) = half_of(c) {
            if !out.contains(&icon) {
                out.push(icon);
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `$NTónico Fuerte`, as Zounds names its items: `$N` is icon 13. A `$` before
    /// anything but a letter is a `$`, and so is one at the end.
    #[test]
    fn a_dollar_and_a_letter_is_an_icon() {
        let text = with_icons("$NTónico Fuerte");
        let [l, r] = halves(13);
        assert_eq!(text, format!("{l}{r}Tónico Fuerte"));
        assert_eq!(
            with_icons("100$ $1 $$z $"),
            format!("100$ $1 ${}{} $", halves(51)[0], halves(51)[1])
        );
        assert_eq!(with_codes(&text), "$NTónico Fuerte");
        assert_eq!(icons_in(&with_icons("$N$O $N")), vec![13, 14]);
        assert_eq!(half_of(r), Some((13, 1)));
        assert_eq!(letter_of_icon(26), 'a');
    }
}
