# rm2k-snes-images: a game's pictures on the console

The pictures of an RPG Maker 2000 game, brought to a Super Nintendo's
screen and palettes: scaled, toned where the console tones, and down to the
colours they get. It is one stage of a converter —see "One stage of a
converter" in `../battle/README.md`— and it answers with pixels: which
pictures a cartridge carries, and the bytes that carry them, are its
caller's.

    rm2k-snes-images fullscreen --request r.json --out answer/
    rm2k-snes-images picture    --request r.json --out answer/
    rm2k-snes-images background --request r.json --out answer/
    rm2k-snes-images backdrops  --request r.json --out answer/
    rm2k-snes-images battlers   --request r.json --out answer/
    rm2k-snes-images animations --data dump/ --request r.json --out answer/

Each writes `<subcommand>.json` into `--out`; `--help` on each prints the
shape of its request and its answer. Exit code 1 is the answer being no —a
picture that cannot be read, a broken dump—, 2 is the call being wrong.

## The six pictures

* **`fullscreen`**: a picture that fills the screen at 8 bits a pixel —a
  title, a Game Over—, as its distinct 8x8 tiles, their palette and the
  tilemap. Its colours are kept by use, black first, and its indices come
  already shifted to the CGRAM entry they start at.
* **`picture`**: the picture of a `ShowPicture`. RM2k's screen is bigger
  than the console's, and the position is the picture's centre: both
  corners go through the same arithmetic, and the picture is brought to the
  size between them. Fifteen colours, kept by use, for a sprite palette.
  At a zoom, if the request says one, and with its transparent colour at
  index 0; and if it goes with the map, not scaled to the console's
  screen —the map is not—, only zoomed, with its corner relative to its
  centre.
* **`background`**: the picture of a `ShowPicture` too big for the
  sprites, as a 4bpp background layer: drawn where it lands on a canvas
  the width of the screen —taller, if it hangs past the top or the bottom
  and its tiles fit—, its colours brought down by Adeleine into the
  palettes it is given so that each cell draws with one, and cut by
  Voodoo into distinct tiles, mirrored ones reused, and a tilemap.
* **`backdrops`**: a battle's backdrop, in quality —kept by use, from a
  CGRAM entry on— and in the light fallback, a fraction of the size with
  its colours merged by what shows the least.
* **`battlers`**: an enemy's picture, turned by its hue, at the scene's
  scale, cut at half its alpha —a pixel is the battler's or the
  backdrop's— and merged by what shows the least into fifteen colours.
* **`animations`**: a battle animation's frames in the box the console
  draws them in. Each cell is toned with the console's arithmetic, at
  fifteen bits, and stacked over the ones before; the whole animation is
  shrunk until it fits the box and centred in it; a pixel is drawn from
  half its alpha; and the colours are chosen over every frame at once,
  because the palette is uploaded once. The animation is read from the
  dump, by number.

**The sizes come in the request**: the screen, the scene, the box, how
many colours and from which CGRAM entry. They are the cartridge's numbers,
which its caller also writes down for the console, and this way they are
written in one place. **The files come in the request too**: finding a
picture in a game's folder or in the RTP is the caller's.

## To the bit

What RM2k draws is `rm2k-render`'s, used as a library. Everything after it
copies what the converter did until 2026-09-30 in Python, rounding
included, because the point is that a cartridge comes out byte for byte
the same:

* the scaling is Pillow's LANCZOS, from `resample`;
* the cells of an animation are stacked with Pillow's `alpha_composite`
  (`composite.rs`), which computes the alpha of the result too;
* the tone is RM2k's `ToneBlit` at fifteen bits, the same arithmetic the
  console runs on a tinted palette (`tint.rs`);
* the colours are Adeleine's: `keep_most_used` or `merge_least_visible`, and
  for a background layer `reduce_colors` too; its tiles, Voodoo's.

## The tests

`tests/python.rs` converts the small game in `tests/game/` —indexed PNGs
with gradients and noise, a battler and a sheet with their colour key, and
three animations in the dump's shape— and compares each answer, as
canonical JSON, against the sha256 of what the Python gave for it. They
need no game.
