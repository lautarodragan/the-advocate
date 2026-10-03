.segment "CODE"

; --- the text screens -----------------------------------------------------------
;
; The items, equipment, shop and battle screens are pure text over their
; windows. What they write goes through these, which since 2026-10-03 hand it
; to the text layer —`text_layer.s`—: each write is a run of letters of the
; variable-width font that starts at a cell, and each row is composed into
; tiles of its own when what it says changes. The screens stage's `render`
; is the reference.
;
; A position is still a byte of the 32 by 28 cell tilemap, `pick_table`: row *
; 64 + column * 2. It is where a run starts, not where each letter goes.
;
; The scratch space is borrowed variables: the message composer's, `comp_*`,
; which are recomputed with each character, and with the menu open there is
; no message; and `pick_table`, which is the position being written to.
SCR_BYTES = 32 * 28 * 2
;   scr_value    is comp_dup       ; the number being written, two bytes
;   scr_width    is comp_dup + 2   ; in how many digits
;   scr_cap      is comp_dup + 3   ; how many cells a text may take, 255 any

; Every row empty, to be written again: only the rows whose text changed get
; composed again.
.proc scr_clear
.a8
.i16
    jsl f:tl_clear + FAST
    rts
.endproc

; In the vblank: the tiles of the row composed last and the tilemap, 1792
; bytes in one DMA. The rows are composed while `wait_vblank` waits —see
; `tl_idle`—, except right after a screen opens, with the screen off: then
; all of them, here.
.proc scr_upload
.a8
.i16
    jsl f:tl_vblank + FAST
    jsl f:tl_map + FAST
    jsl f:tl_work + FAST
    rts
.endproc

; One letter: A the character, `temp + 1` the colour —0 white, 1 gray, 2 the
; "goes up" one and 3 red: see `ITEM_UP` in `rm2k-snes-screens`—. It goes at
; `pick_table`, which advances one cell; a letter written where the previous
; write ended goes right after it. Clobbers X and Y.
.proc scr_glyph
.a8
.i16
    jsl f:tl_letter + FAST
    rts
.endproc

; A text: X its number —see `item_txt_*`—, at `pick_table` and with the
; colour in `temp + 1`, and no wider than `scr_cap` cells.
.proc scr_text
.a8
.i16
    jsl f:tl_text + FAST
    rts
.endproc

; A number from `scr_value`, 0 to 999, in `scr_width` places —2 or 3—, at
; `pick_table` and with the colour in `temp + 1`.
.proc scr_number
.a8
.i16
    jsl f:tl_number + FAST
    rts
.endproc
