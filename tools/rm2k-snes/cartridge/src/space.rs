//! How much space a built ROM has left, from what the build left next to it
//! —`ld65`'s debug file and the memory map—: nothing is relinked.
//!
//! * **Data banks**: the `BANKnn` from [`banks::FIRST_BANK`], against the
//!   ones that fit in the `.cfg`. A "used" bank is one that has something;
//!   the "free" ones are those after the last used one. **It is the number
//!   that matters**, and not a percentage: the packing leaves gaps, and the
//!   reserved banks are not ROM.
//! * **Gaps**: what is left over inside the used ones.
//! * **Bank 0**: the `.cfg`'s `ROM` area minus `CODE` and `TABLES`, which
//!   share it.
//! * **Bank 1**: what the `.align $8000` in the runtime's `header.s` pads,
//!   which is what closes `FAR`. It is recognized by the source line and not
//!   by the position: if `FAR` filled the bank exactly, there would be no
//!   padding and it would give zero.
//! * **BSS and ZEROPAGE**: their `.cfg` areas minus what they take.
//! * **Texts**: `MESSAGES_BYTES` against `MESSAGES_CAP`, which the converter
//!   emits next to the text block.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use crate::assemble::MEMORY_MAP;
use crate::banks::{self, segment_of, BANK_SIZE, FIRST_BANK};
use crate::dbg::{self, number};

/// What [`show`] prints.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Measure {
    pub banks: usize,
    pub first: usize,
    pub last: usize,
    pub free: usize,
    pub gaps: i64,
    pub largest_gap: i64,
    pub bank0: i64,
    pub bank1: i64,
    pub bss: i64,
    pub zeropage: i64,
    pub texts: Option<i64>,
    pub texts_cap: Option<i64>,
}

/// {area: size} from the `MEMORY` of an `ld65` `.cfg`.
fn areas(cfg: &str) -> HashMap<String, i64> {
    let mut out = HashMap::new();
    for line in cfg.lines() {
        let line = line.trim_start();
        let Some(colon) = line.find(':') else { continue };
        let name = &line[..colon];
        if name.is_empty() || !name.chars().all(|c| c.is_alphanumeric() || c == '_') {
            continue;
        }
        let rest = line[colon + 1..].trim_start();
        let Some(rest) = rest.strip_prefix("start = $") else { continue };
        let Some((start, rest)) = rest.split_once(", size = $") else { continue };
        if start.is_empty() || !start.chars().all(|c| matches!(c, '0'..='9' | 'A'..='F')) {
            continue;
        }
        let size: String = rest
            .chars()
            .take_while(|c| matches!(c, '0'..='9' | 'A'..='F'))
            .collect();
        if let Ok(size) = i64::from_str_radix(&size, 16) {
            out.insert(name.to_string(), size);
        }
    }
    out
}

/// How much the `.align` lines of `header.s` pad, in bytes.
fn far_padding(dbg_text: &str, header: &Path) -> Result<i64, String> {
    let header_text =
        std::fs::read_to_string(header).map_err(|e| format!("{}: {e}", header.display()))?;
    let lines: HashSet<String> = header_text
        .lines()
        .enumerate()
        .filter(|(_, l)| crate::text::code(l).starts_with(".align"))
        .map(|(n, _)| (n + 1).to_string())
        .collect();
    let files: HashSet<String> = dbg::records(dbg_text, "file")
        .into_iter()
        .filter(|f| f.get("name").is_some_and(|n| n.ends_with("header.s")))
        .filter_map(|f| f.get("id").cloned())
        .collect();
    let mut spans = HashSet::new();
    for line in dbg::records(dbg_text, "line") {
        let (Some(file), Some(n), Some(span)) = (line.get("file"), line.get("line"), line.get("span"))
        else {
            continue;
        };
        if files.contains(file) && lines.contains(n) {
            spans.extend(span.split('+').map(str::to_string));
        }
    }
    Ok(dbg::records(dbg_text, "span")
        .into_iter()
        .filter(|s| s.get("id").is_some_and(|id| spans.contains(id)))
        .filter_map(|s| s.get("size").and_then(|n| number(n)))
        .sum())
}

