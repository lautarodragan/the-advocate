"""That nothing in `tools/` but a comment names something of A Blurred Line.

The tools are for any RPG Maker 2000 game, and since 2026-10-02 A Blurred
Line lives in its own repo. What stayed here are comments that cite it
—limits measured against it, the case that explained a rule—, and those
stay on purpose (`workflow/decisiones/las-herramientas-se-separan-de-abl.md`).
What may not stay is anything else: a test that feeds the compiler one of
its picture names, a fixture with its dialogue, a default that is its
value. Its texts and assets are not ours to carry, and a test that only
passes with its names is a test of that game.

It reads every file under `tools/` that git tracks, takes the comments out
—`;` in assembly, `//` and `/* */` in Rust, `#` and docstrings in Python,
`#` in TOML, the justfile and the rest—, skips the `.md` files, which are
prose, and looks for the words in `WORDS`: its characters, places and
pictures, and its name. A word list does not see everything —a copied
dialogue line with no name in it passes—, but it sees what came copied
until now, and a new copy almost always brings a name with it.
"""

import io
import os
import re
import subprocess
import tokenize

import pytest


# `tools/`, the folder above this one: what these tests look at.
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIS = os.path.relpath(os.path.realpath(__file__), TOOLS)

# Its characters, its places, pictures and sounds of its own —not the
# RTP's—, and its name. Whole words, in any case: the dialogue writes the
# speakers in capitals.
WORDS = [
    # the game
    r"ABL", r"A Blurred Line", r"Blurred",
    # its characters
    r"Talan", r"Kersh", r"Manta", r"Conda", r"Emily", r"Isabella",
    r"Drago", r"Sern", r"Radin", r"Lerle", r"Saldra", r"Sorbe", r"Dalia",
    r"Arden", r"Eisen", r"Pierson", r"AG7(-17)?",
    # its places
    r"Lashe", r"Tasgarde", r"Memnosyne", r"Paradise", r"Catch Colony",
    r"Linkage", r"Lazer Teeth", r"Hover-Trams?", r"Drust", r"Surl",
    r"Garagaraboren", r"Delcentric", r"Murgator", r"Neon Vipers",
    # its pictures, CharSets, ChipSets and sounds
    r"PhoneCallDiff", r"SurlBroDiff", r"SurlGraves", r"ThreeRubble",
    r"GTest4", r"ShipFlash", r"AgentTrain", r"AdvoInstr", r"BLPeople",
    r"BLmouse", r"Future2", r"People3", r"ablskin", r"ABLFaces",
    r"Fortitude",
]

PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(WORDS),
                     re.IGNORECASE)

# What may name the game outside a comment, with its reason: file relative
# to `tools/`.
EXCEPTIONS = {
    # This file, which lists the words.
    THIS,
}

# A line that may, with its reason: (file relative to `tools/`, a piece of
# the line). A piece and not a line number, so that editing above it does
# not move the exception, and editing the line itself does.
LINE_EXCEPTIONS = {
    # Comments the emission writes into the cartridge's `.inc`: comments
    # there, string literals here. What is emitted into the `.inc` is not
    # touched yet (`decisiones/las-herramientas-se-separan-de-abl.md`).
    ("rm2k-snes/mapdata/src/emit/header.rs", '"; Lashe City ran at 30 frames.'),
    ("rm2k-snes/mapdata/src/record.rs",
     '"; fourteen maps and no more: with the whole of Lashe City it is 33"'),
}

# Files that are not text, or that are not ours.
NOT_TEXT = (".png", ".lock")


def _blank(text):
    """The same text with everything but the line breaks turned to spaces, so
    the line numbers do not move."""
    return re.sub(r"[^\n]", " ", text)


def strip_line_comments(source, marker, quotes='"'):
    """Takes out from `marker` to the end of each line, unless it is inside
    a string. Good for assembly (`;`), TOML, the justfile and the like
    (`#`)."""
    out = []
    for line in source.split("\n"):
        inside = None
        cut = len(line)
        k = 0
        while k < len(line):
            c = line[k]
            if inside:
                if c == "\\":
                    k += 1
                elif c == inside:
                    inside = None
            elif c in quotes:
                inside = c
            elif line.startswith(marker, k):
                cut = k
                break
            k += 1
        out.append(line[:cut])
    return "\n".join(out)


def strip_rust(source):
    """Takes out `//` and `/* */` comments —doc comments included—, keeping
    strings, raw strings and char literals."""
    out = []
    k = 0
    n = len(source)
    while k < n:
        c = source[k]
        if source.startswith("//", k):
            end = source.find("\n", k)
            end = n if end < 0 else end
            out.append(_blank(source[k:end]))
            k = end
        elif source.startswith("/*", k):
            depth, j = 1, k + 2
            while j < n and depth:
                if source.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif source.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            out.append(_blank(source[k:j]))
            k = j
        elif (c == "r" and re.match(r'r#*"', source[k:k + 300])
              and not (k and (source[k - 1].isalnum() or source[k - 1] == "_"))):
            hashes = re.match(r'r(#*)"', source[k:]).group(1)
            end = source.find('"' + hashes, k + len(hashes) + 2)
            end = n if end < 0 else end + 1 + len(hashes)
            out.append(source[k:end])
            k = end
        elif c == '"':
            j = k + 1
            while j < n and source[j] != '"':
                j += 2 if source[j] == "\\" else 1
            out.append(source[k:j + 1])
            k = j + 1
        elif c == "'" and (source[k + 1:k + 2] == "\\"
                           or source[k + 2:k + 3] == "'"):
            # A char literal, and not a lifetime.
            j = source.find("'", k + 2)
            out.append(source[k:j + 1])
            k = j + 1
        else:
            out.append(c)
            k += 1
    return "".join(out)


