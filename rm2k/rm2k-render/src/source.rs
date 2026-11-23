//! Where a picture comes from: the game's folder first, then the RTP's.

use std::path::PathBuf;

/// Looks for `<dir>/<folder>/<name>.png` or `.bmp`, in each directory in
/// order, **without regard to case**: RM2k stores names without extension
/// and the games were made on Windows, so a map says nothing about the real
/// case of a file.
pub fn find_resource(dirs: &[PathBuf], folder: &str, name: &str) -> Option<PathBuf> {
    let (folder, name) = (folder.to_lowercase(), name.to_lowercase());
    for dir in dirs {
        let Ok(entries) = std::fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            if entry.file_name().to_string_lossy().to_lowercase() != folder {
                continue;
            }
            let Ok(files) = std::fs::read_dir(entry.path()) else {
                continue;
            };
            for file in files.flatten() {
                let path = file.path();
                let file_name = file.file_name().to_string_lossy().to_string();
                let (base, extension) = split_extension(&file_name);
                if base.to_lowercase() == name
                    && matches!(extension.to_lowercase().as_str(), ".png" | ".bmp")
                {
                    return Some(path);
                }
            }
        }
    }
    None
}

/// `name.ext` into `name` and `.ext`. A leading dot is not an extension.
fn split_extension(file_name: &str) -> (&str, &str) {
    match file_name.rfind('.') {
        Some(0) | None => (file_name, ""),
        Some(at) => file_name.split_at(at),
    }
}
