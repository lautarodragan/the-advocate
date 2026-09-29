r"""Text boxes reflowed for the SNES width.

RM2k has no auto-wrap: every break in a `ShowMessage` was put there by hand
by the author, thinking of a 320 px window. The one here is narrower
—`constants.COLUMNS` characters per line—, and until this, whatever did
not fit was truncated.

`refit` takes the lines of **one** box, exactly as they are in
`rom/data/`, and returns one or more boxes that fit. It is a pure function:
the same box always gives the same result, and that is what allows applying
it on every build instead of storing its output.

The rules, and where each one comes from:

* **A box that fits is returned as is**, with its breaks and its spaces.
  Most fit, and that way they keep everything the author decided.
* **The speaker's line is not touched** —`KERSH`, `MANTA`, `?????`— and the
  body has one line less.
* **An original break is a good place to cut, not a mandatory one.**
  Treating it as mandatory left a word alone on a line ("it still /
  is.") and made more boxes not fit.
* **A line that splits a sentence goes full**; one with whole sentences may
  be short. What taro does not want to see is a line that stops long before
  the edge —"Remember," alone, and the rest below—, and that happens when
  cutting at a period comes out cheaper than filling.
* **What does not fit in one box is split into several**, cutting between
  sentences when possible, and **each one repeats the speaker's line.** It
  is what the game does: measured on 2026-09-24, of the consecutive boxes
  of the same character none fails to repeat the name, and the author
  himself splits a sentence that way —`MANTA` / "...up to the Emitter Room
  -" and `MANTA` / "- where the Link is projected!"—.
* **The escape tail** —`\|` and `\^`, see `events.escape_tail`— goes at
  the end of the last box, which is where the player saw it.

What is lost in a reflowed box are the extra spaces between words: the words
are joined again with one. In one that fits, nothing is lost.
"""

import re

from port import events
from port import constants

# An end of sentence, with the quotes or parenthesis that close it: cutting
# there is free. `...` matches through the period.
SENTENCE_END = re.compile(r"""[.!?]["')]*$""")
# A minor pause: cutting there costs little.
PAUSE = re.compile(r"""[,;:\-]["')]*$""")

# The costs. They are taste and not a measurement: with other values the same
# box comes out differently. The first ones were tried on the introduction and
# Lashe City on 2026-09-24; those of the gap, the tail and the extra box came
# out the same day from what taro played up to the Back Alleys, comparing
# against the previous version on every box of the game.
#
# Cutting a line after a word:
COST_SENTENCE_END = 0
COST_PAUSE = 15
COST_ANYWHERE = 40
DISCOUNT_ORIGINAL_BREAK = 10   # where the author cut
COST_ORPHAN = 200            # a lone word on the last line
# Between a proper name and its number —"Sector / 33."—. It is almost
# forbidden: it costs more than an extra box.
COST_BEFORE_NUMBER = 1000

# The gap a line that is not the last one leaves. How much it weighs depends
# on where it cuts, and that is the rule that most changes what is seen: **a
# line that splits a sentence has to go full.** One with whole sentences may
# be short —"Time is running out." / "There's no turning back."—, because it
# reads as a break the author intended. With a single weight for all, cutting
# at an end of sentence was so cheap against the gap that the reflow left
# "Remember," or "Well," alone on a line so that the ones below would end in
# a period: that is what taro complained about.
WEIGHT_GAP = 20                 # whole sentences: the gap squared / 20
WEIGHT_GAP_PAUSE = 8            # cuts at a comma: squared / 8
WEIGHT_GAP_SPLIT = 1000       # splits a sentence: cubed, relative to the width

# The piece of sentence left on the other side of a cut —"sure." at the start
# of a line, "There" at the end—, if it is shorter than this. It is the
# generalized orphan: "in time?" alone below looks as cut off as "Well," above.
TAIL_MIN = 16
WEIGHT_TAIL = 3                   # what it is short of, squared / 3

# An extra box is an extra key press for the player. If the nicest layout
# does not fit in one box but there is one that fits and costs at most this
# much more, the one that fits wins.
COST_EXTRA_BOX = 300


def width(text):
    """How many columns it takes: one character, one column. The font is
    fixed-width, and the only escapes that compile go in the tail, outside
    of this."""
    return len(text)


# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
def is_speaker(line):
    """Whether the line names the speaker: all caps, short, and with no
    sentence punctuation at the end.

    `?????` is the odd case that has to match —the game uses it while it is
    not known who is speaking—, so a question mark at the end only counts if
    there is nothing but question marks. "WHAT?" is a shouted sentence, not
    a name.
    """
    text = line.strip()
    if not text or len(text) > 20 or text != text.upper():
        return False
    if set(text) == {"?"}:
        return True
    return not text.endswith((".", "!", "?", ","))


def fits(lines, columns=constants.COLUMNS, rows=constants.LINES):
    """Whether the box is fully visible, not counting its escape tail."""
    untailed, _pauses, _auto_close = events.escape_tail(lines)
    return (len(untailed) <= rows
            and all(width(t) <= columns for t in untailed))


def _tail(lines):
    """The box's escape tail, exactly as written, and the lines without
    it."""
    untailed, _pauses, _auto_close = events.escape_tail(lines)
    untailed = list(untailed)
    if not untailed:
        return untailed, ""
    return untailed, lines[-1][len(untailed[-1]):]


def _words(rows, columns):
    """The words of the body, and after which of them the author cut.

    A word wider than a line is split by force: there is no other way to
    show it.
    """
    words = []
    cuts = set()
    for row in rows:
        for word in row.split():
            while width(word) > columns:
                words.append(word[:columns])
                word = word[columns:]
            words.append(word)
        if words:
            cuts.add(len(words) - 1)
    return words, cuts


def _cut_cost(words, cuts, i):
    word = words[i]
    if SENTENCE_END.search(word):
        cost = COST_SENTENCE_END
    elif PAUSE.search(word):
        cost = COST_PAUSE
    else:
        cost = COST_ANYWHERE
    if i in cuts:
        cost -= DISCOUNT_ORIGINAL_BREAK
    if (word[:1].isupper() and word[-1:].isalpha()
            and i + 1 < len(words) and words[i + 1][:1].isdigit()):
        cost += COST_BEFORE_NUMBER
    return cost


def _line_cost(words, cuts, i, j, columns):
    """What a line with the words from `i` to `j` costs: its gap, the cut it
    ends with and the pieces of sentence it leaves loose.

    The last line does not pay for its gap —it ends where the text ends—,
    but it does pay for being left with a single word or with a short piece
    of the sentence above.
    """
    n = len(words)
    length = width(" ".join(words[i:j]))
    ends = [k for k in range(i, j) if SENTENCE_END.search(words[k])]
    starts_sentence = i == 0 or SENTENCE_END.search(words[i - 1])
    cost = 0
    # The end of a sentence that started on the line above.
    if not starts_sentence and (j == n or (ends and ends[0] < j - 1)):
        last = ends[0] + 1 if ends else j
        cost += _fragment_cost(words[i:last])
    if j == n:
        if j - i == 1 and i > 0:
            cost += COST_ORPHAN
        return cost
    # The start of a sentence that continues on the line below.
    if not SENTENCE_END.search(words[j - 1]) and ends:
        cost += _fragment_cost(words[ends[-1] + 1:j])
    gap = columns - length
    if SENTENCE_END.search(words[j - 1]) and starts_sentence:
        cost += gap * gap / WEIGHT_GAP
    elif PAUSE.search(words[j - 1]):
        cost += gap * gap / WEIGHT_GAP_PAUSE
    else:
        cost += WEIGHT_GAP_SPLIT * (gap / columns) ** 3
    return cost + _cut_cost(words, cuts, j - 1)


def _fragment_cost(words):
    """A piece of sentence separated from the rest by a line break."""
    missing = max(0, TAIL_MIN - width(" ".join(words)))
    return missing * missing / WEIGHT_TAIL


def _rows(words, cuts, columns, limit=None):
    """The words in lines, choosing the cuts that cost the least.

    It is TeX's paragraph algorithm in miniature: dynamic programming over
    where each line ends, keeping count of how many there are so far.
    """
    n = len(words)
    if n == 0:
        return []
    # mejor[j][k]: the cost of putting the first j words in k lines, and
    # where the last one starts.
    best = [dict() for _ in range(n + 1)]
    best[0][0] = (0, None)
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            row = " ".join(words[i:j])
            if width(row) > columns:
                break
            if not best[i]:
                continue
            own = _line_cost(words, cuts, i, j, columns)
            for k, (before, _first) in best[i].items():
                cost = before + own
                # `<` and not `<=`: on a tie the longest line wins, which is
                # the one found first. It is what makes it deterministic.
                if k + 1 not in best[j] or cost < best[j][k + 1][0]:
                    best[j][k + 1] = (cost, i)
    options = sorted(best[n].items(), key=lambda kv: (kv[1][0], kv[0]))
    chosen = options[0][0]
    if limit is not None and chosen > limit:
        # The nicest layout does not fit in one box. If there is one that
        # fits and is not much worse, that one is used: an extra box is an
        # extra key press.
        fit = [kv for kv in options if kv[0] <= limit]
        if fit and fit[0][1][0] < options[0][1][0] + COST_EXTRA_BOX:
            chosen = fit[0][0]
    out = []
    j, k = n, chosen
    while j > 0:
        i = best[j][k][1]
        out.append(" ".join(words[i:j]))
        j, k = i, k - 1
    return out[::-1]


