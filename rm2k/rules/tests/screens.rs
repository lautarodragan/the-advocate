//! Where the pieces of a FaceSet and a System are, and a picture's opacity:
//! easyrpg's numbers, checked where they are easy to get wrong.

use ditto::schema::SystemStretch;
use rm2k_rules::system::{self, Background};
use rm2k_rules::{faceset, picture};

#[test]
fn faces_go_row_by_row_four_across() {
    assert_eq!(faceset::origin(0), (0, 0));
    assert_eq!(faceset::origin(3), (144, 0));
    assert_eq!(faceset::origin(4), (0, 48));
    assert_eq!(faceset::origin(15), (144, 144));
}

#[test]
fn text_colours_go_ten_across_below_the_frame() {
    assert_eq!(system::text_color_origin(0), (0, 48));
    assert_eq!(system::text_color_origin(9), (144, 48));
    assert_eq!(system::text_color_origin(10), (0, 64));
    assert_eq!(system::text_color_origin(19), (144, 64));
    // The last block ends at the System's corner.
    let (x, y) = system::text_color_origin(system::TEXT_COLORS - 1);
    assert_eq!(
        (x + system::COLOR_BLOCK, y + system::COLOR_BLOCK),
        (system::SYSTEM_WIDTH, system::SYSTEM_HEIGHT)
    );
}

#[test]
fn only_rm2ks_backgrounds_are_drawn() {
    assert_eq!(
        system::background(SystemStretch::Stretch),
        Some(Background::Stretched)
    );
    assert_eq!(
        system::background(SystemStretch::Tiled),
        Some(Background::Tiled)
    );
    assert_eq!(system::background(SystemStretch::EasyrpgNone), None);
    assert_eq!(system::background(SystemStretch::Other(7)), None);
}

#[test]
fn a_pictures_opacity_rounds_down() {
    assert_eq!(picture::opacity(0), 255);
    assert_eq!(picture::opacity(1), 252);
    assert_eq!(picture::opacity(50), 127);
    assert_eq!(picture::opacity(100), 0);
    // Past the editor's range it stays at the ends.
    assert_eq!(picture::opacity(-5), 255);
    assert_eq!(picture::opacity(120), 0);
}
