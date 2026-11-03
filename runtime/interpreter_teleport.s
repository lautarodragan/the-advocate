.segment "CODE"
.a8
.i16

; --- the interpreter: teleport ---------------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps
; to each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

.proc op_teleport
.ifdef TELEPORT_FACING
    ; A `Teleport` that keeps the facing writes so, and does not leave the
    ; byte as it finds it: a jump replaces the one pending in the frame,
    ; facing and all, which is `ReserveTeleport`'s.
    lda #0
facing:
    sta jump_facing
.endif
    rep #$20
.a16
    lda [code_ptr], y           ; the map, as a word since the format has
    sta jump_map                ; to be able to name all 328 in the game
    iny
    iny
    lda [code_ptr], y
    sta jump_x
    iny
    iny
    lda [code_ptr], y
    sta jump_y
    sep #$20
.a8
    iny                         ; the two bytes of the Y, which were read
    iny                         ; without advancing the cursor
jump:
    lda #1
    sta jump_has
    ; **A parallel goes on to its next command, in this same frame**: the
    ; `if (!main_flag) return true;` of the same easyrpg function, "parallel
    ; events should keep on running in 2k and 2k3". The jump is taken at the
    ; end of the frame —`events_handle_jump` in the main loop—, and what the
    ; page did until then stays done. Zounds' guard scene on map 7 is a
    ; parallel that tints the screen black, jumps and tints it back: ending
    ; the frame here, the map load threw its cursor away with the tint back
    ; still to run, and the next map stayed black (2026-10-16). Map events
    ; and parallel common events alike (`pair_ev` below `PAIR_BATTLE`); the
    ; foreground, $FF, and a troop page, `PAIR_BATTLE`, end the frame.
    lda pair_ev
    cmp #PAIR_BATTLE
    bcs ends_the_frame
    jmp run_code::other
ends_the_frame:
    ; And it ends the frame, which is exactly what
    ; `Game_Interpreter_Map::CommandTeleport` does in easyrpg-player: it queues
    ; the transfer, does `index++` and returns false. The map loads between
    ; this frame and the next, and the page resumes at the command after this
    ; one with the cursor saved here. No page in the game that compiles today
    ; has commands after a teleport —measured over the whole game—; the
    ; opening cutscene has eleven.
    sty ev_cur
    rts
.endproc

.ifdef TELEPORT_FACING
; RPG Maker 2003's `Teleport` with a facing: the direction, plus one, to
; `jump_facing` —zero there is keeping it—, and the rest is `op_teleport`'s,
; with Y already on the map. It is not turned here but on the black frame the
; hero is placed in: see `teleport_face`.
.proc op_teleport_facing
    lda [code_ptr], y
    iny
    inc a
    jmp op_teleport::facing
.endproc

.pushseg
.segment "BSS"
; The facing the pending jump leaves the hero with, plus one, or zero to keep
; his: `jump_map`'s, which has no room left in the direct page for it.
jump_facing: .res 1
.popseg

.pushseg
.segment "FAR"
; The facing a `Teleport` asked for, on the black frame the hero is placed
; in, from `load_requested`: after the erase, as `Game_Player::
; PerformTeleport` does, so the turn does not show on the map being left.
; Its `SetDirection`, which is `hero_heading`, always; its `UpdateFacing`,
; which is `hero_dir`, not over `hero_lock` —the same as a jump's turn in
; oam.s—.
.proc teleport_face
.a8
.i16
    lda jump_facing
    beq keep
    stz jump_facing
    dec a
    sta hero_heading
    lda hero_lock
    bne keep
    lda hero_heading
    sta hero_dir
keep:
    rtl
.endproc
.popseg
.else
; Without a `Teleport` that asks for a facing in the cartridge —every RM2k
; game's— the compiler never emits it, and it ends the page like a number
; that is not an opcode: the cartridge only pays for its entry in the
; dispatch.
op_teleport_facing = page_ends
.endif


; `MemorizeLocation` and `RecallToLocation`: like `op_heal`, only the entry
; point. The body is `remembered_place`, outside bank 0, and it returns with
; carry set if there is a transfer to do, with the destination already in
; `jump_*`: the transfer finishes here, like the one in `op_teleport`.
.proc op_location
    jsl f:remembered_place
    bcs jump
    jmp run_code::other
jump:
    jmp op_teleport::jump

.endproc
