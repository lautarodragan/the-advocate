"""What goes at the end of the sprite bank besides the characters, from the
side of the converter.

**The bank is `rm2k-snes-maps`'s** —the timer's digits, the raindrops, the
`ShowPicture` picture and the battle animation box; see `extras.rs` in
`rm2k-snes-map-sprites`—. What stays here is what the emission reads —the
timer's glyphs, where it is drawn, its colors— and whether some page of a
map shows a battle animation, which is the animations' to know and goes to
the stage in its request.
"""

import collections

from port import events
from port import animation as animation_mod


# The timer: eleven 8x16 glyphs of the System, which `rm2k-render system`
# hands over in a row. Ten digits and the colon, which is all
# `Sprite_Timer::Draw` draws.
TIMER_GLYPHS = 11
TIMER_GLYPH_W, TIMER_GLYPH_H = 8, 16
# Where it is drawn on screen. `Sprite_Timer` puts it at `menu_offset_x + 4`
# and `menu_offset_y + 4`, and with a screen narrower than the menu both
# offsets come out zero.
TIMER_X, TIMER_Y = 4, 4


def timer_colors_of(sys_img):
    """The colors the timer's eleven glyphs use.

    It is needed **before** splitting the palettes and not only when packing
    the digits: if a map fills all eight, someone has to be chosen to lose a
    color to make room for it, and that decision changes how that character is
    quantized.
    """
    glyphs = sys_img.timer()
    colors = collections.Counter()
    for i in range(TIMER_GLYPHS):
        for y in range(TIMER_GLYPH_H):
            for x in range(TIMER_GLYPH_W):
                r, g, b, a = glyphs.getpixel((i * TIMER_GLYPH_W + x, y))
                if a:
                    colors[(r >> 3, g >> 3, b >> 3)] += 1
    return colors


def map_shows_animation(game_map, renderer, commands=()):
    """Whether some page of this map can draw a battle animation.

    It is looked at on the raw commands and not on the already compiled
    bytecode, and on purpose: VRAM has to be reserved when converting the map
    and the pages are compiled afterwards. It is a superset —a page that in the
    end doesn't compile leaves 64 tiles reserved and unused— and it has to be:
    if the bytecode showed an animation the map didn't reserve, the ROM would
    write the tiles on top of a character's.

    `commands` are those of the test pages, which don't come from the map.
    """
    numbers = set()
    for cmd in list(commands) + [cmd for event in game_map.events
                                 for page in event.pages
                                 for cmd in page.commands]:
        if (cmd.code == events.SHOW_BATTLE_ANIMATION
                and len(cmd.parameters) >= 3):
            numbers.add(cmd.parameters[0])
    return any(info is not None for info
               in animation_mod.by_numbers(renderer, sorted(numbers)).values())


