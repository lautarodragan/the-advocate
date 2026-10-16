; --- an actor's data a variable asks for: what `actor_stat` does not --------
;
; `ControlVars` from an actor, class 5, with `ControlVariables::Actor`'s
; numbers: `actor_stat`, in level.s, answers the HP, the SP and their
; maximums, and sends the other eleven here, which came on 2026-10-16 for
; Zounds —which reads its hero's level and experience every frame— and for
; Vampires Dawn —the level and the spirit—:
;
;   0  the level            `FAR_EXP`'s fourth byte, or the database's for an
;                           actor with no slot, `actor_level`
;   1  the experience       `FAR_EXP`'s three bytes, which reach 999999 where
;                           the variable is a word: past 32767 it answers
;                           32767, the way a constant past the word
;                           saturates —the compiler notes it on the page—.
;                           An actor with no slot has none
;   6 to 9                  attack, defense, spirit and agility: the level's,
;                           `level_param`, plus what each equipped item adds,
;                           clamped to 1..999. It is `eq_parameter` of the
;                           equipment screen without its direct page, which
;                           the message composer may have busy on the map
;   10 to 14                the equipped items, `FAR_EQUIPMENT`'s five words
;
; In `FAR3`: every door in is the `jml` of `actor_stat`, and the only call
; out is `level_param`, in bank 1, with `jsl`.

.pushseg
.segment "FAR3"

; Entered from `actor_stat` with A16 = which minus two: $FFFE the level,
; $FFFF the experience, 4 to 7 the parameters, 8 to 12 the equipment. The
; stack is `actor_stat`'s: the actor, a word, on top of the caller's Y, on
; top of `op_var`'s `jsl` return; all three are undone here. Returns the
; value in A16, with Y as it came. Clobbers X and `temp + 2`, which `op_var`
; only writes after this returns. Every read goes with `f:`: any data bank.
.proc actor_stat_other
.a16
.i16
    ; Unsigned: $FFFE and $FFFF are above everything, so they are asked
    ; for first —the first version compared against 4 and sent them to the
    ; equipment—.
    cmp #$FFFE
    bcc params_or_items
    ; --- the level and the experience: the actor's `FAR_EXP` slot
    tay                         ; $FFFE the level, $FFFF the experience
    lda 1, s                    ; the actor
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    beq no_slot
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax                         ; the slot times four
    cpy #$FFFF
    beq exp
    lda f:FAR_LENGTH + FAR_EXP + 2, x
    xba                         ; the level is the fourth byte
    and #$00FF
    brl done                    ; `brl`: `done` is past the parameters' loop, out of a byte's reach
exp:
    lda f:FAR_LENGTH + FAR_EXP + 2, x
    and #$00FF                  ; the third byte: anything there is past the word
    bne cap
    lda f:FAR_LENGTH + FAR_EXP, x
    bmi cap                     ; bit 15 set is past it too
    brl done
cap:
    lda #$7FFF
    brl done
no_slot:
.a8
    ; An actor who never fights: its database level, and no experience.
    rep #$20
.a16
    lda #0
    cpy #$FFFF
    beq to_done
    lda f:actor_level, x        ; X is still the actor
    and #$00FF
to_done:
    brl done

params_or_items:
    cmp #8
    bcs items
    ; --- attack, defense, spirit and agility: the level's plus the equipment's
    sec
    sbc #4                      ; 0 attack .. 3 agility
    asl a
    pha                         ; its column in `item_points`: stack = column, actor, Y, return
    lsr a
    clc
    adc #2                      ; `level_param`'s Y: 2 attack .. 5 agility
    tay
    lda 3, s                    ; the actor
    sep #$20
.a8
    jsl f:level_param           ; X = the level's value; clobbers A and Y
    rep #$20
.a16
    phx                         ; the sum: stack = sum, column, actor, Y, return
    lda 5, s                    ; the actor
    asl a
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; the actor times ten: its five words of `FAR_EQUIPMENT`
    sta temp + 2
    ldy #5
slot:
    ldx temp + 2
    lda f:FAR_LENGTH + FAR_EQUIPMENT, x
    beq next                    ; nothing equipped
    cmp #ITEMS_N
    bcs next                    ; an item the cartridge does not know
    asl a
    tax
    lda f:item_k, x
    tax
    inc a
    beq next                    ; $FFFF: one the ROM does not know
    txa
    asl a
    asl a
    asl a                       ; eight bytes per item: the four words
    clc
    adc 3, s                    ; plus the column
    tax
    lda f:item_points, x
    clc
    adc 1, s
    sta 1, s
next:
    inc temp + 2
    inc temp + 2
    dey
    bne slot
    pla                         ; the sum
    plx                         ; the column, done with
    ; Clamped as `eq_parameter` clamps it: equipment can subtract, so signed.
    ; The `cmp` is not idle: `plx` left N and Z from the column, and attack's
    ; column is zero —the first version branched on it and every attack came
    ; out as 1—.
    cmp #0
    bmi one
    beq one
    cmp #1000
    bcc done
    lda #999
    bra done
one:
    lda #1
    bra done

items:
    ; --- the equipped item: `FAR_EQUIPMENT`'s word for the actor and the slot
    sec
    sbc #8
    asl a
    sta temp + 2                ; the slot times two
    lda 1, s                    ; the actor
    asl a
    clc
    adc temp + 2
    sta temp + 2                ; the actor times two, plus the slot's
    lda 1, s
    asl a
    asl a
    asl a                       ; the actor times eight
    clc
    adc temp + 2
    tax
    lda f:FAR_LENGTH + FAR_EQUIPMENT, x

done:
    plx                         ; the actor
    ply
    rtl
.endproc

.popseg
