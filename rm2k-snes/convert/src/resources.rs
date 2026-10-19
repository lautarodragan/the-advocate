//! How RM2k finds a resource: by name, in a folder, in each directory in
//! order, **without regard to case** —the games were made on Windows, and
//! a map says nothing about the real case of a file—.

use std::path::{Path, PathBuf};

/// `name.ext` into `name` and `.ext`. A leading dot is not an extension.
fn split_extension(file_name: &str) -> (&str, &str) {
    match file_name.rfind('.') {
        Some(at) if at > 0 && !file_name[..at].chars().all(|c| c == '.') => {
            (&file_name[..at], &file_name[at..])
        }
        _ => (file_name, ""),
    }
}

/// `<dir>/<folder>/<name><ext>`, for the first directory that has it and
/// any of `extensions`.
pub fn find<P: AsRef<Path>>(
    dirs: &[P],
    folder: &str,
    name: &str,
    extensions: &[&str],
) -> Option<PathBuf> {
    let (folder, name) = (folder.to_lowercase(), name.to_lowercase());
    for dir in dirs {
        let Ok(entries) = std::fs::read_dir(dir.as_ref()) else {
            continue;
        };
        for entry in entries.flatten() {
            if entry.file_name().to_string_lossy().to_lowercase() != folder {
                continue;
            }
            let subdir = dir.as_ref().join(entry.file_name());
            let Ok(files) = std::fs::read_dir(&subdir) else {
                continue;
            };
            for file in files.flatten() {
                let file_name = file.file_name().to_string_lossy().to_string();
                let (base, extension) = split_extension(&file_name);
                if base.to_lowercase() == name
                    && extensions.contains(&extension.to_lowercase().as_str())
                {
                    return Some(subdir.join(file.file_name()));
                }
            }
        }
    }
    None
}
