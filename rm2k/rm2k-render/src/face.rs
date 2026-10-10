//! A face: the 48x48 square of a FaceSet an actor, or a message, shows.
//!
//! It is the square as is, with the FaceSet's colour key: **index 0 of an
//! indexed FaceSet is transparent**, like in any RM2k picture, and it is
//! not a detail —in some FaceSets it is a colour that fills most of the
//! square around the figure—. Where the face goes, and what becomes of its
//! colours, is the caller's.

use crate::fail::Result;
use crate::picture::{self, Picture};
use crate::request::{self, Files, Request};
use rm2k_rules::faceset::{self, FACE, FACES};
use std::path::Path;

/// Face `index`, 0 to 15, of a FaceSet already read with its colour key.
pub fn face(faceset: &Picture, index: i32) -> Picture {
    let (x, y) = faceset::origin(index);
    faceset.crop(x as i64, y as i64, FACE as usize, FACE as usize)
}

/// Draws a request: each entry is `{"faceset_file": path, "index": n}`,
/// and face `i` is written as `<i>.png`, 48x48 RGBA.
pub fn write(dir: &Path, request_path: &Path) -> Result<()> {
    let request = Request::read(request_path)?;
    let mut files = Files::new(picture::read_rm2k);
    request::write(dir, &request, |r, i| {
        let index = r.number_in(i, "index", None, 0..FACES as i64)?;
        Ok(face(files.get(&r.file(i, "faceset_file")?)?, index as i32))
    })
}
