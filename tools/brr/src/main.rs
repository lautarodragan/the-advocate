//! BRR from the command line: PCM in, SPC700 blocks out.
//!
//! BRR itself carries almost nothing besides the audio — no sample rate, no
//! loop point — so whatever plays a sample has to be told both, and they are
//! as much a part of a sample as its bytes. Every command that produces or
//! reads a sample therefore prints them, and `--json` prints them in a shape a
//! build script can read without parsing prose.
//!
//! Where files go is the caller's business: nothing here has a default path or
//! a directory it knows about.

mod codec;
mod fail;
mod sf2;
mod wav;

use clap::{Args as ClapArgs, Parser, Subcommand};
use fail::{Bad, Result};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// What the two exit codes mean, and why they are not the same.
///
/// "The font has no program 47" and "you passed me a JPEG" are different kinds
/// of answer: the first is this tool working correctly and saying no, the
/// second is the call being wrong. A script wants to tell those apart without
/// reading the message.
const NO: u8 = 1;
const MISUSE: u8 = 2;

/// The rate to assume when nobody says: what the DSP plays a sample at with
/// its pitch register set to 1.0, so a decode with no `--rate` at least sounds
/// like the right thing.
const DEFAULT_RATE: u32 = 32000;

#[derive(Parser)]
#[command(
    name = "brr",
    about = "Encode PCM into SPC700 BRR blocks, and pull samples out of SoundFonts",
    after_help = "Exit codes: 1 the answer is no (nothing matched, quality bar missed), \
                  2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// PCM (.wav, or raw 16-bit) into BRR blocks
    Encode(Encode),
    /// BRR blocks back into a .wav, to listen to what the codec did
    Decode(Decode),
    /// What a .brr file contains: blocks, filters, ranges, flags
    Info(Info),
    /// Read a SoundFont: list what is in it, or take one sample out
    Sf2(Sf2),
}

#[derive(ClapArgs)]
#[command(after_help = "Input is a .wav if it starts with RIFF, and raw signed \
                        16-bit little-endian mono otherwise.\n\
                        A loop point must fall on a block boundary: the DSP comes \
                        back to the start of a 9-byte block, so every 16 samples.")]
struct Encode {
    /// PCM to encode: a mono .wav, or headerless signed 16-bit
    input: PathBuf,

    /// Where to write the BRR blocks
    #[arg(short, long, value_name = "PATH")]
    output: PathBuf,

    /// Loop back to this block (16 samples each)
    #[arg(long, value_name = "N", conflicts_with = "loop_sample")]
    loop_block: Option<usize>,

    /// Loop back to this sample; must be a multiple of 16
    #[arg(long, value_name = "N")]
    loop_sample: Option<usize>,

    /// Sample rate to report, and to assume for headerless input
    #[arg(long, value_name = "HZ")]
    rate: Option<u32>,

    /// Exit 1 if the worst sample is off by more than this much of the peak
    #[arg(long, value_name = "PERCENT")]
    max_error: Option<f64>,

    /// Print the sample's contract as JSON instead of prose
    #[arg(long)]
    json: bool,
}

#[derive(ClapArgs)]
struct Decode {
    /// The BRR blocks
    input: PathBuf,

    /// Where to write the .wav
    #[arg(short, long, value_name = "PATH")]
    output: PathBuf,

    /// Rate to stamp on the .wav
    #[arg(long, value_name = "HZ", default_value_t = DEFAULT_RATE)]
    rate: u32,

    /// Print as JSON instead of prose
    #[arg(long)]
    json: bool,
}

#[derive(ClapArgs)]
struct Info {
    /// The BRR blocks
    input: PathBuf,

    /// Print as JSON instead of prose
    #[arg(long)]
    json: bool,
}

#[derive(ClapArgs)]
#[command(after_help = "A selector for --extract is one of:\n  \
    program:12        General MIDI program 12, at the reference key\n  \
    program:12@72     the same, choosing the zone that covers key 72\n  \
    drum:36           key 36 of the standard drum kit (bank 128)\n  \
    sample:Piano A4   an shdr entry by its exact name\n\n\
    Exit code 1 means the font has nothing matching the selector.")]
