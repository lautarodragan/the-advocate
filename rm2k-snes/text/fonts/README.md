# The fonts the engine carries

A font is **a sheet**: an indexed PNG with the 95 printable ASCII characters,
from the space to the `~`, each in its cell. It is the font's source of
truth: it is edited by hand, and nothing else needs to change. A game names
one of these in its project file —`[text] font = "low-variable"`— or the
path of a sheet of its own, relative to the project file; or `rm2k`, which
is RPG Maker 2000's own six-pixel font, the one the game's `font_id` picks.

| sheet              | cell | what it is |
|--------------------|------|------------|
| `low-variable.png` | 8    | Variable width, for the console's 256 pixels: each glyph cut to its ink plus one pixel of air, and of two equal inner columns only one is kept —the "o" and the "n" go from 5 to 4—, which is what Final Fantasy VI and Chrono Trigger do. The digits and the slash by hand, 4 of ink, all 5 of advance. Derived once from RM2k's Mincho by rules, on 2026-09-30: a starting point, not a design. |

**Where the font comes from, and its license.** `low-variable.png` descends
from EasyRPG's `rmg2000` font ("basic halfwidth 6x12 font compatible with Don
Miguel's RMG2000", designed by Zikmok (rohkea) for the EasyRPG project in
2017, partially based on Shinonome), which is in the public domain, or CC0
where that is not possible; the sheet this one was cut from matches it glyph
for glyph. No attribution is required, and we give it anyway. The research
is in the task `the-console-fonts-origin-and-license` of the-advocate-work.

## The shape of a sheet

Sixteen cells per row, six rows, with a one-pixel grid line between cells
and around them. Each cell is `w` columns wide —8 for the console's low
resolution— and 13 rows tall:

* **rows 0 to 11, the glyph**, on RM2k's baseline: capitals go from row 1 to
  row 9, and what hangs down, to row 11;
* **row 12, the advance**: as many marks, stuck to the left, as columns the
  line moves after the glyph. **The air between letters goes in the advance,
  not in the glyph**: a letter of 4 columns of ink with one of air carries 5
  marks. A mark with a gap is refused.

What counts is the **index**, not the colour, so the palette can be changed
to see better:

| index | colour (as shipped) | what it is |
|-------|---------------------|------------|
| 0     | black               | the background |
| 1     | white               | the glyph |
| 2     | red                 | the advance mark |
| 3     | grey-blue           | the grid: ignored |

**The shadow is not drawn**: it is added when the line is drawn, one pixel
to the right and one down, as RM2k does. That is why a letter's air is also
where its shadow falls: the ink of a glyph has to end at least one column
before its advance, so that the shadow does not land on the next letter.

The console's composer takes glyphs of at most **8 columns of ink**: with
the shadow, from any of a cell's eight columns, they touch two cells and no
more. A wider one stops the conversion.

The digits are **all the same width**, so that numbers line up in columns as
in RM2k; touching one means touching the advance of all ten.

## Editing it

In Aseprite: open the PNG, which comes in indexed mode, and draw with index
1. The sheet's grid is part of the picture; Aseprite's can be set the same
(*View > Grid Settings*: 9x14, origin 0,0). Save as PNG, without converting
to RGB.

To try more air between the letters without touching the sheet, a game
sets `[text] letter_spacing` in its project file: pixels added to every
advance, the space and the digits included, from 0 to 3, and no letter
may end up moving the line further than a cell (8). It is a knob to try
how a font reads; a font that wants more air for good carries it in its
advance row.

To try a retouch in a game without reinstalling the tools, copy the sheet
into the game, point `[text] font` at the copy and rebuild: the cartridges
are rebuilt when the sheet changes. When it is done, bring it back here.
