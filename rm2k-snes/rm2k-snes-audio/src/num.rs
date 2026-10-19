//! The arithmetic every number here goes through, spelled once.
//!
//! What this crate writes into a cartridge came out of a Python program
//! until 2026-09-29, and has to keep coming out byte for byte the same. So
//! rounding is to the nearest **even** on a tie, which is what Python's
//! `round` does and not what `f64::round` does, and integer division
//! floors instead of truncating towards zero.

/// Rounds to the nearest integer, ties to even.
pub fn round(x: f64) -> i64 {
    x.round_ties_even() as i64
}

/// `x` to the `y`, always through the C library's `pow`, which is what
/// Python's `**` calls. With a constant `y` the compiler would otherwise turn
/// `x.powf(2.0)` into `x * x`, and the two can differ in the last bit.
pub fn pow(x: f64, y: f64) -> f64 {
    x.powf(std::hint::black_box(y))
}

/// Integer division rounding towards minus infinity.
pub fn floor_div(a: i64, b: i64) -> i64 {
    a.div_euclid(b) - if b < 0 && a.rem_euclid(b) != 0 { 1 } else { 0 }
}

/// A float rounded to `digits` decimals, correctly: the decimal nearest to
/// the exact binary value, ties to even, as Python's `round(x, digits)`.
pub fn round_to(x: f64, digits: usize) -> f64 {
    format!("{x:.digits$}")
        .parse()
        .expect("a formatted float parses back")
}

/// The sum of a slice the way numpy adds one up: pairwise, in blocks of
/// eight accumulators. Summing in another order moves the last bit, and a
/// filter kernel normalised by a different sum is a different kernel.
pub fn numpy_sum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut res = -0.0;
        for &x in a {
            res += x;
        }
        return res;
    }
    if n <= 128 {
        let mut r = [0.0; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - n % 8 {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        return res;
    }
    let mut n2 = n / 2;
    n2 -= n2 % 8;
    numpy_sum(&a[..n2]) + numpy_sum(&a[n2..])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ties_go_to_the_even_neighbour() {
        assert_eq!(
            [0.5, 1.5, 2.5, -0.5, -1.5, 2.4, 2.6].map(round),
            [0, 2, 2, 0, -2, 2, 3]
        );
    }

    #[test]
    fn integer_division_floors() {
        assert_eq!(floor_div(7, 2), 3);
        assert_eq!(floor_div(-7, 2), -4);
        assert_eq!(floor_div(-8, 2), -4);
        assert_eq!(floor_div(7, -2), -4);
    }

    #[test]
    fn decimals_round_the_exact_value() {
        // 2.675 is 2.67499999... in binary: Python's round gives 2.67.
        assert_eq!(round_to(2.675, 2), 2.67);
        assert_eq!(round_to(0.1234, 3), 0.123);
    }
}