struct Sf2 {
    /// The .sf2 to read
    file: PathBuf,

    /// List the presets the font declares
    #[arg(long, conflicts_with_all = ["extract", "list_samples"])]
    list: bool,

    /// List the raw samples: rate, length and loop
    #[arg(long, conflicts_with = "extract")]
    list_samples: bool,

    /// Take one sample out; see the selectors below
    #[arg(long, value_name = "SELECTOR")]
    extract: Option<String>,

    /// Where to write the extracted .wav; omit to only print the contract
    #[arg(short, long, value_name = "PATH")]
    output: Option<PathBuf>,

    /// Print as JSON instead of prose
    #[arg(long)]
    json: bool,
}

// --- output -----------------------------------------------------------------

/// `println!` that does not panic when the reader goes away.
///
/// `brr sf2 huge.sf2 --list | head` closes the pipe halfway through, and a
/// listing command that dies with a Rust backtrace on the most ordinary thing
/// anyone does with a listing is not usable.
macro_rules! say {
    ($($arg:tt)*) => {{
        use std::io::Write;
        let mut out = std::io::stdout().lock();
        if writeln!(out, $($arg)*).is_err() {
            std::process::exit(0);
        }
    }};
}

/// Hand-rolled JSON, because one object of scalars does not justify a
/// dependency, and the shape has to stay readable in a diff anyway.
struct Json(Vec<String>);

impl Json {
    fn new() -> Json {
        Json(Vec::new())
    }

    fn num<T: std::fmt::Display>(mut self, key: &str, value: T) -> Json {
        self.0.push(format!("\"{key}\": {value}"));
        self
    }

    fn text(mut self, key: &str, value: &str) -> Json {
        let escaped: String = value
            .chars()
            .flat_map(|c| match c {
                '"' => vec!['\\', '"'],
                '\\' => vec!['\\', '\\'],
                c if (c as u32) < 0x20 => format!("\\u{:04x}", c as u32).chars().collect(),
                c => vec![c],
            })
            .collect();
        self.0.push(format!("\"{key}\": \"{escaped}\""));
        self
    }

    fn maybe<T: std::fmt::Display>(mut self, key: &str, value: Option<T>) -> Json {
        match value {
            Some(v) => self.0.push(format!("\"{key}\": {v}")),
            None => self.0.push(format!("\"{key}\": null")),
        }
        self
    }

    fn flag(self, key: &str, value: bool) -> Json {
        self.num(key, value)
    }

    fn print(self) {
        say!("{{{}}}", self.0.join(", "));
    }
}

// --- encode -----------------------------------------------------------------

fn read_audio(path: &Path, rate: Option<u32>) -> Result<wav::Audio> {
    let bytes =
        std::fs::read(path).map_err(|e| Bad(format!("{}: {e}", path.display())))?;
    if wav::looks_like_wav(&bytes) {
        let mut audio = wav::read(&bytes, path)?;
        if let Some(rate) = rate {
            audio.rate = rate;
        }
        Ok(audio)
    } else {
        wav::read_raw(&bytes, rate.unwrap_or(DEFAULT_RATE), path)
    }
}

fn write_out(path: &Path, bytes: &[u8]) -> Result<()> {
    if let Some(dir) = path.parent() {
        if !dir.as_os_str().is_empty() {
            std::fs::create_dir_all(dir)
                .map_err(|e| Bad(format!("{}: {e}", dir.display())))?;
        }
    }
    std::fs::write(path, bytes).map_err(|e| Bad(format!("{}: {e}", path.display())))
}

