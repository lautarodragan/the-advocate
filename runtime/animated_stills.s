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
; when something else touched one of these rows' pose —`still_dirty`—, and
; it goes straight to the rows it found last time if they are still there.
; A Blurred Line's race (map 49) is at the edge of the frame —45 extra frames
; in 976 ticks driving, with the limit at 48— and its 29 cars animate
; standing still in four groups: walking the forty rows every frame took
; it to 68, measured, and walking them only on the ticks of a change, to 49.
; So each walk leaves in `still_next` the tick on which the soonest column
; changes, and the frames before it cost one subtraction; and in
; `still_hint` where each of its rows was, which the next walk checks by
; the event in +8 before trusting: rows move when a walker is re-sorted
; —`fit_npc`—, and then it walks them all again.
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
    lda #0
    sta still_dirty
    lda #$FF
    sta still_gap
    ; Does this map have any? The padding of the last family in `anim_table`
    ; says how many rows: the walk stops after the last one. A map without
    ; them looks again in 255 ticks, or when it is loaded.
    ldy #(ANIM_FAMILIES - 1)
    jsr anim_where
    lda f:anim_table + 7, x
    bne has
    jmp walked
has:
    sta still_count
    ; Where they were the last time, if they all were in the hints.
    lda still_hints
    beq scan_all
    lda #$FF
    sta still_gap
    ldx #$0000
hinted:
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda still_hint, x
    tay
    sep #$20
.a8
    plx
    lda npc_buf + 13, y
    bpl moved                   ; another row is there now
    lda npc_buf + 8, y
    cmp still_hint_ev, x
    bne moved
    phx
    jsr still_row
    plx
    inx
    txa
    cmp still_hints
    bne hinted
    jmp walked

moved:
    lda #0
    sta still_hints
scan_all:
    lda #$FF
    sta still_gap
    lda still_count
    sta still_rows_left
    lda #0
    sta still_found
    ldy #$0000
    rep #$20
.a16
    ; The rows that do not animate cost the most, so they go at sixteen bits
    ; and without changing width: +13 is the high byte, and its bit 7 the
    ; sign.
scan:
    cpy npc_total
    beq scanned
    lda npc_buf + 12, y
    bmi animates                ; bit 7 of +13 is "still and animating"
    tya
    clc
    adc #NPC_STRIDE
    tay
    bra scan
animates:
    sep #$20
.a8
    ; Where it is, for the next walk, while there is room.
    lda still_found
    cmp #STILL_HINTS
    bcs no_room
    rep #$20
.a16
    and #$00FF
    tax
    asl a
    phx
    tax
    tya
    sta still_hint, x
    plx
    sep #$20
.a8
    lda npc_buf + 8, y
    sta still_hint_ev, x
no_room:
    lda still_found
    inc a
    sta still_found
    jsr still_row
    lda still_rows_left
    dec a
    sta still_rows_left
    beq scanned8                ; that was the last one
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    bra scan
scanned:
    sep #$20
.a8
scanned8:
    ; The hints are good only if they hold every row.
    lda still_found
    cmp #STILL_HINTS + 1
    bcc keep
    lda #0
keep:
    sta still_hints
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
; into `still_gap` if they are fewer. Keeps Y; clobbers A and X.
.proc still_row
.a8
.i16
    lda npc_buf + 13, y
    ; Bit 6: its twins animate in its slot and upload nothing —`moves` in
    ; Wally—, so it uploads even hidden, or erasing it would freeze them.
    bit #$40
    bne shown
    lda npc_buf + 14, y
    bne visible
    rts                         ; hidden: not drawn
visible:
    lda npc_buf + 13, y
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
; a column changes, and walks them all —on a map load the hints are another
; map's—. Clobbers A.
.proc still_touched
.a8
    lda #1
    sta still_dirty
    stz still_hints
    rts
.endproc

; How many rows `animate_still` remembers where they are: more, and it walks
; the table every time.
STILL_HINTS = 8

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
; How many rows animate standing still, from `anim_table`, how many the walk
; has left to find and how many it found.
still_count: .res 1
still_rows_left: .res 1
still_found: .res 1
; Where the rows were the last walk —their offsets in `npc_buf` and their
; events—, and how many: 0 when they have to be looked for.
still_hint: .res 2 * STILL_HINTS
still_hint_ev: .res STILL_HINTS
still_hints: .res 1
.popseg
