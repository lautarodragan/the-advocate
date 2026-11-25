//! What the tests of the `map` stage share: running it on a request file
//! and writing its answer where they read it.

use std::path::Path;
use wally::{request, stage};

/// [`stage::map`] —what the converter calls— on the dump `dump` with its
/// pictures in `pictures` and the request in the file `request`, every file
/// it answers written into `out`; a stage that says no fails the test with
/// what it said.
pub fn map(dump: impl AsRef<Path>, pictures: impl AsRef<Path>, request: &Path, out: &Path) {
    let (asked, whose) = request::read(request).unwrap_or_else(|bad| panic!("{bad}"));
    let asked = request::typed(&asked, &whose).unwrap_or_else(|bad| panic!("{bad}"));
    let files = stage::map(dump.as_ref(), &[pictures.as_ref().to_path_buf()], &asked)
        .unwrap_or_else(|bad| panic!("{bad}"));
    std::fs::create_dir_all(out).unwrap();
    for (name, bytes) in &files {
        std::fs::write(out.join(name), bytes).unwrap();
    }
}
