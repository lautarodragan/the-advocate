.segment "CODE"

; --- the still events that animate anyway ---------------------------------
;
; RM2k's `animation_type` 1 and 3 —"Continuous" and "Fixed Dir/Continuous"—
; make the event run through its walk cycle **without moving**. The save point
; in Lashe City is of the second kind, and taro asked for it on 2026-09-07.
;
; The ones that walk already do this: their move route slot carries the counter
; and `.proc animate_ev_route` advances it. The still ones have no slot, and there
; is nowhere to keep a counter for them: the NPC's row has no free byte —+11 is
; the jump height— and the BSS is full. So the column comes from the game
; clock, the same as the ChipSet animation: `ticks` divided by how many
; frames between changes, which is `anim_continues` for the speed, and the
; four-step cycle with the third step repeating the first.
;
; **The phase is not RM2k's**, which starts each character's counter when the
; map creates it; here it is global. It is declared in
; divergences/the-phase-of-still-events-that-animate.md in the book, and all it changes
; is which of the four steps of the cycle each event enters on.
;
; It runs before `move_events` on purpose: if a forced move route grabs one of
; these, the slot overwrites its pose afterwards and wins, since it is the one
; that carries the real counter.
;
; **It walks the rows only on the tick where the next column changes**, or
; when something else touched one of these rows' pose —`still_dirty`—. A
; Blurred Line's race (map 49) is at the edge of the frame —45 extra frames
; in 976 ticks driving, with the limit at 48— and its 29 cars animate
; standing still in four groups: walking the forty rows every frame took
; it to 68, measured, and walking them only on the ticks of a change, to 49.
; So each walk leaves in `still_next` the tick on which the soonest column
; changes, and the frames before it cost one subtraction. Remembering where
; the rows were, to skip the walk, measured the same 49 and was left out.
;
; Whoever writes the pose of a row that may animate here without going
; through this calls `still_touched`, so the next frame walks: a full upload
; queue, the bank uploaded again on a map load or after a battle, the turn
; toward the hero and back, a page that changes the graphic, a route that
; grabs the event and a slot of the cache handed to it. A route that lets go
; of one gives it back its column on the next change.
.proc animate_still
.a8
.i16
    ; The tick being drawn is `ticks + 1` as seen from here, which is the
    ; same number the ChipSet animation looks at —it reads it after the `inc
    ; ticks`—. Measured: without the `inc`, the save point on map 8 stays
    ; one column behind and that is 76 pixels. Without the frozen ticks, like
    ; it: see `frozen_ticks`.
    rep #$20
.a16
    lda ticks
    sec
    sbc f:frozen_ticks
    inc a
    sta still_t
    sec
    sbc still_next
    sep #$20
.a8
    bpl walk                    ; the tick has come, or gone by
    lda still_dirty
    bne walk
    rts
walk:
    stz still_dirty
    lda #$FF
    sta still_gap
    ; Does this map have any? The padding of the last family in `anim_table`
    ; says how many rows: the walk stops after the last one. A map without
    ; them looks again in 255 ticks, or when it is loaded.
    ldy #(ANIM_FAMILIES - 1)
    jsr anim_where
    lda f:anim_table + 7, x
    beq walked
    rep #$20
.a16
    and #$00FF
    sta still_left
    ldy #$0000
    ; The rows that do not animate cost the most, so they go at sixteen bits
    ; and without changing width: +13 is the high byte, and its bit 7 the
    ; sign.
scan:
    cpy npc_total
    beq walked16
    lda npc_buf + 12, y
    bmi animates                ; bit 7 of +13 is "still and animating"
next:
    tya
    clc
    adc #NPC_STRIDE
    tay
    bra scan
animates:
    sep #$20
.a8
    jsr still_row
    rep #$20
.a16
    dec still_left
    bne next
walked16:
    sep #$20
.a8
walked:
    ; The next walk, on the soonest change.
    rep #$20
.a16
    lda still_gap
    and #$00FF
    clc
    adc still_t
    sta still_next
    sep #$20
.a8
    rts
.endproc

; Row Y, which animates standing still: its column for `still_t`, uploaded
; if it is not the one in its slot, and the ticks until it changes again
; into `still_gap` if they are fewer. Keeps Y.
.proc still_row
.a8
.i16
    lda npc_buf + 13, y
    ; Bit 6: its twins animate in its slot and upload nothing —`moves` in
    ; Wally—, so it uploads even hidden, or erasing it would freeze them.
    bit #$40
    bne shown
    ldx npc_buf + 13, y         ; +14 in the high byte: whether it is drawn
    cpx #$0100
    bcs shown
    rts                         ; hidden: not drawn
shown:
    and #$3F
    dec a                       ; the speed, 0 to 5
    phy
    rep #$20
.a16
    and #$00FF
    tax
    lda still_t
    sta WRDIVL                  ; the dividend, in a single 16-bit write
    sep #$20
.a8
    lda anim_continues, x       ; how many frames between column changes
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    ; How many ticks until its column changes: the divisor less the
    ; remainder. The walk keeps the fewest.
    lda anim_continues, x
    sec
    sbc RDMPYL
    cmp still_gap
    bcs later
    sta still_gap
later:
    lda RDDIVL
    and #(WATER_CYCLE_N - 1)
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda cycle_three, x          ; the column: 0, 1, 2 or back to 1
    ply
    sta temp + 3
    ; The pose: where its page faces times three, plus the column. With a
    ; fixed facing —which is what `animation_type` 3 asks for— nobody turns it.
    jsr facing_of_row           ; its page's, or the turn's
    sta temp + 2
    asl a
    clc
    adc temp + 2
    clc
    adc temp + 3
    sty npc_row
    jsr upload_npc_pose
    ldy npc_row
    rts
.endproc

; A row's pose was written by someone other than `animate_still`, and the row
; may animate standing still: the next frame walks the rows, whether or not
; a column changes. Clobbers A.
.proc still_touched
.a8
    lda #1
    sta still_dirty
    rts
.endproc

.pushseg
.segment "BSS"
; The tick `animate_still` draws, without the frozen ones.
still_t: .res 2
; The tick of the next walk, and how many ticks there are to it while
; walking: the soonest change of column.
still_next: .res 2
still_gap: .res 1
; Something other than `animate_still` wrote the pose of a row: walk them
; on the next frame. See the top of this file.
still_dirty: .res 1
; How many rows that animate standing still the walk has left to find, from
; the byte in `anim_table`.
still_left: .res 2
.popseg
