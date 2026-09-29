# tools/rpgmaker/

The RPG Maker 2000 game as data: the JSON dump of `rom/data/`, the format's
tables and the RM2k rules the port has to imitate. It is the lowest layer of
`tools/` —see `tools/README.md`—: it imports from no other.

    lcf.py              the game, read from the dump in `rom/data/`
    event_codes.json    generated: the names of the event commands
    event_codes.py      loads it and exposes it as `EVENT_CODES`
    rm2k.py             the original game's rules: passability, autotiles,
                        chipset animation, one-page sprites

## No rule of the format lives here, and that was a decision

`lcf.py` reads `rom/data/`, which since 2026-09-20 is the **resolved view**
Ditto emits: every field written, with its default already applied, and the
enums as numbers. So `field` is three lines and a missing field is a
`KeyError` —which is what we want: it means `rom/data/` is stale, not that
it is zero—.

Until that day `rom/data/` was the exact dump —defaults omitted, enums by
name— and understanding it required, in here, a `ditto_schema.json` with the
defaults and the enum tables, and a `ditto_schema.py` to load it. That was
111 KB of format schema living on the reader's side, and it went away along
with `just esquema` and the test that guarded it. `ditto schema` still exists
on Ditto's side, because the exact dump is still emitted and reading it
needs it; what no longer happens is the port consuming it.

The only thing that is still a judgment call here is **guessing a text's
encoding** —see `lcf.text`—, which is the opposite of a rule of the format:
the format does not say which character set a string is in.

And one more thing, which does not come from `rom/data/`: the 183 cases in
`rom/pruebas/casos/*.json` are written by us, in the shorthand that can be
written by hand —the command by its name and only the fields that say
something—. They are read by `lcf.handwritten_commands`, which is not
`lcf.commands`: the only outside data it uses is `event_codes.json`.

## The event command codes

`event_codes.json` maps number to name —`10110` is `ShowMessage`—, and
`event_codes.py` loads it as `EVENT_CODES`. It was a dictionary written
inside the `.py`; since 2026-09-20 it is a data file, because that is what it
always was: 165 pairs and no logic. It is committed on purpose: that is what
lets building a ROM not require any Rust tool to be installed.

It comes from **liblcf's `Code` enum** —`src/generated/lcf/rpg/eventcommand.h`—
and from nowhere else. All 165 are there, against the 128 in `enums.csv`: the
37 missing from the CSV are the extensions, the `EasyRpg_*` and `Maniac_*`
ones, and even though RPG Maker 2000 never writes them it costs nothing to
have them named.

Where they come from matters because it has already been paid for: the
first version of the filter that decided which commands could accompany a
teleport and still count as a door —a filter that no longer exists, because
doors go through the interpreter like any other event— wrote them from
memory, and **three were wrong** —`PlayBGM` and `ChangeSpriteAssociation`
among them—. No comparison can see that error, because a wrong list
compiles a wrong ROM and the golden is the capture of that ROM.

It is rebuilt when liblcf is bumped, which so far has happened zero times,
so it has no recipe: the whole command is this one, and its output is byte
for byte the committed file.

    python3 - <liblcf clone> > tools/rpgmaker/event_codes.json <<'PY'
    import json, re, sys
    fuente = sys.argv[1] + "/src/generated/lcf/rpg/eventcommand.h"
    cuerpo = re.search(r"enum class Code\s*\{(.*?)\n\s*\};",
                       open(fuente, encoding="utf-8").read(), re.S).group(1)
    codigos = {int(v): n for n, v in
               re.findall(r"(\w+)\s*=\s*(\d+)\s*(?:,|$)", cuerpo, re.M)}
    print(json.dumps({str(c): codigos[c] for c in sorted(codigos)}, indent=2))
    PY

A code the table does not name is printed as a bare number, which is what
it already did.

## `rm2k.py` is what the port has to imitate

Everything else here reads a file; this decides. A cell's passability, how
autotiles expand, how many frames the water takes to advance: they are the
original game's rules, read from EasyRPG, and the ROM reimplements them in
65816. If the two drift apart, the game walks differently.

That is why **what only a test uses does not live here**: `puede_pasar`
—whether a step can be taken from one cell to the next— moved to
`rom/pruebas/arnes/recorrido.py` on 2026-09-20, as it was its only caller.
The direction is for Python to keep what the tests use and for the rest to
go to Rust.
