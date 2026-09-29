"""RM2k's screen tint applied to a 15-bit color.

It is easyrpg's `ToneBlit` math, brought to the console's five bits per
channel. The ROM does the same math when it uploads the palette.
"""

# The RM2k tint goes from 0 to 200 with 100 as neutral. The ROM stores it as
# is and applies it when uploading the palette.
NEUTRAL_TINT = 100


# RM2k's luminance weights, which are those of Y' in Y'CbCr: the math of
# `saturation_tone` in easyrpg is `(7471*b + 38470*g + 19595*r) >> 16`. They
# add up to exactly 65536, so applied to five-bit channels they give a
# five-bit luminance without rescaling anything.
LUMA_R, LUMA_G, LUMA_B = 19595, 38470, 7471
LUMA_TOTAL = 65536


def luminance(r, g, b):
    """The luminance of a 15-bit color, in five bits."""
    return (LUMA_R * r + LUMA_G * g + LUMA_B * b) // LUMA_TOTAL


def saturate(channel, luma, s):
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
    if s <= NEUTRAL_TINT:
        # An interpolation between gray and the color, with both terms
        # positive: it is the form the 65816 can do unsigned.
        return (luma * (NEUTRAL_TINT - s) + channel * s) // NEUTRAL_TINT
    m = s - NEUTRAL_TINT
    if channel >= luma:
        return min(31, channel + (channel - luma) * m // NEUTRAL_TINT)
    return max(0, channel - (luma - channel) * m // NEUTRAL_TINT)


def tint_channel(channel, value):
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
    if value <= NEUTRAL_TINT:
        return min(31, channel * value // NEUTRAL_TINT)
    return min(31, 31 - (2 * NEUTRAL_TINT - value) * (31 - channel) // NEUTRAL_TINT)


def apply_tint(word, tint):
    """A 15-bit color passed through the screen tint.

    Saturation first and color second, which is the order of `ToneBlit`:
    there `saturation_tone` runs before `color_tone`. Doing it the other way
    around gives something else —the gray would be computed over the already
    tinted color— and it is one of those a golden would not see: it would be
    captured with the bug in place and would defend it.

    The math is done with integers and on the 15 bits, not on the PNG's 24:
    the console has five bits per channel and would round differently.
    """
    channels = [word & 0x1F, (word >> 5) & 0x1F, (word >> 10) & 0x1F]
    if len(tint) > 3 and tint[3] != NEUTRAL_TINT:
        # Only when needed, like easyrpg's `apply_sat`: saturation cannot be
        # done channel by channel —it needs the gray of the whole color— and
        # it is the expensive part of this on the console.
        luma = luminance(*channels)
        channels = [saturate(c, luma, tint[3]) for c in channels]
    out = 0
    for index, (channel, value) in enumerate(zip(channels, tint)):
        out |= tint_channel(channel, value) << (index * 5)
    return out
