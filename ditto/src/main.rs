//! Ditto: `.ldb`/`.lmu`/`.lmt` ⇄ JSON.

use ditto::archivo;
use std::path::Path;
use std::process::ExitCode;

fn uso() -> ExitCode {
    eprintln!(
        "uso:\n  \
         ditto leer   <archivo.lmu|.ldb|.lmt> [salida.json]\n  \
         ditto volver <archivo.json> [salida.lmu]\n\n\
         Sin salida, escribe por la salida estándar."
    );
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 2 {
        return uso();
    }
    let entrada = Path::new(&args[1]);
    let salida = args.get(2).map(Path::new);
    let r = match args[0].as_str() {
        "leer" => leer(entrada, salida),
        "volver" => volver(entrada, salida),
        _ => return uso(),
    };
    match r {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("ditto: {e}");
            ExitCode::FAILURE
        }
    }
}

fn leer(entrada: &Path, salida: Option<&Path>) -> Result<(), Box<dyn std::error::Error>> {
    let doc = archivo::leer(&std::fs::read(entrada)?)?;
    volcar(&serde_json::to_vec_pretty(&doc)?, salida)
}

fn volver(entrada: &Path, salida: Option<&Path>) -> Result<(), Box<dyn std::error::Error>> {
    let doc: archivo::Documento = serde_json::from_slice(&std::fs::read(entrada)?)?;
    volcar(&archivo::escribir(&doc)?, salida)
}

fn volcar(d: &[u8], salida: Option<&Path>) -> Result<(), Box<dyn std::error::Error>> {
    match salida {
        Some(p) => std::fs::write(p, d)?,
        None => {
            use std::io::Write;
            std::io::stdout().write_all(d)?;
        }
    }
    Ok(())
}
