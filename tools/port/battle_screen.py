"""The battle's text screen: where each thing goes on it, and the texts the
converter builds for it.

It draws nothing when converting: the ROM composes it one letter per cell
with the text screens' font —see `rm2k-snes-screens`— over a flat color, and
what goes here is the geometry and the texts `mapdata` emits for it. The
math of the battle lives in `battle.py`.
"""

from port import screen_stage


def item_text(text, width):
    """What the text screens' font can write: the characters it has, with a
    '?' instead of the others, and cut to the width. It is the stage's rule
    —`item_text` in its `texts.rs`—, over the same range of characters."""
    layout = screen_stage.layout()
    first, count = layout.ITEM_FIRST_CHAR, layout.ITEM_CHARS
    return "".join(c if first <= ord(c) < first + count else "?"
                   for c in text)[:width]


# --- the battle ----------------------------------------------------------------
#
# `Scene_Battle_Rpg2k`, but **text-only and over a flat color**. taro asked for
# it that way on 2026-09-12, spelled out: *"we can ignore challenges related
# to the background image ... so we can focus on the mechanics of the
# turn-based battle"*. So there is no backdrop, no drawn battlers and no
# windows: the same 32 by 28 cell grid the equipment and shop screens use,
# over black —those, until their windows arrived—.
#
# What **is** RM2k's are the words —all from the LDB, none made up— and the
# math, which lives in `battle.py`.
#
# One thing on this screen is not in RM2k and is a decision:
#
# * **escaping is an actor command** and not a party one. In RM2k "Escape" is
#   in the top menu, before choosing what each one does; putting it in each
#   actor's list saves a whole mode of the machine. Declared.
BA_ENEMY_ROW0 = 0
BA_PARTY_ROW0 = 16
BA_MSG_ROW1 = 24
BA_MSG_ROW2 = 26
BA_CURSOR_COL = 0
BA_NAME_COL = 2
BA_NAME_WIDTH = 14
# **An enemy's HP is not shown**, as in RM2k: its line is just the name.
# With `[debug] enemy_hp` in the project file it comes back, in these same
# columns, for debugging.
BA_HP_COL = 18
BA_HP_NUM = 21                  # three digits
BA_BAR_COL = 24
BA_HP_MAX_NUM = 25              # and the three of the maximum, in the party
# The five commands of ABL's battle menu, on the two message lines: three on
# top and two below. While choosing, the bottom one is free.
#
# Until 2026-09-13 they were three on one line —`Attack`, `Defend`, `Escape`—
# and taro asked for the original's menu, which also has `Use Item` and
# `Tech Skill`. The width is ten because that is the length of the longest
# command: `Tech Skill`, and `AgentTrain`, which is what Kersh's is called.
BA_COMMAND_WIDTH = 10
# **The order is the original's**: Attack, the skill, Defend, Use Item. In a
# capture of the real game, from 2026-09-12, Manta's menu says
# Attack / Slicing / Defend / Use Item. `Escape` is not there —escaping is a
# party command, from another menu— and here it goes fifth; it is the
# simplification `battle.py` declares.
(BA_COMMAND_ATTACK, BA_COMMAND_SKILL, BA_COMMAND_DEFEND, BA_COMMAND_USE,
 BA_COMMAND_ESCAPE) = range(5)
# Per command: which term names it, which line it goes on and in which column.
#
# **The skill's column has to leave ten free cells**: its text is the actor's
# `skill_name`, and `AgentTrain` and `Tech Skill` are exactly ten, leaving no
# room for the next one's cursor —which goes one cell before the text—. That
# is why the top line is 1 / 11 / 22 and not 1 / 11 / 21: the skill goes in
# the middle and Defend starts one cell further. ABL's other four words are
# eight or less.
BA_COMMANDS = (
    ("attack", 0, 1),
    ("skill", 0, 11),
    ("defend", 0, 22),
    ("use", 1, 1),
    ("escape", 1, 13),
)

# No command is unimplemented since 2026-09-13: the skill was the only one and
# now it can be chosen. The tuple stays because the converter checks it and
# because it is where the next half-done one would go.
#
# What does get grayed out is the skill **of an actor that knows none**
# —Talan, who is level 1 and has not learned even the first— just like the
# pause menu with what leads nowhere.
BA_COMMAND_UNDONE = ()

# The skill list, which takes the same lines as the item list and for the same
# reason. It is the original's shape —see the capture
# `capturas-batalla/auto_20260912_123023.png`—: the description of the one the
# cursor marks at the very top, and below two columns with the name on the
# left and the SP cost on the right, with a dash in front.
#
# It reads **by rows**: in the capture, Manta's list sorted by number —130,
# 143, 144, 150— comes out as Mental Hack and MindShield on top and MindProbe
# and MindBlast below.
#
# The description goes on a single line and **is cut at thirty-one
# characters**: the original writes it whole with a smaller font, and here a
# line of text takes two tilemap rows, so the one below is not free. It is
# declared debt.
BA_SKILL_DESC_ROW = 0
BA_SKILL_DESC_COL = 1
BA_SKILL_DESC_WIDTH = 31
BA_SKILL_ROW0 = 2
BA_SKILL_ROWS = 7
BA_SKILL_COLUMNS = 2
BA_SKILL_COLUMN_DX = 16          # from one column to the next
BA_SKILL_NAME_COL = 2           # relative to the start of the column
BA_SKILL_NAME_WIDTH = 11
BA_SKILL_DASH_COL = 13
# The cost goes in **two digits and not three**, which is what lets the two
# columns fit in the 32 cells: the second starts at 16 and its number ends
# exactly at 31. With three it went past the screen. No `sp_cost` in ABL
# reaches 100 —the most expensive of the seven the party knows is 20— and the
# converter **stops if one ever did**, instead of drawing wrong.
BA_SKILL_COST_COL = 14
BA_SKILL_COST_DIGITS = 2

