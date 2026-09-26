//! Round trips, the edges of the header, and streams a correct decoder has to
//! refuse.

use lz2::{compress, decompress, decompress_prefix, parse, Error};

/// A small deterministic generator, so a failing case can be rerun as is.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    fn byte(&mut self) -> u8 {
        (self.next() >> 24) as u8
    }
}

fn round_trip(data: &[u8]) -> Vec<u8> {
    let stream = compress(data).expect("compresses");
    assert_eq!(decompress(&stream).expect("decodes"), data, "the round trip changed the data");
    stream
}

/// Data shaped like what the format is for: runs, repeated blocks with small
/// edits, counters and noise, mixed.
fn mixed(rng: &mut Rng, len: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(len);
    while out.len() < len {
        match rng.next() % 6 {
            0 => {
                let b = rng.byte();
                let n = 1 + (rng.next() % 1500) as usize;
                out.extend(std::iter::repeat(b).take(n));
            }
            1 => {
                let (a, b) = (rng.byte(), rng.byte());
                let n = 1 + (rng.next() % 300) as usize;
                out.extend((0..n).map(|k| if k % 2 == 0 { a } else { b }));
            }
            2 => {
                let b = rng.byte();
                let n = 1 + (rng.next() % 400) as usize;
                out.extend((0..n).map(|k| b.wrapping_add(k as u8)));
            }
            3 if out.len() > 8 => {
                let from = (rng.next() as usize) % out.len();
                let n = 1 + (rng.next() % 1200) as usize;
                for k in 0..n {
                    let b = out[from + k];
                    out.push(b);
                }
                if rng.next() % 2 == 0 {
                    let at = out.len() - 1;
                    out[at] ^= 0x55;
                }
            }
            _ => {
                let n = 1 + (rng.next() % 60) as usize;
                out.extend((0..n).map(|_| rng.byte()));
            }
        }
    }
    out.truncate(len);
    out
}

#[test]
fn empty_input_is_just_the_terminator() {
    assert_eq!(round_trip(&[]), vec![0xFF]);
}

#[test]
fn one_byte_is_a_literal() {
    assert_eq!(round_trip(&[0x42]), vec![0x00, 0x42, 0xFF]);
}

#[test]
fn a_run_of_one_byte_is_a_byte_fill() {
    assert_eq!(round_trip(&[7; 32]), vec![0x3F, 7, 0xFF]);
    // 33 takes the long header: 111 001 00, then 32.
    assert_eq!(round_trip(&[7; 33]), vec![0xE4, 32, 7, 0xFF]);
}

#[test]
fn a_run_longer_than_a_command_is_split() {
    let stream = round_trip(&[0; 5000]);
    // Five long byte fills of at most 1024 and the terminator.
    assert_eq!(stream.len(), 5 * 3 + 1);
}

#[test]
fn a_counter_is_an_increasing_fill() {
    let data: Vec<u8> = (0..=255u8).chain(0..10).collect();
    assert_eq!(round_trip(&data), vec![0xE0 | (3 << 2) | 1, 9, 0, 0xFF]);
}

#[test]
fn an_alternating_pair_is_a_word_fill() {
    let data: Vec<u8> = (0..20).map(|k| if k % 2 == 0 { 0xAB } else { 0xCD }).collect();
    assert_eq!(round_trip(&data), vec![0x40 | 19, 0xAB, 0xCD, 0xFF]);
}

#[test]
fn a_repeat_carries_its_address_big_endian() {
    let mut data: Vec<u8> = (0..300).map(|k| (k * 7 % 251) as u8).collect();
    let copy = data[260..290].to_vec();
    data.extend_from_slice(&copy);
    let stream = round_trip(&data);
    // 260 is $0104: the high byte goes first.
    let at = stream.windows(3).position(|w| w == [0x80 | 29, 0x01, 0x04]);
    assert!(at.is_some(), "no repeat of 30 from $0104 in {:02X?}", stream);
}