def _stretches(words, cuts, columns, body):
    """The words spread over as many boxes as needed.

    Each box is filled with whole sentences while they fit. A sentence that
    does not fit in a box on its own is split by lines.
    """
    sentences = []
    first = 0
    for i, word in enumerate(words):
        if SENTENCE_END.search(word) or i == len(words) - 1:
            sentences.append((first, i + 1))
            first = i + 1

    def lines_of(a, b):
        local_ones = {c - a for c in cuts if a <= c < b}
        return _rows(words[a:b], local_ones, columns, body)

    stretches = []
    start = end = 0
    for a, b in sentences:
        if len(lines_of(start, b)) <= body:
            end = b
            continue
        if end > start:
            stretches.append(lines_of(start, end))
            start = end = a
        if len(lines_of(a, b)) <= body:
            end = b
            continue
        # The sentence alone does not fit in a box: it is spread by lines.
        every = lines_of(a, b)
        for k in range(0, len(every) - body, body):
            stretches.append(every[k:k + body])
        rest = every[(len(every) - 1) // body * body:]
        start = b - len(" ".join(rest).split())
        end = b
    if end > start:
        stretches.append(lines_of(start, end))
    return stretches


def refit(lines, columns=constants.COLUMNS,
          rows=constants.LINES):
    """The boxes that replace this one, each a list of lines.

    Returns `[lineas]` untouched if the box already fits, or if it carries an
    escape that does not compile —`events.CannotCompile`—: that page does not
    reach the ROM, so there is nothing to arrange.

    It is memoized by text: the math is pure, and a map is loaded several
    times per conversion —each time with all its boxes— so most calls repeat
    an earlier one. A copy is returned, because some callers add lines to
    what they receive.
    """
    key = (tuple(lines), columns, rows)
    if key not in _refit_cache:
        _refit_cache[key] = _refit(list(lines), columns, rows)
    return [list(frame) for frame in _refit_cache[key]]


_refit_cache = {}


def _refit(lines, columns, rows):
    try:
        if fits(lines, columns, rows):
            return [lines]
        untailed, tail = _tail(lines)
    except events.CannotCompile:
        return [lines]

    head = []
    if len(untailed) > 1 and is_speaker(untailed[0]):
        head = [untailed[0]]
        untailed = untailed[1:]
    body = rows - len(head)

    words, cuts = _words(untailed, columns)
    stretches = _stretches(words, cuts, columns, body) or [[]]
    frames = [head + stretch for stretch in stretches]
    if not frames[-1]:
        frames[-1].append("")
    frames[-1][-1] += tail
    return frames


def refit_commands(commands, columns=constants.COLUMNS,
                   rows=constants.LINES):
    """A list of commands from `rom/data/` —dictionaries, as they are in the
    JSON— with each text box reflowed.

    A `ShowMessage` with its `ShowMessage_2`s is replaced by one or more
    boxes in the same format, with the same `indent`. What is not text, and
    the boxes that already fit, come out as **the same objects**: whoever
    compares with `is` knows what changed.
    """
    out = []
    i = 0
    while i < len(commands):
        command = commands[i]
        if command["code"] != events.SHOW_MESSAGE:
            out.append(command)
            i += 1
            continue
        j = i + 1
        while j < len(commands) and commands[j]["code"] == events.SHOW_MESSAGE_2:
            j += 1
        originals = commands[i:j]
        lines = [c["string"] for c in originals]
        frames = refit(lines, columns, rows)
        if frames == [lines]:
            out.extend(originals)
        else:
            for frame in frames:
                for k, text in enumerate(frame):
                    out.append({
                        "code": (events.SHOW_MESSAGE if k == 0
                                 else events.SHOW_MESSAGE_2),
                        "indent": command["indent"],
                        "parameters": [],
                        "string": text,
                    })
        i = j
    return out
