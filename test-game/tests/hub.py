"""The meadow's hub: the guide and the tester, written from `hub.toml`.

They are what makes the test game playable by hand: the guide teleports to
every map, and the tester runs every case of `tester/` from `ShowChoice`
menus, which call each case's page on the shelf. They are the last three
events of `src/maps/Map0001.json`, and this module writes them there —`just hub`, which is `python3 tests/hub.py`—
out of `hub.toml` and `tester/`: a menu of fifty cases nested four options
at a time is not something to keep in step by hand. `test_hub.py` fails if
the map says something else than what this writes.

The tests import it too, to know which options lead where: see `play.py`.
"""

import json
import os
import re
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.join(ROOT, "hub.toml")
TESTER = os.path.join(ROOT, "tester")
MEADOW = os.path.join(ROOT, "src", "maps", "Map0001.json")

# RM2k's `ShowChoice` shows four options at most.
CHOICES = 4
# `ShowChoice`'s first parameter at 5 is the editor's "cancel branch": one
# more `ShowChoiceOption`, with index 4, that only cancel reaches.
CANCEL_BRANCH = 5
MORE = "More"
# The item the guide hands out, whose switch brings the hero back to the
# meadow: `src/db/items.json` and common event 5.
WAY_HOME = 3


def load():
    with open(HUB, "rb") as file:
        return tomllib.load(file)


def case_commands(name, hub=None):
    """A case's commands, as its file in `tester/` has them."""
    hub = hub or load()
    file = hub["tester"].get("case", {}).get(name, {}).get("file", name)
    with open(os.path.join(TESTER, file + ".json")) as f:
        return json.load(f)["event_commands"]


def command(code, indent=0, string=None, parameters=None):
    c = {"code": code}
    if indent:
        c["indent"] = indent
    if string is not None:
        c["string"] = string
    if parameters is not None:
        c["parameters"] = parameters
    return c


def switches(on, off, indent):
    out = [command("ControlSwitches", indent, parameters=[0, s, s, 0]) for s in on]
    out += [command("ControlSwitches", indent, parameters=[0, s, s, 1]) for s in off]
    return out


def menu(options, indent):
    """A `ShowChoice` of `options` —(label, body), where body is a function
    of the indent that gives its commands—, four at a time: past four,
    three and a "More" that opens the rest. Cancel leaves."""
    if len(options) > CHOICES:
        rest = options[CHOICES - 1:]
        options = options[:CHOICES - 1] + [(MORE, lambda i: menu(rest, i))]
    labels = [label for label, _ in options]
    out = [command("ShowChoice", indent, "/".join(labels), [CANCEL_BRANCH])]
    for k, (label, body) in enumerate(options):
        out.append(command("ShowChoiceOption", indent, label, [k]))
        out += body(indent + 1)
        out.append(command("END", indent + 1))
    out.append(command("ShowChoiceOption", indent, "", [CHOICES]))
    out.append(command("END", indent + 1))
    out.append(command("ShowChoiceEnd", indent))
    return out


def paths(options):
    """{label: the options chosen to reach it}, through `menu`'s "More"."""
    out = {}
    page = []
    while True:
        if len(options) > CHOICES:
            shown, options = options[:CHOICES - 1], options[CHOICES - 1:]
        else:
            shown, options = options, []
        for k, label in enumerate(shown):
            out[label] = page + [k]
        if not options:
            return out
        page = page + [CHOICES - 1]


def way_home(indent):
    """The guide's and the tester's first commands: the item that brings the
    hero back, if they do not carry it."""
    return [
        command("ConditionalBranch", indent, parameters=[4, WAY_HOME, 0, 0, 0, 1]),
        command("END", indent + 1),
        command("ElseBranch", indent),
        command("ChangeItems", indent + 1, parameters=[0, 0, WAY_HOME, 0, 1]),
        command("END", indent + 1),
        command("EndBranch", indent),
    ]


def guide_page(hub):
    def going(entry):
        def body(indent):
            return (switches(entry.get("on", []), entry.get("off", []), indent)
                    + [command("Teleport", indent, parameters=entry["to"])])
        return entry["label"], body
    return way_home(0) + menu([going(m) for m in hub["guide"]["map"]], 0)


def offered(hub):
    """The tester's cases, in the order of its menus: the shelf's pages."""
    return [n for g in hub["tester"]["group"] for n in g["cases"]]


