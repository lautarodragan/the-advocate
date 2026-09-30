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
