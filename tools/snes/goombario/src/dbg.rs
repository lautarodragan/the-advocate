//! The debug file `ld65 --dbgfile` writes: one record per line, a type and
//! then `key=value` pairs separated by commas. Only what the checks use is
//! kept.

use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Segment {
    pub name: String,
    /// The address the segment runs at.
    pub start: u32,
    pub size: u32,
    /// Where it is in the output file, if it goes to one: RAM segments do
    /// not.
    pub ooffs: Option<usize>,
}

#[derive(Debug, Clone)]
pub struct Span {
    pub seg: usize,
    /// From the start of the segment.
    pub start: u32,
    pub size: u32,
    /// A span with a type is data —`.byte`, `.addr`—: it is how `ca65` tells
    /// it apart from an instruction.
    pub data: bool,
}

#[derive(Debug, Clone)]
pub struct Line {
    pub file: usize,
    pub line: u32,
    /// A line of a macro's body, as expanded: `type=2`.
    pub in_macro: bool,
    pub spans: Vec<usize>,
}

#[derive(Debug, Clone)]
pub struct Sym {
    pub name: String,
    pub value: Option<u32>,
    /// A label, as opposed to a symbol given a value with `=`.
    pub label: bool,
    /// The scope it was defined in: 0 is the file's, outside any `.proc`.
    pub scope: usize,
}

#[derive(Debug, Default)]
pub struct DebugInfo {
    pub files: HashMap<usize, String>,
    pub segments: HashMap<usize, Segment>,
    pub spans: HashMap<usize, Span>,
    pub lines: HashMap<usize, Line>,
    pub syms: HashMap<usize, Sym>,
    /// The main file of each module: where `.include` starts.
    pub main_files: Vec<usize>,
}

fn fields(rest: &str) -> HashMap<&str, &str> {
    let mut out = HashMap::new();
    let bytes = rest.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let key_start = i;
        while i < bytes.len() && bytes[i] != b'=' {
            i += 1;
        }
        let key = &rest[key_start..i];
        i += 1;
        let value;
        if i < bytes.len() && bytes[i] == b'"' {
            let start = i + 1;
            i = start;
            while i < bytes.len() && bytes[i] != b'"' {
                i += 1;
            }
            value = &rest[start..i.min(rest.len())];
            i += 1;
        } else {
            let start = i.min(rest.len());
            while i < bytes.len() && bytes[i] != b',' {
                i += 1;
            }
            value = &rest[start..i.min(rest.len())];
        }
        out.insert(key, value);
        // The comma.
        i += 1;
    }
    out
}

pub fn number(s: &str) -> Result<u32, String> {
    let r = if let Some(hex) = s.strip_prefix("0x") {
        u32::from_str_radix(hex, 16)
    } else {
        s.parse()
    };
    r.map_err(|_| format!("not a number: {:?}", s))
}

fn get<'a>(f: &HashMap<&str, &'a str>, key: &str, kind: &str) -> Result<&'a str, String> {
    f.get(key).copied().ok_or_else(|| format!("a {} record without {}", kind, key))
}

fn id(f: &HashMap<&str, &str>, kind: &str) -> Result<usize, String> {
    Ok(number(get(f, "id", kind)?)? as usize)
}

fn ids(s: &str) -> Result<Vec<usize>, String> {
    s.split('+').map(|x| number(x).map(|n| n as usize)).collect()
}

pub fn parse(text: &str) -> Result<DebugInfo, String> {
    let mut info = DebugInfo::default();
    for (n, record) in text.lines().enumerate() {
        let (kind, rest) = record.split_once('\t').unwrap_or((record, ""));
        let f = fields(rest);
        let at = |e: String| format!("line {} of the debug file: {}", n + 1, e);
        match kind {
            "file" => {
                info.files.insert(id(&f, kind).map_err(at)?, get(&f, "name", kind).map_err(at)?.to_string());
            }
            "mod" => {
                info.main_files.push(number(get(&f, "file", kind).map_err(at)?).map_err(at)? as usize);
            }
            "seg" => {
                let seg = Segment {
                    name: get(&f, "name", kind).map_err(at)?.to_string(),
                    start: number(get(&f, "start", kind).map_err(at)?).map_err(at)?,
                    size: number(get(&f, "size", kind).map_err(at)?).map_err(at)?,
                    ooffs: match f.get("ooffs") {
                        Some(o) => Some(number(o).map_err(at)? as usize),
                        None => None,
                    },
                };
                info.segments.insert(id(&f, kind).map_err(at)?, seg);
            }
            "span" => {
                let span = Span {
                    seg: number(get(&f, "seg", kind).map_err(at)?).map_err(at)? as usize,
                    start: number(get(&f, "start", kind).map_err(at)?).map_err(at)?,
                    size: number(get(&f, "size", kind).map_err(at)?).map_err(at)?,
                    data: f.contains_key("type"),
                };
                info.spans.insert(id(&f, kind).map_err(at)?, span);
            }
            "line" => {
                let line = Line {
                    file: number(get(&f, "file", kind).map_err(at)?).map_err(at)? as usize,
                    line: number(get(&f, "line", kind).map_err(at)?).map_err(at)?,
                    in_macro: f.get("type") == Some(&"2"),
                    spans: match f.get("span") {
                        Some(s) => ids(s).map_err(at)?,
                        None => Vec::new(),
                    },
                };
                info.lines.insert(id(&f, kind).map_err(at)?, line);
            }
            "sym" => {
                let sym = Sym {
                    name: get(&f, "name", kind).map_err(at)?.to_string(),
                    value: match f.get("val") {
                        Some(v) => Some(number(v).map_err(at)?),
                        None => None,
                    },
                    label: f.get("type") == Some(&"lab"),
                    scope: match f.get("scope") {
                        Some(s) => number(s).map_err(at)? as usize,
                        None => 0,
                    },
                };
                info.syms.insert(id(&f, kind).map_err(at)?, sym);
            }
            _ => {}
        }
    }
    if info.main_files.is_empty() && info.files.contains_key(&0) {
        info.main_files.push(0);
    }
    Ok(info)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_quoted_and_bare_values_and_the_last_field() {
        let text = "file\tid=0,name=\"a,b.s\",size=3,mtime=0x1,mod=0\n\
                    sym\tid=0,name=\"x\",addrsize=absolute,scope=0,def=1,val=0x8000,seg=0,type=lab\n";
        let info = parse(text).unwrap();
        assert_eq!(info.files[&0], "a,b.s");
        let sym = &info.syms[&0];
        assert!(sym.label);
        assert_eq!(sym.value, Some(0x8000));
    }
}