def tester_page(hub, shelf):
    """The tester's menus. A case chosen sets its switches and calls its
    page on the shelf, event `shelf`."""
    tester = hub["tester"]
    needs = tester.get("case", {})
    pages = {name: k + 1 for k, name in enumerate(offered(hub))}

    def running(name):
        def body(indent):
            return (switches(needs.get(name, {}).get("on", []),
                             needs.get(name, {}).get("off", []), indent)
                    + [command("CallEvent", indent, parameters=[1, shelf, pages[name]])])
        return name, body

    def group(g):
        return g["label"], lambda indent: menu([running(n) for n in g["cases"]], indent)

    return way_home(0) + menu([group(g) for g in tester["group"]], 0)


def guide_paths(hub=None):
    """{map label: the options to choose on the guide}."""
    hub = hub or load()
    return paths([m["label"] for m in hub["guide"]["map"]])


def tester_paths(hub=None):
    """{case: the options to choose on the tester}: its group's, then its."""
    hub = hub or load()
    groups = hub["tester"]["group"]
    top = paths([g["label"] for g in groups])
    out = {}
    for g in groups:
        for name, inside in paths(g["cases"]).items():
            out[name] = top[g["label"]] + inside
    return out


def event(id, name, spec, commands):
    return {
        "id": id,
        "name": name,
        "x": spec["x"],
        "y": spec["y"],
        # No graphic: the map's tiles draw it. On the hero's layer, which
        # stops them in front of it and answers A from there.
        "pages": [{
            "id": 1,
            "layer": "same",
            "event_commands": commands,
        }],
    }


def events(first_id, hub=None):
    hub = hub or load()
    shelf = first_id + 2
    return [event(first_id, "Guide", hub["guide"], guide_page(hub)),
            event(first_id + 1, "Tester", hub["tester"], tester_page(hub, shelf)),
            shelf_event(shelf, hub)]


# Where the shelf stands: the top left corner's bush, a cell the hero never
# stands on nor faces, so its pages run only when the tester calls them.
SHELF = (0, 0)


def shelf_event(id, hub):
    """Every case of the tester, a page each, in the order of its menus:
    the tester calls the one chosen.

    A page each and not inline in the tester's branches, though a call is
    one more level of the call stack —`nested-calls` goes six deep, of
    eight—: the converter asks which actors can lead a map page by page,
    from the cartridge's party, and the branches of one page it plays in a
    row, as if every case ran after the one before. Inline, `screen-letters`
    puts Zoë first on a party the cases before it had filled, and she was
    not among the meadow's leaders: the hero was not drawn."""
    return {
        "id": id,
        "name": "Shelf",
        "x": SHELF[0],
        "y": SHELF[1],
        "pages": [{"id": k + 1, "event_commands": case_commands(name, hub)}
                  for k, name in enumerate(offered(hub))],
    }


def _format_page(page):
    head = {k: v for k, v in page.items() if k != "event_commands"}
    lines = ["        {"]
    for k, v in head.items():
        lines.append('          %s: %s,' % (json.dumps(k), json.dumps(v, ensure_ascii=False)))
    commands = [json.dumps(c, ensure_ascii=False) for c in page["event_commands"]]
    if commands:
        lines.append('          "event_commands": [')
        lines.append(",\n".join("            " + c for c in commands))
        lines.append("          ]")
    else:
        lines.append('          "event_commands": []')
    lines.append("        }")
    return "\n".join(lines)


def _format(ev):
    """An event in the style the map is written in: one command a line."""
    lines = ["    {"]
    for k in ("id", "name", "x", "y"):
        lines.append('      %s: %s,' % (json.dumps(k), json.dumps(ev[k], ensure_ascii=False)))
    lines.append('      "pages": [')
    lines.append(",\n".join(_format_page(p) for p in ev["pages"]))
    lines.append("      ]")
    lines.append("    }")
    return "\n".join(lines)


# Where the generated events start in the map's text: the guide's.
_GENERATED = re.compile(r',\n    \{\n      "id": \d+,\n      "name": "Guide",')
_END = "\n  ]\n}\n"


def written(text, hub=None):
    """The map's text with the hub's events as `hub.toml` says: the
    hand-written events stay as they are, and the guide and the tester go
    after them."""
    match = _GENERATED.search(text)
    hand = text[:match.start()] if match else text[:-len(_END)]
    assert text.endswith(_END), "the meadow does not end as this expects"
    data = json.loads(hand + _END)
    first = max(e["id"] for e in data["events"]) + 1
    generated = ",\n".join(_format(e) for e in events(first, hub))
    return hand + ",\n" + generated + _END


def main():
    with open(MEADOW) as file:
        text = file.read()
    new = written(text)
    if new != text:
        with open(MEADOW, "w") as file:
            file.write(new)
        print("wrote the hub into %s" % os.path.relpath(MEADOW, ROOT))
    else:
        print("the hub in %s is up to date" % os.path.relpath(MEADOW, ROOT))


if __name__ == "__main__":
    sys.exit(main())