# The item list takes the enemies' lines: while choosing what to use, the
# enemies are not needed and the party is, since it is who gets healed.
BA_ITEM_COUNT_COL = 18

# The `ShowMessage` of a troop page. In RM2k the battle's message window
# **covers the party's**: it is the same 320x80 one as the map's, at the
# bottom, over the status and the commands. Here that is the party's four
# lines, which stop being drawn while the message is on screen; the two lines
# of the battle message are left empty below.
#
# The line is cut at **thirty-one characters**, which is what fits from
# column 1 of this screen's 32; the map window carries thirty-nine. Among
# Talan's systems messages there are lines of up to forty —two techniques in
# one, "     RainDrop...       GatheringWaves...", which already loses the
# last letter in the map window— and those lose their second technique here.
# It is declared debt.
BA_PAGE_MSG_ROW0 = BA_PARTY_ROW0
BA_PAGE_MSG_COL = 1
BA_PAGE_MSG_WIDTH = 31


# What the victory reports goes, as in RM2k, in the message window that covers
# the party: the same four lines of `BA_PAGE_MSG_ROW0`, with its width. The
# first page is the victory term and the experience; each actor that leveled
# up has its own after that.
#
# ABL's victory term does not fit in one line —" The combat has resulted in
# victory!" is 36— so the converter splits it in two, at a space:
# `victory_lines`. The rest is built in the ROM with a number or a
# name in the middle, and what the converter enforces is that it fits.
BA_VICTORY_TERM_MAX = 2


def victory_lines(term, width=BA_PAGE_MSG_WIDTH):
    """The victory term split into lines of `width`, at the spaces. **The
    leading spaces stay**: RM2k writes them, and in this port's map window
    they show too."""
    indent = term[:len(term) - len(term.lstrip(" "))]
    lines, current = [], indent
    for word in term.split():
        empty = not current.strip()
        together = current + word if empty else current + " " + word
        if len(together) <= width:
            current = together
            continue
        if empty:
            raise SystemExit("the victory term has a word longer than the "
                             "line: %r" % word)
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def exp_line(term, exp):
    """RM2k's `GetExperienceGainedMessage` without placeholders: the number
    stuck to the term. The `\\.` easyrpg adds is a wait, not a letter."""
    return "%d%s" % (exp, term["exp_received"])


def level_line(term, name, level):
    """RM2k's `GetLevelUpMessage` in English: "<name> <level> <n><level_up>",
    which in ABL is "Kersh LEVEL 21 achieved!"."""
    return "%s %s %d%s" % (name, term["level"], level, term["level_up"])


def skill_line(term, skill):
    """`GetLearningMessage`: the name stuck to the term."""
    return skill + term["learned"]


def gold_line(term, gold):
    """RM2k's `GetGoldReceivedMessage` without placeholders:
    `gold_recieved_a`, a space, the number stuck to `gold` and
    `gold_recieved_b`. In ABL, " You found 285Cr credits!": the currency and
    "credits" both go, which is what RM2k builds with these terms."""
    return "%s %d%s%s" % (term["gold_a"], gold, term["currency"], term["gold_b"])


def item_line(term, name):
    """RM2k's `GetItemReceivedMessage`: the name stuck to `item_recieved`,
    with no space in between —that one is RM2k3's—. The name is the one the
    ROM carries, cut to `ITEM_NAME_WIDTH`."""
    return item_text(name, screen_stage.layout().ITEM_NAME_WIDTH) \
        + term["obtained"]


def collect_victory(term, exp_max, actors, skills, gold_max=0,
                    items=()):
    """Stops the build if any victory line does not fit in
    `BA_PAGE_MSG_WIDTH`: the ROM builds them by joining pieces and does not
    split them, so a long one would spill onto the line below. Levels are
    measured with two digits, which is RM2k's cap."""
    lines = ([exp_line(term, exp_max)]
             + [gold_line(term, gold_max)]
             + [item_line(term, n) for n in items]
             + [level_line(term, n, 99) for n in actors]
             + [skill_line(term, h) for h in skills])
    lengths = [r for r in lines if len(r) > BA_PAGE_MSG_WIDTH]
    if lengths:
        raise SystemExit("these victory lines do not fit in the window's %d "
                         "characters: %r"
                         % (BA_PAGE_MSG_WIDTH, lengths))


def revived_text(db):
    """What the battle writes after the name of a downed one an item revived:
    the `message_recovery` of state 1, the dead one, which is what
    `BattleMessage::GetStateRecoveryMessage` sticks to the name. In ABL it
    says " has revived!"."""
    from rpgmaker import lcf
    dead = lcf.by_id(db.sections["states"])[1]
    return lcf.field(dead, "message_recovery")


def command_text(term):
    """One of the five commands as the screen writes it.

    The LDB terms carry leading spaces —ABL's `battle_escape` says
    " Escape"— and on the bottom line that would shift the text out of its
    column. It goes here and not in the ROM because the converter emits the
    text **already trimmed**: that way the ROM does not have to know how to
    trim.
    """
    return item_text(term.strip(), BA_COMMAND_WIDTH)


def lcf_term(db, name):
    from rpgmaker import lcf
    return lcf.to_string(db.terms[name])
