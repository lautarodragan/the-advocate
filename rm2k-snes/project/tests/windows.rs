//! `[windows.background]`: a colour or a gradient, by System.

use std::path::Path;

use rm2k_project::windows::{color_text, WindowBackground};
use rm2k_project::Project;

fn project(windows: &str) -> Project {
    Project::from_text(Path::new("/games/one"), &format!("[paths]\ndata = \"data\"\n{windows}")).unwrap()
}

#[test]
fn without_the_table_no_system_has_an_entry() {
    let p = project("");
    assert!(p.window_backgrounds().unwrap().is_empty());
    assert_eq!(p.window_background("ablskin").unwrap(), None);
}

#[test]
fn a_colour_and_a_gradient_by_system_name_without_case() {
    let p = project(
        "[windows.background]\nablskin = \"#000000\"\nRoyal = [\"#783f31\", \"#5a231f\", \"#421D2D\"]\n",
    );
    assert_eq!(p.window_background("AblSkin").unwrap(), Some(WindowBackground::Color([0, 0, 0])));
    assert_eq!(
        p.window_background("royal").unwrap(),
        Some(WindowBackground::Gradient(vec![[0x78, 0x3f, 0x31], [0x5a, 0x23, 0x1f], [0x42, 0x1d, 0x2d]]))
    );
    assert_eq!(p.window_background("thunter").unwrap(), None);
}

/// The average of the line the stops draw: the ends weigh half.
#[test]
fn a_gradient_is_drawn_flat_with_its_average() {
    let g = WindowBackground::Gradient(vec![[0, 0, 0x30], [0, 0, 0x78]]);
    assert_eq!(color_text(g.flat()), "#000054");
    let g = WindowBackground::Gradient(vec![[0, 0, 0], [100, 0, 0], [0, 0, 0]]);
    assert_eq!(g.flat(), [50, 0, 0]);
    assert_eq!(WindowBackground::Color([1, 2, 3]).flat(), [1, 2, 3]);
}

#[test]
fn what_is_not_a_colour_says_which_system_and_what_it_takes() {
    for bad in ["\"black\"", "\"#00000\"", "[\"#000000\"]", "[\"#000000\", 3]", "0"] {
        let p = project(&format!("[windows.background]\nablskin = {bad}\n"));
        let e = p.window_backgrounds().unwrap_err().0;
        assert!(e.contains("windows.background.ablskin") && e.contains("#rrggbb"), "{bad}: {e}");
    }
}

#[test]
fn one_value_for_the_whole_game_is_refused_saying_it_goes_by_system() {
    let p = project("[windows]\nbackground = \"#000000\"\n");
    let e = p.window_backgrounds().unwrap_err().0;
    assert!(e.contains("keyed by the System"), "{e}");
}

#[test]
fn the_same_system_twice_in_two_cases_is_refused() {
    let p = project("[windows.background]\nablskin = \"#000000\"\nABLSKIN = \"#000001\"\n");
    let e = p.window_backgrounds().unwrap_err().0;
    assert!(e.contains("twice"), "{e}");
}