fn encode(args: &Encode) -> Result<u8> {
    let audio = read_audio(&args.input, args.rate)?;
    if audio.samples.is_empty() {
        return Err(Bad(format!("{}: no samples in it", args.input.display())));
    }

    let blocks = audio.samples.len().div_ceil(codec::BLOCK_SAMPLES);
    let loop_block = match (args.loop_block, args.loop_sample) {
        (Some(b), _) => Some(b),
        (_, Some(s)) => {
            if s % codec::BLOCK_SAMPLES != 0 {
                let below = s - s % codec::BLOCK_SAMPLES;
                return Err(Bad(format!(
                    "--loop-sample {s} is not a multiple of {}: the nearest points \
                     the DSP can come back to are {below} and {}",
                    codec::BLOCK_SAMPLES,
                    below + codec::BLOCK_SAMPLES
                )));
            }
            Some(s / codec::BLOCK_SAMPLES)
        }
        _ => None,
    };
    if let Some(block) = loop_block {
        if block >= blocks {
            return Err(Bad(format!(
                "loop block {block} is past the end: {} samples make {blocks} blocks",
                audio.samples.len()
            )));
        }
    }

    let data = codec::encode(&audio.samples, loop_block);
    let worst = codec::error(&audio.samples, &data);
    write_out(&args.output, &data)?;

    let over = args.max_error.is_some_and(|limit| worst > limit);

    if args.json {
        Json::new()
            .text("output", &args.output.display().to_string())
            .num("samples", audio.samples.len())
            .num("rate", audio.rate)
            .num("blocks", blocks)
            .num("bytes", data.len())
            .maybe("loop_block", loop_block)
            .maybe("loop_sample", loop_block.map(|b| b * codec::BLOCK_SAMPLES))
            .num("worst_error_percent", format!("{worst:.3}"))
            .flag("within_limit", !over)
            .print();
    } else {
        say!("wrote {}", args.output.display());
        if let Some(note) = &audio.note {
            say!("  input: {note}");
        }
        say!(
            "  {} samples at {} Hz -> {} blocks, {} bytes ({:.2}x)",
            audio.samples.len(),
            audio.rate,
            blocks,
            data.len(),
            data.len() as f64 / (audio.samples.len() * 2) as f64
        );
        match loop_block {
            Some(b) => say!("  loops back to block {b} (sample {})", b * codec::BLOCK_SAMPLES),
            None => say!("  does not loop"),
        }
        say!("  worst sample off by {worst:.2}% of the peak");
    }

    if over {
        eprintln!(
            "worst error {worst:.2}% is over the {:.2}% asked for",
            args.max_error.unwrap()
        );
        return Ok(NO);
    }
    Ok(0)
}

// --- decode and info --------------------------------------------------------

fn read_blocks(path: &Path) -> Result<Vec<u8>> {
    let data =
        std::fs::read(path).map_err(|e| Bad(format!("{}: {e}", path.display())))?;
    if data.is_empty() || data.len() % codec::BLOCK_BYTES != 0 {
        return Err(Bad(format!(
            "{}: {} bytes is not a whole number of {}-byte BRR blocks",
            path.display(),
            data.len(),
            codec::BLOCK_BYTES
        )));
    }
    Ok(data)
}

fn decode(args: &Decode) -> Result<u8> {
    let data = read_blocks(&args.input)?;
    let samples = codec::decode(&data);
    write_out(&args.output, &wav::write(&samples, args.rate))?;

    if args.json {
        Json::new()
            .text("output", &args.output.display().to_string())
            .num("samples", samples.len())
            .num("rate", args.rate)
            .num("blocks", data.len() / codec::BLOCK_BYTES)
            .print();
    } else {
        say!("wrote {}", args.output.display());
        say!("  {} samples at {} Hz", samples.len(), args.rate);
    }
    Ok(0)
}

