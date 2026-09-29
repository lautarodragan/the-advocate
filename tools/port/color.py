"""RM2k's screen tint applied to a 15-bit color.

It is easyrpg's `ToneBlit` math, brought to the console's five bits per
channel. The ROM does the same math when it uploads the palette.
"""

# The RM2k tint goes from 0 to 200 with 100 as neutral. The ROM stores it as
# is and applies it when uploading the palette.
TINTE_NEUTRO = 100


# RM2k's luminance weights, which are those of Y' in Y'CbCr: the math of
# `saturation_tone` in easyrpg is `(7471*b + 38470*g + 19595*r) >> 16`. They
# add up to exactly 65536, so applied to five-bit channels they give a
# five-bit luminance without rescaling anything.
LUZ_R, LUZ_G, LUZ_B = 19595, 38470, 7471
LUZ_TOTAL = 65536


def luminancia(r, g, b):
    """The luminance of a 15-bit color, in five bits."""
    return (LUZ_R * r + LUZ_G * g + LUZ_B * b) // LUZ_TOTAL


def saturar(canal, luz, s):
    """A channel moved toward or away from gray, with `s` in RM2k units.

    It is easyrpg's `saturation_tone` brought to five bits and to RM2k's
    units instead of its own. There the factor is
    `sat = gray > 128 ? 1024 + (gray - 128) * 16 : gray * 8` over 1024, with
    `gray = s * 128 / 100`; working it out, that is `s / 100` for `s <= 100`
    and `(2s - 100) / 100` for `s > 100`. So 0 takes everything to gray, 100
    does nothing, and 200 triples the distance to gray.

    The above-100 case is done with the sign split off and truncating,
    instead of with easyrpg's arithmetic shift, which rounds down with
    negative numbers too. The difference is one step out of 31 and only when
    oversaturating; doing it signed on the 65816 would cost quite a lot more
    than that.
    """
    if s <= TINTE_NEUTRO:
        # An interpolation between gray and the color, with both terms
        # positive: it is the form the 65816 can do unsigned.
        return (luz * (TINTE_NEUTRO - s) + canal * s) // TINTE_NEUTRO
    m = s - TINTE_NEUTRO
    if canal >= luz:
        return min(31, canal + (canal - luz) * m // TINTE_NEUTRO)
    return max(0, canal - (luz - canal) * m // TINTE_NEUTRO)


def tenir_canal(canal, valor):
    """A five-bit channel passed through RM2k's tint, which is a hard light.

    RM2k does not scale the channel: it composites it with a *hard light*
    —`hard_light.table` in easyrpg, which is `2ab` for the lower half and the
    screen `1-2(1-a)(1-b)` for the upper one—. In RM2k units, with 100
    neutral, that is:

        valor <= 100:  canal * valor / 100
        valor  > 100:  31 - (200 - valor) * (31 - canal) / 100

    The first half is exactly what this repo had been doing, and that is why
    the tints that darken do not change. The second one was not.
    `canal * valor / 100` with valor up to 200 multiplies by two and clamps,
    and that **is not** what RM2k does: the difference reaches 31 out of 31
    at valor 200, that is, the whole screen. Nobody caught it because no page
    that compiled used a brightening tint; the two that saturation unlocks
    —maps 229 and 230— do, with (0, 120, 120).

    Measured against easyrpg's math over eight bits, this version differs by
    **one step out of 31 at most**, for every tint the game uses. It is the
    same tolerance the lower half already had, and it comes from RM2k doing
    the math in eight bits while the console has five.
    """
    if valor <= TINTE_NEUTRO:
        return min(31, canal * valor // TINTE_NEUTRO)
    return min(31, 31 - (2 * TINTE_NEUTRO - valor) * (31 - canal) // TINTE_NEUTRO)


def tenir(palabra, tinte):
    """A 15-bit color passed through the screen tint.

    Saturation first and color second, which is the order of `ToneBlit`:
    there `saturation_tone` runs before `color_tone`. Doing it the other way
    around gives something else —the gray would be computed over the already
    tinted color— and it is one of those a golden would not see: it would be
    captured with the bug in place and would defend it.

    The math is done with integers and on the 15 bits, not on the PNG's 24:
    the console has five bits per channel and would round differently.
    """
    canales = [palabra & 0x1F, (palabra >> 5) & 0x1F, (palabra >> 10) & 0x1F]
    if len(tinte) > 3 and tinte[3] != TINTE_NEUTRO:
        # Only when needed, like easyrpg's `apply_sat`: saturation cannot be
        # done channel by channel —it needs the gray of the whole color— and
        # it is the expensive part of this on the console.
        luz = luminancia(*canales)
        canales = [saturar(c, luz, tinte[3]) for c in canales]
    salida = 0
    for numero, (canal, valor) in enumerate(zip(canales, tinte)):
        salida |= tenir_canal(canal, valor) << (numero * 5)
    return salida
