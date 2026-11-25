//! How much space a built ROM has left, from what the build left next to it
//! —`ld65`'s debug file and the memory map—: nothing is relinked.
//!
//! * **Data banks**: the `BANKnn` of [`banks::slots`] that the `.cfg`
//!   declares. A "used" one has something, and a free one nothing. **The
//!   free whole banks are the number that matters**, 64 KB each, and not a
//!   percentage: the packing leaves gaps, and not all of the 8 MB is data.
//!   They are counted apart from the free halves, which only take pieces of
//!   up to 32 KB, and the fast ones —the first 4 MB— apart from the rest.
//! * **Gaps**: what is left over inside the used ones.
//! * **Bank 0**: the `.cfg`'s `ROM` area minus `CODE` and `TABLES`, which
//!   share it.
//! * **Bank 1**: what the `.align $8000` in the runtime's `header.s` pads,
//!   which is what closes `FAR`. It is recognized by the source line and not
//!   by the position: if `FAR` filled the bank exactly, there would be no
//!   padding and it would give zero.
//! * **Bank `$C0`**: the third code bank, [`banks::FAR2`]: its `.cfg` area
//!   minus what `FAR2` takes. It has no `.align` to close it, nor needs one:
//!   nothing comes after it in its area.
//! * **Bank `$C1`**: the fourth, [`banks::FAR3`], the same way.
//! * **Bank `$FF`**: the fifth, [`banks::FAR4`], the same way, in its own
//!   area, [`banks::FAR4_AREA`].
//! * **BSS and ZEROPAGE**: their `.cfg` areas minus what they take; and
//!   the same for **far RAM**, the `FARRAM` area minus `FARBSS` and
//!   `SWITCHES`, the two segments it holds: see [`banks::FAR_POOL_START`].
//! * **Texts**: `MESSAGES_BYTES` against `MESSAGES_CAP`, which the converter
//!   emits next to the text block.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use crate::assemble::MEMORY_MAP;
use crate::banks::{self, segment_of, BANK_SIZE};
use crate::dbg::{self, number};

/// What a ROM has left: what `space.json` keeps beside it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Measure {
    pub banks: usize,
    pub used: usize,
    /// How many of the used ones are in the slow 4 MB.
    pub slow: usize,
    /// Free whole banks, and how many of those are fast.
    pub free: usize,
    pub free_fast: usize,
    /// Free halves.
    pub free_halves: usize,
    pub gaps: i64,
    pub largest_gap: i64,
    pub bank0: i64,
    pub bank1: i64,
    pub bank_far2: i64,
    pub bank_far3: i64,
    pub bank_far4: i64,
    pub bss: i64,
    pub zeropage: i64,
    pub far: i64,
    pub texts: Option<i64>,
    pub texts_cap: Option<i64>,
}

