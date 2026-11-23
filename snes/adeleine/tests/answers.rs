//! Three answers small enough to read whole, as JSON: the order a mapping
//! comes back in, a pack that does not fit, and a reduction's local
//! mappings, merges and palettes.

mod common;

use adeleine::{merge_least_visible, reduce_colors, try_pack, Color};
use common::{merged_answer, packed_answer, reduced_answer};
use std::collections::BTreeSet;

fn tile(colors: &[Color]) -> BTreeSet<Color> {
    colors.iter().copied().collect()
}

#[test]
fn a_merge_gives_the_mapping_in_the_order_given() {
    let counts = [([2, 0, 0], 1), ([0, 0, 0], 9), ([31, 31, 31], 5)];
    assert_eq!(
        merged_answer(&merge_least_visible(&counts, 2).unwrap()).to_string(),
        r#"{"mapping":[[0,0,0],[0,0,0],[31,31,31]],"merges":[[[2,0,0],[0,0,0],1]]}"#
    );
}

#[test]
fn a_pack_that_does_not_fit_answers_null() {
    let tiles = [tile(&[[1, 1, 1], [2, 2, 2]]), tile(&[[3, 3, 3]])];
    assert_eq!(
        packed_answer(try_pack(&tiles, 1, 2).as_deref()).to_string(),
        r#"{"palettes":null}"#
    );
}

#[test]
fn a_reduction_gives_local_mappings_merges_and_palettes() {
    let counts = [([1, 1, 1], 4), ([2, 2, 2], 1), ([3, 3, 3], 8)];
    let tiles = [tile(&[[1, 1, 1], [2, 2, 2]]), tile(&[[3, 3, 3]])];
    assert_eq!(
        reduced_answer(&reduce_colors(&counts, &tiles, 1, 2).unwrap()).to_string(),
        r#"{"merges":[[0,[2,2,2],[1,1,1],1]],"palettes":[[[1,1,1],[3,3,3]]],"tiles":[{"mapping":[[1,1,1],[1,1,1]],"palette":0},{"mapping":[[3,3,3]],"palette":0}]}"#
    );
}
