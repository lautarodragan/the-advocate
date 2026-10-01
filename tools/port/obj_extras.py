"""What goes at the end of the sprite bank besides the characters, from the
side of the converter.

**The bank is `wally`'s** —the timer's digits, the raindrops, the
`ShowPicture` picture and the battle animation box; see `extras.rs` in
`rm2k-snes-map-sprites`—, and so are the timer's colors and which entries
of its palette they take, which the emission reads back; where the timer is
drawn is the emission's, `engine.rs` in `rm2k-snes-mapdata`. What stays here
is whether some page of a map shows a battle animation, which is the
animations' to know and goes to the stage in its request.
"""

from port import events
from port import animation as animation_mod


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


