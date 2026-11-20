; --- the font's colour -----------------------------------------------------
; The cartridge carries the font once, colour-free —`font_pre0` to
; `font_pre7`, a table per phase, built by `font_prerender` in the screens
; stage—, and each of its writers puts in its colours as it composes a
; letter: the message window (`compose_char_far`, and the gold window's
; digits), the text screens and the slot bank's names (`tl_paint_scr`,
; `tl_paint_slot`), and the debug screen (`tl_glyph_hi`). The ones the game
; waits on are unrolled with the colours as immediates, a routine per
; writer, in `FAR4`; the gold window and the debug screen read them from a
; table, `ink_table`, rolled. Until 2026-11-20 each writer had its
; own table, already coloured for its palette: 364 KB in A Blurred Line,
; three copies of the same letters. See the task
; `the-font-is-precomposed-three-times`.
;
; Per glyph and phase come the FONT_PRE_ROWS rows it touches, and per row
; the two cells it can step on, each with two words: **the pixels it inks**
; —glyph and shadow— and, of those, **the glyph's**, each byte twice. A
; cell it does not touch has its ink word at 0 and is skipped.
;
; The colours are the converter's constants —`MSG_INK_k`, `SCR_INK_k`,
; `SLOT_INK_k` and their `_SHADOW`, the palette index of glyph row k and of
; the shadow— and go into the code as immediates: the macros below choose,
; per row and per pair of planes, the shortest sequence those two colours
; allow. A pair of planes is a word —its low byte one plane, its high byte
; the next— and in it the row's colour and the shadow's are each a mask,
; `ink_planes`: $00, $FF on each byte as the colour's bit is 0 or 1. With K what is kept —the ink word inverted—, G the glyph
; word and SM, CM the shadow's and the row's masks, a pair is
;
;     (buf & K) | (G & CM) | (S & SM)     S = ink & ~G, the shadow's pixels
;   = ((buf ^ SM) & K) ^ ((G & (CM ^ SM)) ^ SM)
;
; which needs neither the shadow's word nor a second mask. Where
; CM ^ SM is 0 the glyph is not read; where it is $FFFF and SM is 0 the
; glyph is ORed straight from the table.
;
; **It is more work per pair than the coloured tables were** —those were a
; read, a mask and a write; this is up to nine instructions—, which the
; unrolling pays back: what each writer's letter costs, before and after,
; is measured in the task.

; The masks of colour COLOR over a pair of planes, 0-1 into LOW and 2-3
; into HIGH. A macro and not a `.define` with arguments: ca65 reads a
; `.define`'s call followed by more of an expression wrongly —the rest goes
; into the argument—, and that is what a mask is always used in.
.macro ink_planes LOW, HIGH, COLOR
    LOW .set (((COLOR) & 1) * $00FF) | ((((COLOR) >> 1) & 1) * $FF00)
    HIGH .set ((((COLOR) >> 2) & 1) * $00FF) | ((((COLOR) >> 3) & 1) * $FF00)
.endmacro

; One pair of planes of one cell row, at `BUF, x`: the row's colour mask CM
; and the shadow's SM, Y on the cell's glyph word, KEEPV holding what is
; kept, INKV what is inked —its inverse—, TV a word it may clobber. A16.
;
; Which of the two it needs and how long it is goes by the two masks:
;
;   SM = 0       (buf & keep) | (G & D)
;   SM = $FFFF   (buf | ink) ^ (G & D)
;   otherwise    ((buf ^ SM) & keep) ^ ((G & D) ^ SM)
;
; with D = CM ^ SM; G & D is the glyph word itself where D is $FFFF, and
; nothing where D is 0.
.macro ink_pair BUF, CM, SM, KEEPV, INKV, TV
.if ((CM) ^ (SM)) <> 0 && ((CM) ^ (SM)) <> $FFFF
    lda [comp_glyph], y
    and #((CM) ^ (SM))
.if (SM) <> 0 && (SM) <> $FFFF
    eor #(SM)
.endif
    sta TV
.elseif ((CM) ^ (SM)) = $FFFF && (SM) <> 0 && (SM) <> $FFFF
    lda [comp_glyph], y
    eor #(SM)
    sta TV