def strip_python(source):
    """Takes out the `#` comments and the docstrings: a string that is a
    statement on its own."""
    lines = source.split("\n")
    spans = []
    previous = tokenize.NEWLINE
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.COMMENT:
            spans.append((tok.start, tok.end))
        elif (tok.type == tokenize.STRING
              and previous in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
                               tokenize.DEDENT)
              and i + 1 < len(tokens)
              and tokens[i + 1].type in (tokenize.NEWLINE,
                                         tokenize.ENDMARKER)):
            spans.append((tok.start, tok.end))
        if tok.type not in (tokenize.COMMENT, tokenize.NL):
            previous = tok.type
    for (r0, c0), (r1, c1) in reversed(spans):
        if r0 == r1:
            line = lines[r0 - 1]
            lines[r0 - 1] = line[:c0] + _blank(line[c0:c1]) + line[c1:]
        else:
            lines[r0 - 1] = lines[r0 - 1][:c0] + _blank(lines[r0 - 1][c0:])
            for r in range(r0, r1 - 1):
                lines[r] = _blank(lines[r])
            lines[r1 - 1] = _blank(lines[r1 - 1][:c1]) + lines[r1 - 1][c1:]
    return "\n".join(lines)


def code(path, source):
    """What of a file is not a comment, with its lines where they were; or
    None if the whole file is prose."""
    name = os.path.basename(path)
    extension = os.path.splitext(name)[1]
    if extension == ".md":
        return None
    if extension == ".rs":
        return strip_rust(source)
    if extension == ".py":
        return strip_python(source)
    if extension in (".s", ".inc"):
        return strip_line_comments(source, ";", quotes="\"'")
    if extension in (".toml", ".ini") or name == "justfile":
        return strip_line_comments(source, "#", quotes="\"'")
    # JSON has no comments, and a patch is somebody else's file, whole.
    return source


def names(path, source):
    """The words of `WORDS` in a file's code, as `line: word`, but for the
    lines in `LINE_EXCEPTIONS`."""
    text = code(path, source)
    if text is None:
        return []
    allowed = [piece for (where, piece) in LINE_EXCEPTIONS if where == path]
    found = []
    for number, line in enumerate(text.split("\n"), 1):
        if any(piece in line for piece in allowed):
            continue
        found += ["%d: %s" % (number, m.group(0))
                  for m in PATTERN.finditer(line)]
    return found


def test_every_line_exception_is_still_there():
    """An exception whose line went away, or changed, is a hole in the net
    that nobody sees."""
    stale = []
    for where, piece in sorted(LINE_EXCEPTIONS):
        with open(os.path.join(TOOLS, where), encoding="utf-8") as f:
            if piece not in f.read():
                stale.append("%s: %s" % (where, piece))
    assert not stale, "these exceptions no longer match a line:\n  " + \
        "\n  ".join(stale)


def _tracked():
    listing = subprocess.run(["git", "ls-files", "-z", "--", "."],
                             cwd=TOOLS, check=True, capture_output=True,
                             text=True).stdout
    for relative in sorted(filter(None, listing.split("\0"))):
        if relative.endswith(NOT_TEXT) or relative in EXCEPTIONS:
            continue
        yield relative


def test_no_tool_names_the_game_outside_a_comment():
    bad = []
    for relative in _tracked():
        with open(os.path.join(TOOLS, relative), encoding="utf-8") as f:
            source = f.read()
        bad += ["%s:%s" % (relative, n) for n in names(relative, source)]
    assert not bad, (
        "these files name A Blurred Line outside a comment: the tools are "
        "for any game. A test uses invented names, and a fixture invented "
        "content; a comment may cite it:\n  " + "\n  ".join(bad))


@pytest.mark.parametrize("path,source", [
    ("a.rs", 'let name = "PhoneCallDiff";\n'),
    ("a.rs", "assert!(!is_speaker(\"KERSH\"));\n"),
    ("a.rs", 'let raw = r#"Lashe City"#; // a comment\n'),
    ("a.py", 'DEFAULT = "A Blurred Line"\n'),
    ("a.s", '.byte "Talan" ; the hero\n'),
    ("a.toml", 'name = "Manta" # who\n'),
    ("justfile", "build:\n  convert --game abl\n"),
    ("a.json", '{"name": "Talan\'s Pad"}\n'),
])
def test_the_net_sees_every_form(path, source):
    assert names(path, source), "%s: %r went unseen" % (path, source)


@pytest.mark.parametrize("path,source", [
    ("a.rs", "// measured against A Blurred Line\nlet x = 1;\n"),
    ("a.rs", "/// The longest name in ABL.\nfn f() {}\n"),
    ("a.rs", "/* Talan */ let x = 1;\n"),
    ("a.rs", "let c = '\"'; // Kersh\nlet s = \"//\"; // Manta\n"),
    ("a.py", '"""Talan."""\nx = 1  # Kersh\n'),
    ("a.py", 'def f():\n    """Measured on A Blurred Line."""\n'),
    ("a.s", "  lda #0 ; Lashe City runs at 30\n"),
    ("a.toml", "# ABL's value\nx = 1\n"),
    ("a.md", "A Blurred Line\n"),
    ("a.rs", 'let word = "Ablative"; let other = "Talanted";\n'),
])
def test_the_net_lets_comments_through(path, source):
    assert not names(path, source), names(path, source)
