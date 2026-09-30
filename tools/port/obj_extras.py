"""What goes at the end of the sprite bank besides the characters: the timer
digits, the raindrops, the `ShowPicture` picture and the battle animation
box, each with its tiles and the palette it takes; and how many palettes that
leaves for the characters.
"""

import collections

from port import events
from port import animation as animation_mod
from port import picture
from port.adeleine import CELL
from port.snes_format import pack_tile
from port.sprites import OBJ_COLORS, OBJ_PALETTES, drawable_npcs


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


def timer_digits(sys_img, tiles, palettes, leader_owned=(),
                     cap=OBJ_PALETTES):
    """The timer's eleven glyphs, at the end of the sprite bank.

    Each goes as two stacked 8x8 tiles, and all eleven fit in a row of
    sixteen: glyph i takes tile `base + i` and `base + 16 + i`. The base is
    rounded up to a row so that computation holds.

    Returns (tiles, base, palette number). **It doesn't take a palette of its
    own unless needed**: they are two colors —black and pure red— and fit
    easily in that of any character with thirteen or fewer, exactly like the
    events drawn with a chipset tile fit. One is added only if none has room.

    Reserving it up front cost one palette of the eight, and that is not
    bookkeeping: `drawable_npcs` decides with that number **which events are
    drawn**. On 2026-09-07, when building `demo-apertura` with the timer, map 2
    lost two events, and one was the middle one of the door Core breaks: taro
    reached the cutscene, the door didn't change tile and he couldn't get
    through. An event that isn't drawn **still takes space**, so the loss is
    not only visual.
    """
    colors = timer_colors_of(sys_img)
    if len(colors) > OBJ_COLORS:
        raise SystemExit("the timer digits use %d colors and %d fit"
                         % (len(colors), OBJ_COLORS))
    wanted = sorted(colors)
    # The first palette its colors fit in without merging anything. It is the
    # same first-fit as `build_characters` and for the same reason.
    #
    # **Except the leader slots.** The ROM overwrites those with the fifteen
    # colors of whoever is leading every time the party changes or a map
    # loads, so a digit put there would lose its red as soon as Talan hands
    # the lead to Kersh. In the seven maps of `demo-apertura` it doesn't land
    # in any today, which is exactly what made the error invisible.
    for number, existing in enumerate(palettes):
        if number in leader_owned:
            continue
        union = list(existing) + [c for c in wanted if c not in existing]
        if len(union) <= OBJ_COLORS:
            palettes[number] = union
            palette, which = union, number
            break
    else:
        if len(palettes) >= cap:
            raise SystemExit(
                "the timer doesn't fit: the map already uses the %d sprite "
                "palettes it gets and none has room for its %d colors"
                % (cap, len(wanted)))
        palette, which = list(wanted), len(palettes)
        palettes.append(palette)
    index = {color: palette.index(color) + 1 for color in wanted}

    tiles = bytearray(tiles)
    # The base is rounded up to a **row of blocks**, 64 tiles, and not to a
    # grid row: the 4x4 blocks of the last row of blocks take four grid rows,
    # and with the small VRAM image there is since poses go on the fly,
    # rounding to 16 left the glyphs on top of the last row of the hero's
    # block. Nothing showed there until the hero's pose was uploaded and
    # overwrote the 0 and the colon.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + TIMER_GLYPHS) * 32 > len(tiles):
        tiles += bytes((base + 16 + TIMER_GLYPHS) * 32 - len(tiles))
    glyphs = sys_img.timer()
    for i in range(TIMER_GLYPHS):
        for half in (0, 1):
            cell = []
            for y in range(CELL):
                row = []
                for x in range(CELL):
                    r, g, b, a = glyphs.getpixel(
                        (i * TIMER_GLYPH_W + x, half * CELL + y))
                    row.append(index[(r >> 3, g >> 3, b >> 3)] if a else 0)
                cell.append(tuple(row))
            number = base + half * 16 + i
            tiles[number * 32:(number + 1) * 32] = pack_tile(tuple(cell),
                                                             planes=4)
    return bytes(tiles), base, which


def rain_drops(tiles, palettes, leader_owned=(), timer_base=None,
                   cap=OBJ_PALETTES, timer_pal=None):
    """The six raindrop tiles —above and below the streak, in the three
    grays— and the palette their colors go in. See OP_WEATHER in events.py.

    It is the same as `timer_digits`: the colors go in the first
    character palette with room, except the leader ones, and the tiles at the
    end of the bank. If the timer is there, in its same row of sixteen, which
    has five places to spare; if not, in a row of blocks of its own. Tone `t`
    above is tile `base + t` and below `base + 16 + t`. Returns (tiles, base,
    palette number).

    **And not in the timer's either.** The reason was that `upload_timer_pal`
    uploaded that whole palette again **untinted** —the digits go above the
    tint, `Priority_Timer` is 140 and `Priority_Screen` 90—, and a drop put
    there stayed gray on a tinted screen; rain is tinted in RM2k,
    `Priority_Weather` is 80. Since 2026-09-25 it uploads only the digits'
    entries, so a drop wouldn't stay gray anymore, except in a color it shared
    with them. It is still avoided because removing it can move where the
    drops land, and that wasn't measured.
    """
    wanted = [c for c in events.RAIN_COLORS]
    avoid = set(leader_owned)
    if timer_pal is not None:
        avoid.add(timer_pal)
    which = _first_place(palettes, avoid, wanted, cap)
    if which is None:
        # No room: this map doesn't draw rain. Nobody loses a color to make
        # room for it, unlike the timer: that would change the split, and the
        # split is what decides which colors each map has.
        return bytes(tiles), 0, 0
    palette = palettes[which]
    tiles = bytearray(tiles)
    if timer_base:
        base = timer_base + TIMER_GLYPHS
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + 3) * 32 > len(tiles):
        tiles += bytes((base + 16 + 3) * 32 - len(tiles))
    streak = set(events.rain_pixels(0, 0))
    for hue, color in enumerate(wanted):
        index = palette.index(color) + 1
        for half in (0, 1):
            cell = tuple(tuple(index if (x, half * CELL + y) in streak else 0
                               for x in range(CELL)) for y in range(CELL))
            number = base + half * 16 + hue
            tiles[number * 32:(number + 1) * 32] = pack_tile(cell, planes=4)
    return bytes(tiles), base, which