fn info(args: &Info) -> Result<u8> {
    let data = read_blocks(&args.input)?;
    let headers: Vec<codec::Header> =
        data.chunks_exact(codec::BLOCK_BYTES).map(|b| codec::Header::of(b[0])).collect();

    let mut filters = [0usize; 4];
    let mut shifts = [0usize; 16];
    for h in &headers {
        filters[h.filter as usize] += 1;
        shifts[h.shift as usize] += 1;
    }
    let last = headers.last().expect("read_blocks refuses an empty file");
    // A loop flag anywhere but the last block is ignored by the DSP, and is
    // the usual sign of a file assembled by hand.
    let stray = headers[..headers.len() - 1].iter().filter(|h| h.loops).count();
    let unusable = shifts[(codec::MAX_SHIFT as usize + 1)..].iter().sum::<usize>();

    if args.json {
        Json::new()
            .num("blocks", headers.len())
            .num("samples", headers.len() * codec::BLOCK_SAMPLES)
            .flag("ends", last.end)
            .flag("loops", last.loops)
            .num("stray_loop_flags", stray)
            .num("unusable_ranges", unusable)
            .text("filters", &format!("{filters:?}"))
            .print();
    } else {
        say!("{}", args.input.display());
        say!(
            "  {} blocks, {} samples",
            headers.len(),
            headers.len() * codec::BLOCK_SAMPLES
        );
        say!(
            "  last block: {}{}",
            if last.end { "end" } else { "no end flag" },
            if last.loops { ", loops" } else { ", does not loop" }
        );
        for (filter, count) in filters.iter().enumerate() {
            if *count > 0 {
                say!("  filter {filter}: {count} blocks");
            }
        }
        let used: Vec<String> = shifts
            .iter()
            .enumerate()
            .filter(|(_, c)| **c > 0)
            .map(|(s, c)| format!("{s}x{c}"))
            .collect();
        say!("  ranges: {}", used.join(" "));
        if stray > 0 {
            say!("  {stray} block(s) before the last carry a loop flag, which the DSP ignores");
        }
        if unusable > 0 {
            say!("  {unusable} block(s) ask for a range above {}, which the DSP does not decode",
                     codec::MAX_SHIFT);
        }
    }
    Ok(0)
}

// --- soundfont --------------------------------------------------------------

/// What `--extract` was asked for.
#[derive(Debug)]
enum Selector {
    Program { program: u16, bank: u16, key: u8 },
    Named(String),
}

/// The key a melodic program's zone is chosen with when nobody says: middle C.
const REFERENCE_KEY: u8 = 60;

fn parse_selector(text: &str) -> Result<Selector> {
    let bad = || {
        Bad(format!(
            "{text:?} is not a selector: expected program:N, program:N@KEY, \
             drum:N or sample:NAME"
        ))
    };
    let (kind, rest) = text.split_once(':').ok_or_else(bad)?;
    match kind {
        "program" => {
            let (number, key) = match rest.split_once('@') {
                Some((n, k)) => (n, Some(k)),
                None => (rest, None),
            };
            let program: u16 = number.parse().map_err(|_| {
                Bad(format!("program {number:?} is not a number 0-127"))
            })?;
            let key: u8 = match key {
                None => REFERENCE_KEY,
                Some(k) => k
                    .parse()
                    .map_err(|_| Bad(format!("key {k:?} is not a number 0-127")))?,
            };
            Ok(Selector::Program { program, bank: 0, key })
        }
        "drum" => {
            let key: u8 = rest
                .parse()
                .map_err(|_| Bad(format!("drum key {rest:?} is not a number 0-127")))?;
            Ok(Selector::Program { program: 0, bank: sf2::DRUM_BANK, key })
        }
        "sample" => Ok(Selector::Named(rest.to_string())),
        _ => Err(bad()),
    }
}

