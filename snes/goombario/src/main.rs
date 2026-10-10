//! Goombario from the command line.
//!
//! It knows nothing of where a project keeps its files: the ROM, its debug
//! file, where the sources are and the exceptions all come in as arguments.

use std::path::PathBuf;
use std::process::ExitCode;

use goombario::Check;

const FOUND: u8 = 1;
const MISUSE: u8 = 2;

const USAGE: &str = "\
usage: goombario [options] ROM

Checks the 65816 code of a ROM built with ca65 and ld65, reading where each
instruction came from in the debug file ld65 writes with --dbgfile.

  --dbg FILE      the debug file (default: ROM.dbg)
  --root DIR      the directory the debug file's paths are relative to,
                  which is where ca65 ran (default: the current one)
  --only PREFIX   report only what is in source files whose path, as the
                  debug file has it, starts with PREFIX; can be repeated
  --allow FILE    the exceptions: see the README for the format
  --checks LIST   which checks, comma-separated, of pull-branch, call-return,
                  stack and width (default: all four)
  --stats         how much each check looked at, on stderr
  --unfollowed    where the walks had to stop, on stderr

Exit codes: 0 nothing found; 1 findings, or exceptions that are wrong or match
nothing; 2 the call itself is wrong.";

struct Options {
    rom: PathBuf,
    dbg: Option<PathBuf>,
    root: PathBuf,
    only: Vec<String>,
    allow: Option<PathBuf>,
    checks: Vec<Check>,
    stats: bool,
    unfollowed: bool,
}

fn options(args: Vec<String>) -> Result<Options, String> {
    let mut o = Options {
        rom: PathBuf::new(),
        dbg: None,
        root: PathBuf::from("."),
        only: Vec::new(),
        allow: None,
        checks: vec![Check::PullBranch, Check::CallReturn, Check::Stack, Check::Width],
        stats: false,
        unfollowed: false,
    };
    let mut rom = None;
    let mut it = args.into_iter();
    while let Some(a) = it.next() {
        let mut value = |name: &str| it.next().ok_or_else(|| format!("{} needs a value", name));
        match a.as_str() {
            "--dbg" => o.dbg = Some(value("--dbg")?.into()),
            "--root" => o.root = value("--root")?.into(),
            "--only" => o.only.push(value("--only")?),
            "--allow" => o.allow = Some(value("--allow")?.into()),
            "--checks" => {
                o.checks = value("--checks")?
                    .split(',')
                    .map(|c| Check::from_name(c.trim()).ok_or_else(|| format!("{:?} is not a check", c)))
                    .collect::<Result<_, _>>()?
            }
            "--stats" => o.stats = true,
            "--unfollowed" => o.unfollowed = true,
            "-h" | "--help" => return Err(String::new()),
            s if s.starts_with("--") => return Err(format!("unknown option {}", s)),
            _ if rom.is_none() => rom = Some(PathBuf::from(a)),
            _ => return Err("only one ROM".into()),
        }
    }
    o.rom = rom.ok_or("which ROM?")?;
    Ok(o)
}

fn main() -> ExitCode {
    let o = match options(std::env::args().skip(1).collect()) {
        Ok(o) => o,
        Err(e) => {
            if !e.is_empty() {
                eprintln!("goombario: {}", e);
            }
            eprintln!("{}", USAGE);
            return ExitCode::from(MISUSE);
        }
    };
    let dbg = o.dbg.clone().unwrap_or_else(|| {
        let mut p = o.rom.clone().into_os_string();
        p.push(".dbg");
        p.into()
    });
    let exceptions = match &o.allow {
        Some(path) => match std::fs::read_to_string(path)
            .map_err(|e| e.to_string())
            .and_then(|t| goombario::allow::parse(&t))
        {
            Ok(list) => list,
            Err(e) => {
                eprintln!("goombario: {}: {}", path.display(), e);
                return ExitCode::from(MISUSE);
            }
        },
        None => Vec::new(),
    };
    let program = match goombario::load(&o.rom, &dbg, &o.root) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("goombario: {}", e);
            return ExitCode::from(MISUSE);
        }
    };
    let mut wrong = 0;
    // What the checks stand on: if these are not empty, a finding can be
    // missing or made up, so they count as findings.
    let wanted = |file: &str| o.only.is_empty() || o.only.iter().any(|p| file.starts_with(p.as_str()));
    for m in program.missing_sources() {
        println!("{}: the source cannot be read, so the widths after it are unknown", m);
        wrong += 1;
    }
    for (file, u) in &program.undecoded {
        if wanted(file) {
            println!("{}", u);
            wrong += 1;
        }
    }
    let (reports, stats) = goombario::lint(&program, &o.root);
    let reports = reports.into_iter().filter(|r| o.checks.contains(&r.check) && wanted(&r.file)).collect();
    let (left, unused) = goombario::apply_exceptions(reports, &exceptions);
    for r in &left {
        println!(
            "{}:{}: {}: in `{}`, `{}`: {}.\n    allow: {}",
            r.file,
            r.line,
            r.check.name(),
            r.routine,
            r.text,
            r.message,
            r.allow_line()
        );
        wrong += 1;
    }
    if let Some(path) = &o.allow {
        for e in &unused {
            if o.checks.contains(&e.check) {
                println!(
                    "{}:{}: this exception matches nothing: `{} {}{}`",
                    path.display(),
                    e.line,
                    e.check.name(),
                    e.routine,
                    e.text.as_deref().map(|t| format!(" {}", t)).unwrap_or_default()
                );
                wrong += 1;
            }
        }
    }
    if o.stats {
        let w = &stats.width;
        eprintln!(
            "instructions {}, pulls {}, entries {}, calls walked {}, returns reached {}, \
             places a walk stopped {}",
            stats.instructions,
            stats.pulls,
            stats.entries,
            stats.calls,
            stats.returns_checked,
            stats.unfollowed.len()
        );
        eprintln!(
            "widths: immediates {} decided ({} wrong), {} not; other width-dependent \
             instructions {} decided ({} wrong), {} not; calls {} decided ({} wrong), {} not",
            w.immediates_known,
            w.immediates_wrong,
            w.immediates_unknown,
            w.others_known,
            w.others_wrong,
            w.others_unknown,
            w.calls_known,
            w.calls_wrong,
            w.calls_unknown
        );
        let disagree = program.width_disagreements();
        eprintln!("immediates whose size the source's widths do not explain: {}", disagree.len());
        for d in disagree.iter().take(20) {
            eprintln!("    {}", d);
        }
    }
    if o.unfollowed {
        for (addr, why) in &stats.unfollowed {
            let place = program
                .insns
                .get(addr)
                .and_then(|i| program.place(i))
                .map(|(f, l)| format!("{}:{}", f, l))
                .unwrap_or_else(|| format!("${:06X}", addr));
            eprintln!("{}: in `{}`: {}", place, program.routine(*addr), why);
        }
    }
    if wrong > 0 {
        ExitCode::from(FOUND)
    } else {
        ExitCode::SUCCESS
    }
}