def picture_of_image(info, tiles, palettes, previous_base=None):
    """The `ShowPicture` picture at the end of the sprite bank: its tiles and **a
    whole palette just for it**.

    It shares a palette with nobody, unlike the timer and the drops, and not
    for lack of room: the picture's fade is a tint of its fifteen CGRAM entries
    frame by frame, so a character put in that palette would fade out and back
    in with it.

    And it goes **above `SPRITE_CGRAM`**, that is outside the range
    `apply_tint` and `upload_palettes` walk. That is not shuffling numbers: in
    RM2k pictures have `affected_by_tint` off by default
    —`Priority_PictureOld` is 120 and `Priority_Screen` 90—, so the screen tint
    doesn't touch them. Being outside the range, nobody has to remember to
    skip them.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes: then this map doesn't draw the picture.
    """
    if len(palettes) >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    which = len(palettes)        # the first free one, without adding it to the list
    tiles = bytearray(tiles)
    if previous_base:
        base = -(-(previous_base + 2 * 16) // 64) * 64
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    count = picture.reserved_tiles(info)
    if (base + count) * 32 > len(tiles):
        tiles += bytes((base + count) * 32 - len(tiles))
    for number, cell in picture.cells(info).items():
        tiles[(base + number) * 32:(base + number + 1) * 32] = pack_tile(
            cell, planes=4)
    return bytes(tiles), base, which


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


def map_animation(tiles, palettes, used=0):
    """The battle animation box at the end of the sprite bank: its 64 tiles
    and **a whole palette just for it**.

    It shares a palette with nobody for the same reason as the picture: the
    fifteen colors belong to the animation, are uploaded when it starts and
    overwritten when another starts, and a character put there would change
    color with it. And it goes **above `SPRITE_CGRAM`**, that is outside the
    range `apply_tint` and `upload_palettes` walk, which is also the faithful
    thing: in `Spriteset_Map::Update` the map's tone goes to the tilemap, the
    characters, the panorama and the shadows, and not to the animations.

    The tiles are reserved **blank**: what goes inside is uploaded by the ROM
    via DMA frame by frame, from the cartridge. See `animation.py`.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes. `used` are the ones the picture already
    took.
    """
    which = len(palettes) + used
    if which >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    tiles = bytearray(tiles)
    # After everything else: the timer, the drops and the picture already grew
    # `tiles` to cover theirs, so the end of the bank is the length. Rounded up
    # to a **row of blocks**, which is what the arithmetic of 32x32 objects
    # needs whole.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + animation_mod.TILES) * 32 > len(tiles):
        tiles += bytes((base + animation_mod.TILES) * 32 - len(tiles))
    return bytes(tiles), base, which


def map_palette_cap(renderer, game_map, leaders, graphics,
                    timer_colors, singles, poses, sample_animation):
    """How many sprite palettes this map can split among its characters: all
    eight, or **seven** if it shows battle animations.

    The animation box needs a whole palette just for it, and the two maps of
    the intro —2 and 3, which are the ones the scene uses— filled all eight.
    Taking one away from the characters is what gives the Emitter Room scene
    its drawing; what it costs is merged colors, and each map's report says so.

    **Unless the timer doesn't fit with seven**, which is not negotiable:
    without its two colors there is no timer in the whole ROM. Then it goes
    back to eight and this map doesn't draw animations, which is what happens
    to map 9.

    It lives on its own and not inside `convert_map` because it is a split
    decision and not a detail of `convert_map`.
    """
    if not sample_animation:
        return OBJ_PALETTES
    minus = OBJ_PALETTES - 1
    if timer_colors:
        split = drawable_npcs(renderer, game_map, leaders, minus, graphics,
                              timer_colors, singles, poses)[2]
        clone = [list(p) for p in split[0]]
        if _first_place(clone, split[3], list(timer_colors),
                        minus) is None:
            return OBJ_PALETTES
    return minus


def _first_place(palettes, leader_owned, colors, cap=OBJ_PALETTES):
    """The first palette —except the leader ones— where `colors` fit without
    merging anything, or a new one if a slot is left; it adds or grows it and
    returns its number, or None if there is no room.

    `cap` is how many sprite palettes this map can use, which **isn't always
    all eight**: a map that shows battle animations reserves one for the
    animation box, and neither the timer nor the drops can take it. See
    `palette_cap` in `convert_map`.
    """
    for number, existing in enumerate(palettes):
        if number in leader_owned:
            continue
        union = list(existing) + [c for c in colors if c not in existing]
        if len(union) <= OBJ_COLORS:
            palettes[number] = union
            return number
    if len(palettes) < cap:
        palettes.append(list(colors))
        return len(palettes) - 1
    return None
