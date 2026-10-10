//! Merging the pair of colours that shows the least, until what is left
//! passes.
//!
//! "What shows the least" is **how many pixels move times how far they
//! move**: the cost of sending colour `a` to colour `b` is
//! `pixels(a) * luma_distance(a, b)`, which is the error the change adds to
//! the picture. The cheapest pair is merged, the pixels of the one that went
//! are added to the one that stayed, and it repeats.
//!
//! The criterion used to be just `pixels(a)`: the least used colour was
//! killed without looking at how far away its neighbour was. A colour can
//! cover few pixels and still **define the drawing** —a highlight, an eye,
//! the edge of a helmet—, and sending it ten steps away shows; meanwhile two
//! nearly equal greys covering half the sheet both survived because neither
//! was the least used. With the cost above it is exactly the other way
//! around: the two greys melt into one —it costs almost nothing— and the
//! highlight stays, which is a palette entry well spent.
//!
//! It does not invent colours: the one that stays is always one of those
//! that were already there, so nothing has to be quantized again. And it is
//! deterministic: the cost is an integer and ties are broken by the colour.

use crate::fail::{Bad, Result};
use crate::Color;

/// Distance between colours, weighted as the eye perceives it.
///
/// The weights are the usual luma ones —0.30 / 0.59 / 0.11— multiplied by a
/// hundred so the math is **integer**. The order it produces is the same as
/// with the fractional coefficients, and in exchange two equal distances
/// compare equal: the merge multiplies this by a pixel count and then takes
/// the smallest, and there a tie resolved by the last bit of a float is
/// exactly the kind of difference that changes the output without anyone
/// having touched anything.
pub fn luma_distance(a: Color, b: Color) -> i64 {
    let d = |k: usize| i64::from(a[k]) - i64::from(b[k]);
    30 * d(0) * d(0) + 59 * d(1) * d(1) + 11 * d(2) * d(2)
}

/// One merge: every pixel of `victim` became `target`. `pixels` is how many
/// the victim had when it went, counting those it had taken from earlier
/// victims.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Merge {
    pub victim: Color,
    pub target: Color,
    pub pixels: u64,
}

/// What a merge decided: for each colour it was given, **in the order it was
/// given**, the colour it became —itself if it survived—; and the merges, in
/// the order they were made.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Merged {
    pub mapping: Vec<Color>,
    pub merges: Vec<Merge>,
}

/// Merges until at most `keep` colours are left.
///
/// `counts` is each colour with its pixels; a colour may not appear twice.
pub fn merge_least_visible(counts: &[(Color, u64)], keep: usize) -> Result<Merged> {
    let (merged, ()) = merge_until(counts, |merger| (merger.alive <= keep).then_some(()))?;
    Ok(merged)
}

/// Merges until `accept` says what is left passes, and hands back what it
/// said with it. It is asked before every merge, the first time with nothing
/// merged yet, and gets the mapping so far: for each colour of `counts`, in
/// that order, the colour it became.
///
/// When a single colour is left and it still does not pass, the answer is
/// no.
pub fn merge_until<T>(
    counts: &[(Color, u64)],
    mut accept: impl FnMut(&Progress) -> Option<T>,
) -> Result<(Merged, T)> {
    let mut merger = Merger::new(counts)?;
    loop {
        if let Some(said) = accept(&merger.progress) {
            let Progress {
                mapping, merges, ..
            } = merger.progress;
            return Ok((Merged { mapping, merges }, said));
        }
        if merger.progress.alive <= 1 {
            return Err(Bad::answer("The palette could not be reduced enough."));
        }
        merger.merge_one();
    }
}

/// Where a merge is, for `accept` to look at.
pub struct Progress {
    /// For each colour it was given, in that order, the colour it is now.
    pub mapping: Vec<Color>,
    /// The merges made so far.
    pub merges: Vec<Merge>,
    /// How many distinct colours are left.
    pub alive: usize,
}