#[test]
fn mixed_data_round_trips_at_every_size_up_to_the_limit() {
    let mut rng = Rng(0x9E37_79B9_7F4A_7C15);
    for &len in &[2usize, 3, 31, 32, 33, 1023, 1024, 1025, 4096, 32768, 65536] {
        let data = mixed(&mut rng, len);
        round_trip(&data);
    }
}

#[test]
fn noise_round_trips_and_grows_by_at_most_one_in_thirty_two() {
    let mut rng = Rng(12345);
    let data: Vec<u8> = (0..20000).map(|_| rng.byte()).collect();
    let stream = round_trip(&data);
    assert!(stream.len() <= data.len() + data.len() / 32 + 2, "{} bytes for {}", stream.len(), data.len());
}

#[test]
fn the_parse_is_never_longer_than_a_greedy_one() {
    // A greedy parser takes the longest thing at each step. The optimal parse
    // can only tie or win; the case below is one where greedy loses.
    let mut data = vec![1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    data.extend_from_slice(&[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    data.extend_from_slice(&[9, 9, 9, 9, 9, 9, 9, 9, 9]);
    let stream = round_trip(&data);
    assert!(stream.len() <= 1 + 10 + 3 + 2 + 1, "{:02X?}", stream);
}

#[test]
fn among_the_shortest_it_takes_the_fewest_commands() {
    // Four equal bytes: a fill (2 bytes) or a literal (5). Obvious, but it is
    // the tie-break at work on every block of zeros between other data.
    let data = [5, 0, 0, 0, 0, 6];
    let commands = parse(&data).unwrap();
    let stream = round_trip(&data);
    assert_eq!(stream.len(), 2 + 2 + 2 + 1);
    assert_eq!(commands.len(), 3);
}

#[test]
fn too_long_an_input_is_refused() {
    assert_eq!(compress(&vec![0; 65537]), Err(Error::TooLong(65537)));
}

#[test]
fn a_stream_without_its_terminator_is_truncated() {
    assert!(matches!(decompress(&[0x01, 0xAA, 0xBB]), Err(Error::Truncated(_))));
    assert!(matches!(decompress(&[0x21]), Err(Error::Truncated(_))));
}

#[test]
fn bytes_after_the_terminator_are_refused_but_a_prefix_is_fine() {
    assert_eq!(decompress(&[0x00, 0x11, 0xFF, 0x00]), Err(Error::Trailing(3)));
    assert_eq!(decompress_prefix(&[0x00, 0x11, 0xFF, 0x00]).unwrap(), (vec![0x11], 3));
}

#[test]
fn a_repeat_from_the_future_is_refused() {
    // One literal, then a repeat from position 1 while producing position 1.
    assert_eq!(
        decompress(&[0x00, 0x11, 0x80, 0x00, 0x01, 0xFF]),
        Err(Error::BadRepeat { offset: 2, from: 1, at: 1 })
    );
}

#[test]
fn an_overlapping_repeat_repeats() {
    // "ab", then 6 from position 0: abababab.
    assert_eq!(decompress(&[0x01, b'a', b'b', 0x85, 0x00, 0x00, 0xFF]).unwrap(), b"abababab");
}

#[test]
fn commands_five_and_six_do_not_exist() {
    assert_eq!(decompress(&[0xA0, 0xFF]), Err(Error::BadCommand { offset: 0, command: 5 }));
    assert_eq!(decompress(&[0xF8, 0x00, 0xFF]), Err(Error::BadCommand { offset: 0, command: 6 }));
}

#[test]
fn an_output_past_the_limit_is_refused() {
    // 65 long byte fills of 1024 are 66560 bytes.
    let mut stream = Vec::new();
    for _ in 0..65 {
        stream.extend_from_slice(&[0xE7, 0xFF, 0x00]);
    }
    stream.push(0xFF);
    assert!(matches!(decompress(&stream), Err(Error::Overflow(_))));
}
