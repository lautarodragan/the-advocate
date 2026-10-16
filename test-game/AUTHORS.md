# The test game's assets, and whose they are

Every picture in this folder comes from **EasyRPG's RTP**, the free
replacement for RPG Maker 2000's run-time package:
<https://github.com/EasyRPG/RTP>, taken at commit `993d88c`
(2025-04-05). Its materials are licensed under the [Creative Commons
Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
license, some of them dedicated to the public domain under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/); which one each
file has, and its author, is what its `AUTHORS.md` says, copied here for
each file used. The text of CC BY 4.0 is `LICENSE-CC-BY-4.0.txt`, next to
this file: the RTP's `COPYING`, unchanged.

| File | Year | Author | License | Author's page | Changes |
| :- | :- | :- | :- | :- | :- |
| `ChipSet/Exterior.png` | 2022 | Jason Perry | CC0 | <https://finalbossblues.itch.io/> | none: the RTP's file, byte for byte |
| `CharSet/People1.png` | 2023 | VictorSena | CC BY 4.0 | <https://vashmaker.blogspot.com/p/works.html> | none: the RTP's file, byte for byte |
| `FaceSet/Actor1.png` | 2024 | Garakuta | CC0 | <http://garakutamaker.blog.fc2.com/> | none: the RTP's file, byte for byte |
| `System/System.png` | 2011 | andwhyisit | CC BY 4.0, OGA-BY 3.0 | none given | none: the RTP's file, byte for byte |

**The files are not changed; the cartridge does change them.** What the
console cannot show —more colours in the message window than its palette
holds— the converter merges when it builds the ROM, so the System and the
rest are seen in the cartridge with fewer colours than in the file. That is
a conversion the tools make, not an edit of the asset, and the build says
what it merged.

**Why the System is the RTP's and not one of ours.** RPG Maker needs one to
draw any window, and the message the test game's first test reads is in
one. The tools have no System of their own: the one that `rm2k-snes/screens/`
uses in its tests is a few flat colours made by formula, which says nothing
about how a real window converts. The RTP's has a frame, a gradient and
eleven text colours, like a game's.

**What is ours**: everything else in `test-game/` —the game written as text
in `src/`, its tests and their goldens—, like the rest of the repository.
The font the cartridge draws text with is not in here: it is the tools', in
`rm2k-snes/text/`, which says where it comes from (EasyRPG's rmg2000 font
by Zikmok, public domain / CC0; see `rm2k-snes/text/fonts/README.md`).