/// {area: size} from the `MEMORY` of an `ld65` `.cfg`.
fn areas(cfg: &str) -> HashMap<String, i64> {
    let mut out = HashMap::new();
    for line in cfg.lines() {
        let line = line.trim_start();
        let Some(colon) = line.find(':') else {
            continue;
        };
        let name = &line[..colon];
        if name.is_empty() || !name.chars().all(|c| c.is_alphanumeric() || c == '_') {
            continue;
        }
        let rest = line[colon + 1..].trim_start();
        let Some(rest) = rest.strip_prefix("start = $") else {
            continue;
        };
        let Some((start, rest)) = rest.split_once(", size = $") else {
            continue;
        };
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
        let (Some(file), Some(n), Some(span)) =
            (line.get("file"), line.get("line"), line.get("span"))
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

impl Measure {
    /// The numbers, as JSON, with the ROM they measure: what `space --json`
    /// prints for each cartridge and what the build leaves beside the ROM,
    /// in `space.json`.
    pub fn json(&self, rom: &Path) -> serde_json::Value {
        serde_json::json!({
            "rom": rom,
            "banks": self.banks,
            "used": self.used,
            "slow": self.slow,
            "free": self.free,
            "free_fast": self.free_fast,
            "free_halves": self.free_halves,
            "gaps": self.gaps,
            "largest_gap": self.largest_gap,
            "bank0": self.bank0,
            "bank1": self.bank1,
            "bank_far2": self.bank_far2,
            "bank_far3": self.bank_far3,
            "bank_far4": self.bank_far4,
            "bss": self.bss,
            "far": self.far,
            "zeropage": self.zeropage,
            "texts": self.texts,
            "texts_cap": self.texts_cap,
        })
    }
}

/// The measure of the ROM `sfc`, whose runtime has its `header.s` in
/// `runtime`.
pub fn measure(sfc: &Path, runtime: &Path) -> Result<Measure, String> {
    let dbg_path = {
        let mut s = sfc.as_os_str().to_os_string();
        s.push(".dbg");
        std::path::PathBuf::from(s)
    };
    let dbg_text =
        std::fs::read_to_string(&dbg_path).map_err(|e| format!("{}: {e}", dbg_path.display()))?;
    let cfg_path = sfc.parent().unwrap_or(Path::new(".")).join(MEMORY_MAP);
    let cfg =
        std::fs::read_to_string(&cfg_path).map_err(|e| format!("{}: {e}", cfg_path.display()))?;
    let areas = areas(&cfg);
    let used: HashMap<String, i64> = dbg::records(&dbg_text, "seg")
        .into_iter()
        .filter_map(|s| Some((s.get("name")?.clone(), number(s.get("size")?)?)))
        .collect();
    let used_of = |name: &str| used.get(name).copied().unwrap_or(0);
    let data: Vec<banks::Slot> = banks::slots()
        .into_iter()
        .filter(|s| areas.contains_key(&segment_of(s.bank)))
        .collect();
    if data.is_empty() {
        return Err(format!("{}: declares no data bank", cfg_path.display()));
    }
    let used_slot = |s: &banks::Slot| used_of(&segment_of(s.bank)) != 0;
    let free: Vec<&banks::Slot> = data.iter().filter(|s| !used_slot(s)).collect();
    let gaps: Vec<i64> = data
        .iter()
        .filter(|s| used_slot(s))
        .map(|s| s.size as i64 - used_of(&segment_of(s.bank)))
        .collect();
    let area = |name: &str| {
        areas
            .get(name)
            .copied()
            .ok_or_else(|| format!("{}: has no {name} area", cfg_path.display()))
    };
    let symbols = dbg::symbols(&dbg_text);
    Ok(Measure {
        banks: data.len(),
        used: data.len() - free.len(),
        slow: data.iter().filter(|s| used_slot(s) && !s.fast()).count(),
        free: free.iter().filter(|s| s.size == BANK_SIZE).count(),
        free_fast: free
            .iter()
            .filter(|s| s.size == BANK_SIZE && s.fast())
            .count(),
        free_halves: free.iter().filter(|s| s.size != BANK_SIZE).count(),
        gaps: gaps.iter().sum(),
        largest_gap: gaps.iter().copied().max().unwrap_or(0),
        bank0: area("ROM")? - used_of("CODE") - used_of("TABLES"),
        bank1: far_padding(&dbg_text, &runtime.join("header.s"))?,
        bank_far2: area(&segment_of(banks::FAR2.bank))? - used_of("FAR2"),
        bank_far3: area(&segment_of(banks::FAR3.bank))? - used_of("FAR3"),
        bank_far4: area(banks::FAR4_AREA)? - used_of("FAR4"),
        bss: area("RAM")? - used_of("BSS"),
        zeropage: area("ZP")? - used_of("ZEROPAGE"),
        far: area("FARRAM")? - used_of("FARBSS") - used_of("SWITCHES"),
        texts: symbols.get("MESSAGES_BYTES").copied(),
        texts_cap: symbols.get("MESSAGES_CAP").copied(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_areas_come_from_the_memory_map() {
        let areas = areas(&banks::cfg());
        assert_eq!(areas["ROM"], 0x7FC0);
        assert_eq!(areas["RAM"], 0x1F00 - banks::STACK as i64);
        assert_eq!(areas["FARRAM"], banks::FAR_POOL_SIZE as i64);
        assert_eq!(areas["BANKC2"], 0x10000);
        assert_eq!(areas["BANKC0"], 0x8000, "the third code bank");
        assert_eq!(areas["BANKC1"], 0x8000, "the fourth code bank");
        assert_eq!(areas[banks::FAR4_AREA], 0x8000, "the fifth code bank");
        assert_eq!(areas["BANKFF"], 0x8000, "the fifth code bank's data half");
        assert_eq!(areas["BANK70"], 0x8000);
        assert!(!areas.contains_key("BANK7E"));
    }
}
