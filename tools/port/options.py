"""The converter's command line: its flags, and the ROM's maps in table
order, which is the first thing everything else asks of them.
"""

import argparse
import os

from common import project
from common import environment


def map_order(args):
    """The ROM's maps, in table order and without repeats.

    It is in a function and not written three times because **the order is
    the contract**: a compiled teleport stores the index in this table, not
    the RM2k id. Two lists built differently would take the same bytecode to
    different maps.
    """
    return [args.map_id] + [m for m in (args.maps or []) if m != args.map_id]


def flags_parser():
    """The converter's flags. Separate from `main` for whoever needs to read a
    command line without converting anything."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Mandatory, but without `required`: `test_cases` reads the flags of
    # each `--case` again with this same parser, and there it doesn't go.
    # `main` enforces it.
    parser.add_argument("--map-id", type=int, default=None,
                        help="the boot map, which goes first in the "
                             "table. Mandatory and with no default: it "
                             "belongs to the game, and its project file "
                             "declares it")
    project.add_argument(parser)
    # No default, and no `required` for the same reason as `--map-id`:
    # `environment` enforces them when they are read.
    environment.add_arguments(parser, "game_dir", "rtp_dir", "soundfont",
                              "cache")
    parser.add_argument("-o", "--output",
                        default=os.path.join(project.build(), "inc", "mapdata.inc"))
    parser.add_argument("--msu",
                        help="where to write the .msu with the data the\n"
                             "MSU-1 serves to the ROM: next to the .sfc and\n"
                             "with its name, so the emulator finds it.\n"
                             "Without this, datos.msu next to --output")
    parser.add_argument("--text-padding", type=int, default=0,
                        help="dead texts after the item ones, so that\n"
                             "the battle's indices go past 255 without\n"
                             "building a twenty-nine-map cartridge. It\n"
                             "doesn't change a pixel, and that is why they\n"
                             "don't go first: item k's name is text 3k")
    parser.add_argument("--no-title", action="store_true",
                        help="without the game's title screen and its "
                             "start and load menu: the ROM boots straight "
                             "into the map. It is what the regression "
                             "suite's cartridges ask for: the title screen "
                             "would add frames to the boot, and the cases "
                             "compare frames counted from reset.")
    parser.add_argument("--measure-headroom", type=float, metavar="HEADROOM",
                        help="the same headroom for every song, instead of "
                             "the volume ceiling table: it is what "
                             "`rm2k-snes-volume-ceilings` builds the ROM where "
                             "it measures each song's peak with. It goes to "
                             "`rm2k-snes-audio` as the job's "
                             "`measuring_headroom`")
    parser.add_argument("--enemy-hp", action="store_true",
                        help="the battle shows the enemies' HP, which RM2k "
                             "never shows: for debugging. It is asked for by "
                             "`[debug] enemy_hp` of the project file")
    parser.add_argument("--no-speed-keys", action="store_true",
                        help="L and R do not change the hero's speed. "
                             "They are a port addition, not RM2k's: without "
                             "them the hero walks exactly at the speed the "
                             "game gives him")
    parser.add_argument("--no-timer", action="store_true",
                        help="the timer digits —eleven glyphs of the System "
                             "image at the end of the sprite bank, which "
                             "share a palette with a character— only in the "
                             "maps where a case that uses them runs, and not "
                             "in all. It is what the suite's cartridges ask "
                             "for: see `args.timer_en`")
    parser.add_argument("--test-graphic", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDEX"),
                        help="puts this graphic in the sprite bank of the\n"
                             "maps where some case runs, so that the test\n"
                             "page can change someone's graphic with\n"
                             "command 34 or with ChangeSpriteAssociation.\n"
                             "It can be repeated. No page that compiles\n"
                             "today changes graphic, so without this\n"
                             "nothing runs that path")
    parser.add_argument("--test-encounters", type=int, default=None,
                        metavar="STEPS",
                        help="every how many steps there is a random "
                             "encounter, for every map of the cartridge. "
                             "Without this the game tree's value applies, "
                             "which goes from 25 to 85 steps; 0 turns them off")
    parser.add_argument("--hero-above", action="store_true",
                        help="the hero at object priority 2, above the "
                             "layer that should cover it. It is the only "
                             "way to exercise it: the game's only above "
                             "event never gets to step on the upper layer")
    parser.add_argument("--party", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="the party it starts with, by actor ids. The "
                             "hero's graphic is the first one's, which is how "
                             "RM2k decides it. By default, the database's: "
                             "this game starts with actor 10, DummyHero, whose "
                             "sprite is an empty cell on purpose")
    parser.add_argument("--test-commands", default=None,
                        metavar="FILE",
                        help="this case's test page, as the command list of "
                             "an RM2k page in Ditto's JSON —see "
                             "rom/pruebas/casos/—. It is compiled by the same "
                             "path as a page of the game, with the context of "
                             "the map where it runs: that of its Teleport if "
                             "it starts with one, and otherwise the boot "
                             "map's")
    parser.add_argument("--charset", default=None,
                        help="force the hero's CharSet; by default it comes "
                             "from the party's first, which is how RM2k "
                             "decides it")
    parser.add_argument("--charset-index", type=int, default=None,
                        help="which of the CharSet's 8 characters")
    parser.add_argument("--maps", nargs="+", type=int, metavar="ID",
                        help="other maps to put in the same ROM. The one "
                             "from --map-id goes first in the table")
    parser.add_argument("--start-index", type=int, default=0, metavar="N",
                        help="which table index the ROM boots at. It serves "
                             "to test a map other than the first, which is "
                             "the only case where the record's offset isn't "
                             "zero")
    return parser
