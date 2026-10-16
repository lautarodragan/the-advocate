"""`ControlVars` from an actor: the level, the experience, a parameter with
the equipment and the equipped items, which the ROM answers since
2026-10-16 —`actor_stat_other`, in `runtime/actor_stats.s`—. Until then
only the HP, the SP and their maximums compiled, and Zounds' common event 3,
which reads its hero's level and experience every frame, was left out.

The case `actor-stats` gives the Hero 84 experience —his curve is the
database's default, base 30 and inflation 30: 30 to reach level 2 and 84 to
reach level 3, RM2k's `CalculateExp`—, puts the Sword in his hand —+5
attack, +7 defense, +9 spirit and +11 agility over curves of zeros, which
the ROM clamps to 1 before adding— and reads:

    variable 20  his level            3       switch 1300
    variable 21  his experience       84      switch 1301
    variable 22  his attack           6       switch 1302
    variable 23  his weapon           1       switch 1303
    variable 24  his shield           0       switch 1304
    variable 25  Bram's level         7       switch 1305
    variable 26  his defense          8       switch 1306
    variable 27  his spirit           10      switch 1308
    variable 28  his agility          12      switch 1309

Bram, actor 3, is in no party and never fights, so he has no experience
slot: his level is the database's, `actor_level`. Then 40,000 more
experience, and the variable takes 32767 (switch 1307): the word
saturates, which the compiler notes as a degradation.

Before the change the `ControlVars` with 0, 1, 6 to 11 did not compile,
and with them neither did the case nor the cartridge: red by construction.
And the first version of the ROM side answered 1 for the attack: a `plx`
left the flags of the column it pulled, which is zero for the attack, and
the clamp branched on them —the trap of AGENTS.md—; this is the case that
caught it.
"""

from game import Session

CASE = "actor-stats"
EXPECTED = {
    1300: "the Hero's level is not 3",
    1301: "the Hero's experience is not 84",
    1302: "the Hero's attack with the Sword is not 6",
    1303: "the Hero's weapon is not the Sword",
    1304: "the Hero's shield is not empty",
    1305: "Bram's level, with no experience slot, is not the database's 7",
    1306: "the Hero's defense with the Sword is not 8",
    1307: "the experience past the word did not saturate at 32767",
    1308: "the Hero's spirit with the Sword is not 10",
    1309: "the Hero's agility with the Sword is not 12",
}


def test_an_actors_stats_into_variables(core):
    sess = Session(core, case=CASE)
    for _ in range(30):
        sess.advance()
    wrong = [why for switch, why in EXPECTED.items() if not sess.switch(switch)]
    assert not wrong, "; ".join(wrong)
