//! The patches as a stage of a converter: what the converter asks of this
//! crate, as the files the binary writes into a build, by name. The
//! converter calls [`patches`] as a function and writes the files itself
//! with [`put`](crate::put); the binary's `--request` is a `main` over
//! [`patches_of`].
//!
//! It reads nothing but the request it is given.

use crate::{files, Files, Request};
use serde::Deserialize;
use serde_json::Value;

/// `--request`: the patches of one build, from what the converter decided,
/// each named by its path relative to the build.
pub fn patches(request: &Value) -> Result<Files, String> {
    let request = Request::deserialize(request).map_err(|e| format!("the request: {e}"))?;
    Ok(patches_of(&request))
}

/// [`patches`], with the request already read: the binary reads it from
/// its file, so that a bad one names the file and the line.
pub fn patches_of(request: &Request) -> Files {
    files(request)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{put, Kind};
    use std::path::{Path, PathBuf};

    fn game(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/game")
            .join(name)
    }

    /// The converter's door, a request already parsed into a `Value`,
    /// answers what the binary's answers from the file's text; and `put`
    /// leaves in a build exactly those files, over what a previous run left
    /// there.
    #[test]
    fn the_converter_s_door_answers_what_the_binary_writes() {
        let build =
            std::env::temp_dir().join(format!("rm2k-snes-patches-stage-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&build);
        for name in ["release.json", "special.json"] {
            let text = std::fs::read_to_string(game(name)).unwrap();
            let typed: Request = serde_json::from_str(&text).unwrap();
            let value: Value = serde_json::from_str(&text).unwrap();
            let answered = patches(&value).unwrap();
            assert_eq!(answered, patches_of(&typed), "{name}");
            assert!(!answered.is_empty(), "{name}");

            std::fs::create_dir_all(build.join(Kind::Map.in_build())).unwrap();
            std::fs::write(build.join(Kind::Map.in_build()).join("9999.toml"), "old").unwrap();
            put(&build, &answered).unwrap();
            let mut left = Files::new();
            for kind in Kind::ALL {
                let folder = build.join(kind.in_build());
                for entry in std::fs::read_dir(&folder).unwrap() {
                    let entry = entry.unwrap();
                    let name = format!(
                        "{}/{}",
                        kind.in_build(),
                        entry.file_name().to_string_lossy()
                    );
                    left.insert(name, std::fs::read(entry.path()).unwrap());
                }
            }
            assert_eq!(left, answered, "{name}");
        }
        let _ = std::fs::remove_dir_all(&build);
    }

    /// A request that is not one says so, as the binary did for its file.
    #[test]
    fn a_bad_request_is_a_no() {
        let bad = serde_json::json!({"maps": [{"id": 1}]});
        let no = patches(&bad).unwrap_err();
        assert!(no.starts_with("the request: missing field"), "{no}");
    }

    /// `put` writes only inside the kinds' folders.
    #[test]
    fn put_refuses_a_file_outside_the_patches() {
        let files = Files::from([("patches/auto/maps/a/b.toml".to_string(), Vec::new())]);
        let no = put(Path::new("/nonexistent"), &files).unwrap_err();
        assert!(no.contains("is not inside"), "{no}");
    }
}
