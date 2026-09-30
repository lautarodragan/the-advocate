# resample: Pillow's LANCZOS, to the bit

A library that resizes a picture exactly as Pillow's
`Image.resize(size, Image.LANCZOS)` does: not a Lanczos filter, **that
one**, down to the last rounding.

    resample::lanczos_rgb(&rgb, width, height, new_width, new_height)
    resample::lanczos_rgba(&rgba, width, height, new_width, new_height)

`cargo test`. There are no dependencies.

## Why to the bit

A picture that is resized and then brought down to a handful of colours
keeps the colours its pixels land on. A resampler one step away from
Pillow's changes which colours are the most used, and with them the
palette and every index after it. Anything that used to be made with
Pillow and has to come out the same byte for byte needs these pixels, not
pixels like these.

## What is copied

`libImaging/Resample.c` and the lines of `Image.resize` around it, from
Pillow 12.3.0:

* **The weights** are computed in `double` —the filter is
  `sinc(x) * sinc(x / 3)`, with the C library's `sin`—, normalised so each
  output pixel's add up to one, and turned into integers of 22 fractional
  bits, rounding away from zero.
* **Two passes**, across and then down, each a weighted sum in 32-bit
  integers clipped back to a byte: the rounding after the first pass is
  part of the result. The pass across only covers the rows the pass down
  reads, and a pass whose size does not change is skipped.
* **Shrinking widens the filter** by the same factor, so every source pixel
  weighs in; enlarging does not.
* **RGBA is premultiplied** by its alpha before and divided back after,
  with Pillow's own roundings for both, so a transparent pixel does not
  bleed its colour into its neighbours. A pixel that ends fully opaque or
  fully transparent is left as the sum gave it.
* **The same size is a copy**, without the premultiplying round trip; and
  a picture a hundred times taller than wide that shrinks in height is
  resized down first and across after, in two calls, as Pillow does.

`reducing_gap` and `box`, which a plain `resize(size, LANCZOS)` uses
neither of, are not here.

## The tests

`tests/pillow.rs` resizes pictures of noise made by a congruence and
compares against the sha256 of what Pillow wrote for the same pictures:
screens shrunk, pictures enlarged, one axis alone, the tall case, and RGBA
with transparent, opaque and translucent pixels.