/// The measure of the ROM `sfc`, whose runtime has its `header.s` in
/// `runtime`.
pub fn measure(sfc: &Path, runtime: &Path) -> Result<Measure, String> {
    let dbg_path = {
        let mut s = sfc.as_os_str().to_os_string();
        s.push(".dbg");
        std::path::PathBuf::from(s)
    };
    let dbg_text = std::fs::read_to_string(&dbg_path)
        .map_err(|e| format!("{}: {e}", dbg_path.display()))?;
    let cfg_path = sfc.parent().unwrap_or(Path::new(".")).join(MEMORY_MAP);
    let cfg = std::fs::read_to_string(&cfg_path)
        .map_err(|e| format!("{}: {e}", cfg_path.display()))?;
    let areas = areas(&cfg);
    let used: HashMap<String, i64> = dbg::records(&dbg_text, "seg")
        .into_iter()
        .filter_map(|s| Some((s.get("name")?.clone(), number(s.get("size")?)?)))
        .collect();
    let used_of = |name: &str| used.get(name).copied().unwrap_or(0);
    let data_banks: Vec<usize> = (FIRST_BANK..banks::BANKS)
        .filter(|&b| areas.contains_key(&segment_of(b)))
        .collect();
    let first = *data_banks
        .first()
        .ok_or_else(|| format!("{}: declares no data bank", cfg_path.display()))?;
    let last = data_banks
        .iter()
        .copied()
        .filter(|&b| used_of(&segment_of(b)) != 0)
        .max()
        .unwrap_or(FIRST_BANK - 1);
    let gaps: Vec<i64> = data_banks
        .iter()
        .filter(|&&b| b <= last)
        .map(|&b| BANK_SIZE as i64 - used_of(&segment_of(b)))
        .collect();
    let area = |name: &str| {
        areas
            .get(name)
            .copied()
            .ok_or_else(|| format!("{}: has no {name} area", cfg_path.display()))
    };
    let symbols = dbg::symbols(&dbg_text);
    Ok(Measure {
        banks: data_banks.len(),
        first,
        last,
        free: data_banks.iter().filter(|&&b| b > last).count(),
        gaps: gaps.iter().sum(),
        largest_gap: gaps.iter().copied().max().unwrap_or(0),
        bank0: area("ROM")? - used_of("CODE") - used_of("TABLES"),
        bank1: far_padding(&dbg_text, &runtime.join("header.s"))?,
        bss: area("RAM")? - used_of("BSS"),
        zeropage: area("ZP")? - used_of("ZEROPAGE"),
        texts: symbols.get("MESSAGES_BYTES").copied(),
        texts_cap: symbols.get("MESSAGES_CAP").copied(),
    })
}

/// `n` bytes, with dots between the thousands: `12.345 B`.
fn b(n: i64) -> String {
    let digits = n.unsigned_abs().to_string();
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push('.');
        }
        out.push(c);
    }
    format!("{}{out} B", if n < 0 { "-" } else { "" })
}

/// The report for one ROM, headed by `title`.
pub fn show(title: &str, m: &Measure) -> String {
    let mut out = format!("{title}\n");
    out += &format!(
        "  data banks       {} of {} used, ${:02X}-${:02X}; {} free after them\n",
        m.last as i64 - m.first as i64 + 1,
        m.banks,
        m.first,
        m.last,
        m.free
    );
    out += &format!(
        "  gaps             {} in the used ones, the largest {}\n",
        b(m.gaps),
        b(m.largest_gap)
    );
    out += &format!("  bank 0           {}\n", b(m.bank0));
    out += &format!("  bank 1           {}\n", b(m.bank1));
    out += &format!("  BSS              {}\n", b(m.bss));
    out += &format!("  ZEROPAGE         {}\n", b(m.zeropage));
    match (m.texts, m.texts_cap) {
        (Some(texts), Some(cap)) => {
            out += &format!(
                "  texts            {} of {}; {} left\n",
                b(texts),
                b(cap),
                b(cap - texts)
            );
        }
        _ => out += "  texts            the ROM does not say how long they are\n",
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thousands_go_with_dots() {
        assert_eq!(b(0), "0 B");
        assert_eq!(b(999), "999 B");
        assert_eq!(b(1000), "1.000 B");
        assert_eq!(b(1234567), "1.234.567 B");
        assert_eq!(b(-1234), "-1.234 B");
    }

    #[test]
    fn the_areas_come_from_the_memory_map() {
        let areas = areas(&banks::cfg());
        assert_eq!(areas["ROM"], 0x7FC0);
        assert_eq!(areas["RAM"], 0x1F00 - banks::STACK as i64);
        assert_eq!(areas["BANK02"], 0x8000);
        assert!(!areas.contains_key("BANK7E"));
    }
}