fn soundfont(args: &Sf2) -> Result<u8> {
    let mut font = sf2::SoundFont::open(&args.file)?;

    if args.list {
        if args.json {
            for i in 0..font.preset_count() {
                let (p, name) = font.preset(i);
                Json::new()
                    .num("bank", p.bank)
                    .num("program", p.program)
                    .text("name", name)
                    .print();
            }
        } else {
            say!("{}: {} presets, {} samples",
                     args.file.display(), font.preset_count(), font.samples.len() - 1);
            let mut rows: Vec<(u16, u16, String)> = (0..font.preset_count())
                .map(|i| {
                    let (p, name) = font.preset(i);
                    (p.bank, p.program, name.to_string())
                })
                .collect();
            rows.sort();
            for (bank, program, name) in rows {
                let selector = if bank == sf2::DRUM_BANK {
                    "drum:KEY".to_string()
                } else {
                    format!("program:{program}")
                };
                say!("  bank {bank:3}  program {program:3}  {name:<22} {selector}");
            }
        }
        return Ok(0);
    }

    if args.list_samples {
        // The terminating shdr record is a marker, not a sample.
        for sample in &font.samples[..font.samples.len() - 1] {
            if args.json {
                Json::new()
                    .text("name", &sample.name)
                    .num("frames", sample.frames())
                    .num("rate", sample.rate)
                    .num("root_key", sample.root_key)
                    .num("correction_cents", sample.correction)
                    .num("loop_start", sample.loop_start.saturating_sub(sample.start))
                    .num("loop_end", sample.loop_end.saturating_sub(sample.start))
                    .print();
            } else {
                say!(
                    "  {:<22} {:>8} frames  {:>6} Hz  key {:>3}  loop {}..{}",
                    sample.name,
                    sample.frames(),
                    sample.rate,
                    sample.root_key,
                    sample.loop_start.saturating_sub(sample.start),
                    sample.loop_end.saturating_sub(sample.start)
                );
            }
        }
        return Ok(0);
    }

    let Some(text) = &args.extract else {
        return Err(Bad(
            "nothing to do: pass --list, --list-samples or --extract".into()
        ));
    };

    let selector = parse_selector(text)?;
    let (zone, sample) = match &selector {
        Selector::Program { program, bank, key } => match font.zone_for(*program, *key, *bank) {
            Some(found) => (Some(found.0), found.1),
            None => {
                eprintln!(
                    "{}: nothing covers {text}",
                    args.file.display()
                );
                return Ok(NO);
            }
        },
        Selector::Named(name) => match font.find_sample(name) {
            Some(s) => (None, s.clone()),
            None => {
                eprintln!("{}: no sample named {name:?}", args.file.display());
                return Ok(NO);
            }
        },
    };

    // The loop is reported relative to the extracted audio, because that is
    // the only place it means anything once the sample is out of the file.
    let looped = zone.as_ref().map_or(
        sample.loop_end > sample.loop_start,
        |z| z.looped() && sample.loop_end > sample.loop_start,
    );
    let loop_start = looped.then(|| sample.loop_start.saturating_sub(sample.start));
    let loop_end = looped.then(|| sample.loop_end.saturating_sub(sample.start));

    let root = match zone.as_ref().and_then(|z| z.get(sf2::GEN_ROOT_KEY)) {
        Some(k) if (0..=127).contains(&k) => k as u8,
        _ => sample.root_key,
    };
    // A SoundFont corrects tuning from three different places, and a player
    // that reads only one of them plays the sample out of tune.
    let cents = sample.correction as i32
        + zone.as_ref().map_or(0, |z| z.get_or(sf2::GEN_FINE_TUNE, 0))
        + 100 * zone.as_ref().map_or(0, |z| z.get_or(sf2::GEN_COARSE_TUNE, 0));

    let audio = font.pcm(sample.start, sample.end)?;
    if let Some(path) = &args.output {
        write_out(path, &wav::write(&audio, sample.rate))?;
    }

    if args.json {
        Json::new()
            .text("name", &sample.name)
            .maybe("output", args.output.as_ref().map(|p| format!("{:?}", p.display())))
            .num("frames", audio.len())
            .num("rate", sample.rate)
            .num("root_key", root)
            .num("tuning_cents", cents)
            .flag("loops", looped)
            .maybe("loop_start", loop_start)
            .maybe("loop_end", loop_end)
            .print();
    } else {
        if let Some(path) = &args.output {
            say!("wrote {}", path.display());
        }
        say!("  {} ({} frames at {} Hz)", sample.name, audio.len(), sample.rate);
        say!("  plays at key {root}, off by {cents} cents");
        match (loop_start, loop_end) {
            (Some(a), Some(b)) => say!("  loops {a}..{b} ({} frames)", b - a),
            _ => say!("  does not loop"),
        }
    }
    Ok(0)
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Encode(a) => encode(a),
        Command::Decode(a) => decode(a),
        Command::Info(a) => info(a),
        Command::Sf2(a) => soundfont(a),
    };
    match done {
        Ok(code) => ExitCode::from(code),
        Err(message) => {
            eprintln!("error: {message}");
            ExitCode::from(MISUSE)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_selector_says_what_it_expected_when_it_is_not_one() {
        let e = parse_selector("piano").unwrap_err();
        assert!(e.0.contains("program:N"), "{e}");
        let e = parse_selector("instrument:3").unwrap_err();
        assert!(e.0.contains("drum:N"), "{e}");
        let e = parse_selector("program:grand").unwrap_err();
        assert!(e.0.contains("not a number"), "{e}");
    }

    #[test]
    fn a_drum_selector_is_a_key_of_the_percussion_bank() {
        match parse_selector("drum:36").unwrap() {
            Selector::Program { program, bank, key } => {
                assert_eq!((program, bank, key), (0, sf2::DRUM_BANK, 36));
            }
            _ => panic!("a drum is a program"),
        }
    }

    #[test]
    fn a_program_selector_defaults_to_middle_c_and_takes_a_key() {
        match parse_selector("program:12").unwrap() {
            Selector::Program { key, bank, .. } => assert_eq!((key, bank), (REFERENCE_KEY, 0)),
            _ => panic!(),
        }
        match parse_selector("program:12@72").unwrap() {
            Selector::Program { key, .. } => assert_eq!(key, 72),
            _ => panic!(),
        }
    }

    #[test]
    fn a_loop_point_off_a_block_boundary_names_the_two_that_would_work() {
        let dir = std::env::temp_dir().join(format!("brr-cli-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let input = dir.join("ramp.wav");
        let samples: Vec<i16> = (0..64).map(|i| i * 100).collect();
        std::fs::write(&input, wav::write(&samples, 16000)).unwrap();

        let e = encode(&Encode {
            input: input.clone(),
            output: dir.join("out.brr"),
            loop_block: None,
            loop_sample: Some(20),
            rate: None,
            max_error: None,
            json: false,
        })
        .unwrap_err();
        assert!(e.0.contains("16") && e.0.contains("32"), "{e}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_quality_bar_that_is_missed_is_an_answer_and_not_an_error() {
        let dir = std::env::temp_dir().join(format!("brr-cli-bar-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let input = dir.join("noise.wav");
        // Sample-to-sample noise at full scale is the worst case there is: no
        // filter predicts it and the range cannot cover the jumps.
        let noisy: Vec<i16> =
            (0..512).map(|i: i32| if i % 2 == 0 { 32767 } else { -32768 }).collect();
        std::fs::write(&input, wav::write(&noisy, 16000)).unwrap();

        let mut args = Encode {
            input,
            output: dir.join("out.brr"),
            loop_block: None,
            loop_sample: None,
            rate: None,
            max_error: Some(0.0),
            json: false,
        };
        assert_eq!(encode(&args).unwrap(), NO);
        args.max_error = Some(100.0);
        assert_eq!(encode(&args).unwrap(), 0);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_file_that_is_not_a_whole_number_of_blocks_is_refused() {
        let dir = std::env::temp_dir().join(format!("brr-cli-blocks-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("half.brr");
        std::fs::write(&path, [0u8; 10]).unwrap();
        let e = read_blocks(&path).unwrap_err();
        assert!(e.0.contains("10 bytes") && e.0.contains("9-byte"), "{e}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn json_escapes_what_would_otherwise_break_it() {
        // Sample names come out of somebody else's file and do contain quotes.
        let mut out = Json::new().text("name", "a \"quoted\" \\ name").0;
        assert_eq!(out.pop().unwrap(), r#""name": "a \"quoted\" \\ name""#);
    }
}