/// The state of a merge. Colours are worked on **by their rank in sorted
/// order**, which makes breaking a tie "by colour" the same as breaking it by
/// index, integer and without comparing colours.
struct Merger {
    colors: Vec<Color>,
    weight: Vec<i64>,
    alive: Vec<bool>,
    /// Which colours of `counts` —by their place there— each living one
    /// stands for today, so as not to walk the whole mapping on every merge.
    members: Vec<Vec<usize>>,
    /// The cheapest neighbour of each living colour, and what it costs to
    /// send it there. It is recomputed only for those whose neighbour was
    /// the one that died —and for the one that grew—, which is what keeps
    /// this from being cubic: a sheet can reach three hundred colours and
    /// merge a hundred.
    cost: Vec<i64>,
    neighbor: Vec<Option<usize>>,
    progress: Progress,
}

impl Merger {
    fn new(counts: &[(Color, u64)]) -> Result<Self> {
        let mut order: Vec<usize> = (0..counts.len()).collect();
        order.sort_by_key(|&i| counts[i].0);
        if let Some(pair) = order.windows(2).find(|w| counts[w[0]].0 == counts[w[1]].0) {
            let c = counts[pair[0]].0;
            return Err(Bad::usage(format!(
                "colour ({}, {}, {}) is given twice",
                c[0], c[1], c[2]
            )));
        }
        let n = counts.len();
        let mut weight = Vec::with_capacity(n);
        for &i in &order {
            let pixels = i64::try_from(counts[i].1)
                .map_err(|_| Bad::usage("a pixel count does not fit in 63 bits"))?;
            weight.push(pixels);
        }
        let mut merger = Merger {
            colors: order.iter().map(|&i| counts[i].0).collect(),
            members: order.iter().map(|&i| vec![i]).collect(),
            weight,
            alive: vec![true; n],
            cost: vec![0; n],
            neighbor: vec![None; n],
            progress: Progress {
                mapping: counts.iter().map(|&(c, _)| c).collect(),
                merges: Vec::new(),
                alive: n,
            },
        };
        for i in 0..n {
            merger.recompute(i);
        }
        Ok(merger)
    }

    /// The nearest living colour to `i`, by `(distance, rank)`.
    fn recompute(&mut self, i: usize) {
        let mut best: Option<(i64, usize)> = None;
        for j in 0..self.colors.len() {
            if j == i || !self.alive[j] {
                continue;
            }
            let d = luma_distance(self.colors[i], self.colors[j]);
            if best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, j));
            }
        }
        match best {
            Some((d, j)) => {
                self.cost[i] = self.weight[i] * d;
                self.neighbor[i] = Some(j);
            }
            None => self.neighbor[i] = None,
        }
    }

    /// The living colour that is cheapest to move, by `(cost, rank)`, goes
    /// to its neighbour.
    fn merge_one(&mut self) {
        let mut victim: Option<usize> = None;
        for i in 0..self.colors.len() {
            if self.alive[i] && victim.is_none_or(|v| self.cost[i] < self.cost[v]) {
                victim = Some(i);
            }
        }
        let victim = victim.expect("two colours are alive");
        let target = self.neighbor[victim].expect("two colours are alive");
        let members = std::mem::take(&mut self.members[victim]);
        for &given in &members {
            self.progress.mapping[given] = self.colors[target];
        }
        self.members[target].extend(members);
        self.progress.merges.push(Merge {
            victim: self.colors[victim],
            target: self.colors[target],
            pixels: self.weight[victim] as u64,
        });
        self.weight[target] += self.weight[victim];
        self.alive[victim] = false;
        self.progress.alive -= 1;
        self.recompute(target);
        for i in 0..self.colors.len() {
            if i != target && self.alive[i] && self.neighbor[i] == Some(victim) {
                self.recompute(i);
            }
        }
    }
}
