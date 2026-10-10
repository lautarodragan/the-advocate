//! A FaceSet: the picture the faces of the actors, and of the messages, are
//! cut from.
//!
//! It holds 4 faces across by 4 down, of 48x48 each, and a face is named by
//! its index, 0 to 15, row by row: an actor's `face_index` is that number.
//! easyrpg's `Window_Base::DrawFace`.

/// A face is a 48x48 square.
pub const FACE: i32 = 48;
/// How many faces a FaceSet has across and down.
pub const FACES_ACROSS: i32 = 4;
pub const FACES_DOWN: i32 = 4;
/// How many faces a FaceSet has.
pub const FACES: i32 = FACES_ACROSS * FACES_DOWN;

/// Where face `index`, 0 to 15, starts in the FaceSet.
pub fn origin(index: i32) -> (i32, i32) {
    ((index % FACES_ACROSS) * FACE, (index / FACES_ACROSS) * FACE)
}
