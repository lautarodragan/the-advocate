//! LC_LZ2 from the command line.
//!
//! Where files go is the caller's business: nothing here has a default path or
//! a directory it knows about. Every input goes with the output named right
//! after it, so a build script can do a few hundred files in one process.

use std::process::ExitCode;

/// A stream that does not decode is an answer ("no"); a call that makes no
/// sense is a different one, and a script wants to tell them apart.
const NO: u8 = 1;
const MISUSE: u8 = 2;

const USAGE: &str = "\
usage: lz2 compress   [--no-increasing] IN OUT [IN OUT ...]
       lz2 decompress IN OUT [IN OUT ...]
       lz2 stats      IN [IN ...]

compress    writes each IN as one LC_LZ2 stream, the shortest there is for the
            format and, among the shortest, the one with the fewest commands.
            IN can be at most 65536 bytes: a repeat addresses the output with
            16 bits. --no-increasing leaves out command 3, for decoders
            that do not implement it.
decompress  writes each stream back; refuses a stream with bytes after its $FF.
stats       for each stream: its size, its output size and how many commands
            of each kind it has, one line of JSON per stream.

Exit codes: 1 a stream does not decode or an input does not fit; 2 the call
itself is wrong (missing arguments, a file that cannot be read).";

fn pairs(args: &[String]) -> Result<Vec<(&str, &str)>, String> {
    if args.is_empty() || args.len() % 2 != 0 {
        return Err("expected IN OUT pairs".into());
    }
    Ok(args
        .chunks(2)
        .map(|p| (p[0].as_str(), p[1].as_str()))
        .collect())
}

fn read(path: &str) -> Result<Vec<u8>, (u8, String)> {
    std::fs::read(path).map_err(|e| (MISUSE, format!("{}: {}", path, e)))
}

fn write(path: &str, data: &[u8]) -> Result<(), (u8, String)> {
    std::fs::write(path, data).map_err(|e| (MISUSE, format!("{}: {}", path, e)))
}

fn stats(path: &str, stream: &[u8]) -> Result<String, (u8, String)> {
    let (out, _) = lz2::decompress_prefix(stream).map_err(|e| (NO, format!("{}: {}", path, e)))?;
    let mut kinds = [0usize; 5];
    let mut i = 0;
    loop {
        let h = stream[i];
        if h == lz2::END {
            break;
        }
        let (kind, len, header) = if h >> 5 == 7 {
            (
                (h >> 2) & 7,
                ((h as usize & 3) << 8 | stream[i + 1] as usize) + 1,
                2,
            )
        } else {
            (h >> 5, (h as usize & 31) + 1, 1)
        };
        kinds[kind as usize] += 1;
        let operand = match kind {
            lz2::LITERAL => len,
            lz2::BYTE_FILL | lz2::INCREASING => 1,
            _ => 2,
        };
        i += header + operand;
    }
    Ok(format!(
        "{{\"file\": {:?}, \"stream\": {}, \"output\": {}, \"literal\": {}, \"byte_fill\": {}, \
         \"word_fill\": {}, \"increasing\": {}, \"repeat\": {}}}",
        path,
        stream.len(),
        out.len(),
        kinds[0],
        kinds[1],
        kinds[2],
        kinds[3],
        kinds[4]
    ))
}

fn run(args: &[String]) -> Result<(), (u8, String)> {
    let (command, rest) = match args.split_first() {
        Some((c, r)) => (c.as_str(), r),
        None => return Err((MISUSE, USAGE.into())),
    };
    match command {
        "compress" => {
            let mut options = lz2::Options::default();
            let mut rest = rest;
            if rest.first().map(|a| a.as_str()) == Some("--no-increasing") {
                options.increasing = false;
                rest = &rest[1..];
            }
            for (input, output) in
                pairs(rest).map_err(|e| (MISUSE, format!("{}\n\n{}", e, USAGE)))?
            {
                let data = read(input)?;
                let stream = lz2::compress_with(&data, options)
                    .map_err(|e| (NO, format!("{}: {}", input, e)))?;
                write(output, &stream)?;
            }
            Ok(())
        }
        "decompress" => {
            for (input, output) in
                pairs(rest).map_err(|e| (MISUSE, format!("{}\n\n{}", e, USAGE)))?
            {
                let stream = read(input)?;
                let data =
                    lz2::decompress(&stream).map_err(|e| (NO, format!("{}: {}", input, e)))?;
                write(output, &data)?;
            }
            Ok(())
        }
        "stats" => {
            if rest.is_empty() {
                return Err((MISUSE, USAGE.into()));
            }
            for input in rest {
                let stream = read(input)?;
                println!("{}", stats(input, &stream)?);
            }
            Ok(())
        }
        "-h" | "--help" | "help" => {
            println!("{}", USAGE);
            Ok(())
        }
        other => Err((MISUSE, format!("no command {:?}\n\n{}", other, USAGE))),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err((code, message)) => {
            eprintln!("lz2: {}", message);
            ExitCode::from(code)
        }
    }
}