.endif
    lda BUF, x
.if (SM) = $FFFF
    ora INKV
.else
.if (SM) <> 0
    eor #(SM)
.endif
    and KEEPV
.endif
.if ((CM) ^ (SM)) = 0
.if (SM) <> 0 && (SM) <> $FFFF
    eor #(SM)
.endif
.elseif ((CM) ^ (SM)) = $FFFF && ((SM) = 0 || (SM) = $FFFF)
    eor [comp_glyph], y
.else
    eor TV
.endif
    sta BUF, x
.endmacro

; One cell row of a letter: its ink word at IOFS in the letter's data —row
; K's cell D is at K * 8 + D * 4—, its planes 0-1 at `BUF01, x` and 2-3 at
; `BUF23, x`, COL the row's colour and SHD the shadow's. Clobbers Y, KEEPV,
; INKV and TV —only those its colours need—. A16.
.macro ink_cell IOFS, BUF01, BUF23, COL, SHD, KEEPV, INKV, TV
    ink_planes ink_c01, ink_c23, COL
    ink_planes ink_s01, ink_s23, SHD
    ldy #(IOFS)
    lda [comp_glyph], y
    beq :+
.if ink_s01 = $FFFF || ink_s23 = $FFFF
    sta INKV
.endif
.if ink_s01 <> $FFFF || ink_s23 <> $FFFF
    eor #$FFFF
    sta KEEPV
.endif
    iny
    iny
    ink_pair BUF01, ink_c01, ink_s01, KEEPV, INKV, TV
    ink_pair BUF23, ink_c23, ink_s23, KEEPV, INKV, TV
:
.endmacro

; Cell D of row K of a letter for writer P —"MSG", "SCR" or "SLOT"—, with
; that writer's colours: `ink_cell` over the converter's constants.
.macro ink_row_cell P, K, D, BUF01, BUF23, KEEPV, INKV, TV
    ink_c .set ::.ident(.sprintf("%s_INK_%d", P, K))
    ink_s .set ::.ident(.sprintf("%s_INK_SHADOW", P))
    ink_cell (K) * 8 + (D) * 4, BUF01, BUF23, ink_c, ink_s, KEEPV, INKV, TV
.endmacro

; Writer P's colours as data, for the composers that read them instead of
; taking them as immediates —the text layer's `tl_ink_column` and the gold
; window's `gold_cell`—: laid out as the font's letters are, so the index
; that reads a letter's cell reads its colours. At the ink word's place
; CM ^ SM of planes 0-1, at the glyph word's place that of planes 2-3; and
; after the thirteen rows, at FONT_PRE_CHAR, SM of both pairs.
.macro ink_table P
    .repeat FONT_PRE_ROWS, K
        ink_c .set ::.ident(.sprintf("%s_INK_%d", P, K))
        ink_s .set ::.ident(.sprintf("%s_INK_SHADOW", P))
        ink_planes ink_c01, ink_c23, ink_c
        ink_planes ink_s01, ink_s23, ink_s
        .repeat 2
            .word ink_c01 ^ ink_s01, ink_c23 ^ ink_s23
        .endrepeat
    .endrepeat
    .word ink_s01, ink_s23
.endmacro

; The thirteenth row has no glyph, only the shadow of the twelfth: its
; colour is the shadow's, which makes its pairs the cheapest kind.
.assert FONT_PRE_ROWS = 13 && FONT_HEIGHT = 12, error, "the font's rows are not twelve and one of shadow"
MSG_INK_12 = MSG_INK_SHADOW
SCR_INK_12 = SCR_INK_SHADOW
SLOT_INK_12 = SLOT_INK_SHADOW
.assert FONT_PRE_CHAR = FONT_PRE_ROWS * 8, error, "a letter's row is two cells of two words"

; The window's shadow over each pair of planes, for `gold_cell`.
ink_planes MSG_SM01_SET, MSG_SM23_SET, MSG_INK_SHADOW
MSG_SM01 = MSG_SM01_SET
MSG_SM23 = MSG_SM23_SET
