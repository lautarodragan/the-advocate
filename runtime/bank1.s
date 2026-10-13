; ===========================================================================
; The battle, outside bank 0
; ===========================================================================
;
; It is about two kilobytes of code and bank 0 had three hundred bytes left,
; so it went out of bank 0 and is entered with `jsl battle_run`. It lived
; here, in bank 1, until 2026-10-02, when bank 1 filled up too and it moved
; to `FAR2`, the third code bank: see the header of main.s. What that forces
; is in the comment on the `ba_t_*` bridges, in bank 0: from there you cannot
; return with `jsr`, because `jsr` does not change the program bank.
;
; **The data bank is $7E for as long as the battle lasts.** `op_battle` sets
; it before the `jsl` and restores it on return. That is what lets this code
; use absolute addressing on its state: `inc`, `stz`, `ldx` and `cpy` have no
; long mode, so with `f:` each one would have to go through the accumulator.
; And it costs the rest nothing: in bank $7E the addresses from $0000 to $1FFF
; **are** bank 0's low RAM, so `temp`, `comp_*` and `party` read the same as
; always.
;
; What does change are **the ROM tables**, which go with `f:`: the ones here
; because they live in another bank, and the ones in bank 0 —`actor_txt`—
; because with the data bank at $7E their absolute address would land in RAM.
;
; The scratch space, borrowed as in the shop —with the menu open there is no
; message to compose—:
;   ba_diva   is temp        ; the dividend, and then the quotient
;   ba_divb   is temp + 2    ; the divisor
;   ba_divr   is comp_and    ; the remainder
;   ba_mulp   is comp_or23   ; the low partial of the product
; **Everything that follows in `FAR`, up to the header, lives in bank 1 and
; entirely within it.** Inside, they call each other with `jsr`, which does
; not cross banks, and before it had its own segment this went after the generated
; data: it fell in a different bank with each cartridge, and a padding
; computed by eye had to keep the battle from being split. What guarantees it
; fits is checked by `abl/tests/tooling/test_banks.py` in the-advocate-ports, over the
; symbol table.
.segment "FAR"

; --- what does not need to live in bank 0 ----------------------------------
;
; These three are read with `lda f:table, x` —absolute long indexed, which
; adds X over the 24 bits and does not depend on the data bank register—, so
; they can live out here. They cost a byte and a cycle per access, and none of
; the three is in a loop that runs every frame: the PPU registers are written
; once at power-on and `save_table` is walked when saving and loading.
;
; They moved down from bank 0 on 2026-09-13, when `HaltAllMovement` and the
; per-item branch pushed it over by 128 bytes. Bank 0 holds the code and the
; tables that **are** indexed with the data bank at zero; whatever is not,
; does not belong there.

; And since the same day, six more: on 2026-09-13 the `KeyInputProc` that
; waits for the D-pad and the `ChangeEventLocation` by variables overflowed
; bank 0 again, this time by 58 bytes. The six are read with **X**, which is
; the only register the 65816 indexes long with —`long,Y` does not exist—, and
; that is why these moved down and not the route speed ones, which are read
; with Y.
;
; None of them is in a per-frame loop. The hottest is `row_buf_table`, which
; the text composer reads **once per glyph row**: sixteen per letter and only
; while a message window is being built, that is one extra cycle per row on
; top of the hundreds it takes to compose it.

; Which byte of the text buffer each of its sixteen rows starts at. The buffer
; is two cell rows, so row Y falls in tile (Y/8) times 30 columns of 32 bytes,
; plus (Y mod 8) times 2 within the tile.
row_buf_table:
    .word 0, 2, 4, 6, 8, 10, 12, 14
    .word 960, 962, 964, 966, 968, 970, 972, 974

; How far each direction moves, in cells: up, right, down, left, and the four
; diagonals. Signed, which is how `build_*_jump` adds them.
step_dx_table:
    .byte 0, 1, 0, $FF, 1, 1, $FF, $FF
step_dy_table:
    .byte $FF, 0, 1, 0, $FF, 1, 1, $FF

; `step_dx_table`, `step_dy_table` and `step_per_speed` moved down to RODATA on 2026-09-13,
; while resolving the merge of two branches that had each moved tables down on
; their own and still did not fit together: ten bytes were missing. The twelve
; accesses to the first two are with X, which has a long mode; the third has a
; single one and goes through X saving the slot, four bytes against the
; table's twelve.
; How far a step advances per frame by speed, 1 to 6, out of 256 per cell,
; and how far the jump: PASO_POR_VELOCIDAD in events.py and
; `jump_speed[move_speed - 1]` in RM2k. 4 is the hero's: 32 per frame, two
; pixels.
step_per_speed:
    .word 4, 8, 16, 32, 64, 128

; `step_per_speed` moved down to RODATA on 2026-09-13: it has a single access,
; and going through X costs four bytes against the table's twelve.
jump_per_speed:
    .byte 8, 12, 16, 24, 32, 64

; The menu tilemap that goes with the selected option. There is one per
; option and they are contiguous, so which one comes out of a multiplication;
; moving the cursor is uploading the other one and not writing by hand the two
; cells that change, which is the kind of number that gets written right on
; one side and wrong on the other.
;
; It runs with the screen off the first time and inside the vblank the rest:
; it is 2048 bytes per DMA, which fit with room to spare in a vblank that has
; nothing else to do.
; `title_upload_menu` lives in RODATA since 2026-09-14: the demo with a title
; screen overflowed bank 0 by four bytes. It calls no one, so moving it only
; costs the `jsl` of its three callers.
.proc title_upload_menu
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TITLE_MENU_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    ; The source: the start of the block plus 2048 per option.
    lda title_sel
    and #$00FF
    xba                         ; times 256
    asl a
    asl a
    asl a                       ; and times 8: 2048 in total
    sta temp
    lda #<(title_menu_cells)
    ora #(>(title_menu_cells) * 256)
    clc
    adc temp
    ; The sum can overflow the 16 bits of the offset, so the bank is taken
    ; from the carry: the placement in `rm2k-snes/cartridge/src/banks.rs` guarantees
    ; that the block does not cross a bank, not which bank it starts in.
    sta A1T0L
    sep #$20
.a8
    lda #^(title_menu_cells)
    adc #0
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; One bit per position, for the switch bitmap. It comes out cheaper than eight
; shifts and is read with the index we already have.
mask:
    .byte $01,$02,$04,$08,$10,$20,$40,$80

; Which passability is needed to leave a cell and to enter the neighboring
; one, by direction —up, right, down, left—.
;
; The pairs are crossed on purpose: to go up you have to be able to leave the
; source cell through the top and enter the destination cell through the
; bottom. It is RM2k's rule.
pass_exit:
    .byte PASS_UP, PASS_RIGHT, PASS_DOWN, PASS_LEFT
pass_enter:
    .byte PASS_DOWN, PASS_LEFT, PASS_UP, PASS_RIGHT

; The two components of each diagonal, indexed by the direction minus four:
; first the vertical and then the horizontal. From here come the two L shapes
; that `cell_allowed_diag` tests and the two poses `face_diagonal` compares.
; They are RUTA_DIAGONALES in events.py.
diag_vert:
    .byte DIR_UP, DIR_DOWN, DIR_DOWN, DIR_UP
diag_horiz:
    .byte DIR_RIGHT, DIR_RIGHT, DIR_LEFT, DIR_LEFT

; Where the composed glyphs of each phase start, indexed by twice the phase
; —0 to 14—: that is why the banks go with a padding byte between them. See
; `compose_char`. They are read **once per glyph**, not per row. Eight phases
; since the font has variable width: a letter starts at any column of a cell.
font_pre_lo:
    .word .loword(font_pre0), .loword(font_pre1)
    .word .loword(font_pre2), .loword(font_pre3)
    .word .loword(font_pre4), .loword(font_pre5)
    .word .loword(font_pre6), .loword(font_pre7)
font_pre_bk:
    .byte ^font_pre0, 0, ^font_pre1, 0, ^font_pre2, 0, ^font_pre3, 0
    .byte ^font_pre4, 0, ^font_pre5, 0, ^font_pre6, 0, ^font_pre7

; Which JOY1H bit each `KeyInputProc` direction looks at and which number it
; stores in the variable, in the order of `CheckInput` —from highest value to
; lowest—. The same order `events.key_value` walks on the model's side; the
; numbers are emitted by the converter, so they are not written twice.
key_dir_bit:
    .byte PAD_UP, PAD_RIGHT, PAD_LEFT, PAD_DOWN, 0
key_dir_val:
    .byte KEY_VALUE_UP, KEY_VALUE_RIGHT
    .byte KEY_VALUE_LEFT, KEY_VALUE_DOWN

; Adding, removing or enlarging a line changes `SAVE_BYTES`, and with it
; the header: saves made before stop loading, which is what has to happen
; —see `SRAM_BYTES`—. **Reordering two lines without changing the total goes
; unseen**: the header comes out the same and an old save would load shifted.
; The converter's signature does not look at this table, which is hand-written
; source.
save_table:
    .word hero_x, 2
    .word hero_y, 2
    .word hero_dir, 1
    .word tile_x, 2
    .word tile_y, 2
    .word map_current, 2
    .word party, 6              ; the party and how many there are, which are contiguous
    .word tint_r, 3             ; the tint, minus the saturation, which lives far away
    .word tint_s, 1
    .word timer_sec, 5          ; seconds, sub, whether it runs and whether it shows
    .word gold, 3
    .word switches, SWITCH_BYTES
    ; Which song is playing and whether it is muted. An event's `PlayBGM`
    ; turns it on, so it is world state like a switch: without this a loaded
    ; save starts with the song of the ROM's initial map instead of the one
    ; that was playing. They are contiguous in BSS —`music_off` and then
    ; `song_current`— but they are listed separately anyway, because being
    ; adjacent is a detail of the order they were declared in and not a
    ; promise.
    .word music_off, 1
    .word song_current, 2
    ; And the hero's locked facing, as `party_location.lock_facing`, with the
    ; way he last tried to go, which the action key reads while locked. They
    ; go here and not next to `hero_dir` so `SAVE_PARTY` stays put.
    .word hero_lock, 1
    .word hero_heading, 1
    ; And whether he is drawn: `PlayerVisibility` lasts until the next one.
    .word hero_hidden, 1
    ; And the variables, from far RAM. VARIABLES_N is at least 1 —the
    ; converter guarantees it— because a zero length would end the table here.
    .word FAR_VARIABLES, VARIABLES_N * 2
    .word FAR_HERO_SPEED, 1     ; the hero's speed, which routes change
    .word FAR_ITEMS, ITEMS_N    ; the inventory
    .word FAR_ACCESS, 1         ; the save and menu permissions
    .word FAR_MSG_OPTIONS, 1    ; where and how the message window is drawn
    .word FAR_EQUIPMENT, ACTORS_N * 10  ; each actor's equipment
    ; And each actor's HP, which since there are battles is real state.
    .word FAR_HP, ACTORS_N * 2
    ; And the SP, for the same reason since there are skills to spend them.
    .word FAR_SP, ACTORS_N * 2
    ; And which graphic a `ChangeSpriteAssociation` changed the sprite to: one
    ; byte per actor. It travels in the save as in RM2k, and survives teleport.
    .word FAR_ACTOR_GFX, ACTORS_N
    ; And which skills each actor knows: one bit per (actor, skill) pair, which
    ; `ChangeSkills` sets and clears. See `FAR_SKILL`.
    .word FAR_SKILL, SKILL_BYTES
    ; And what the materials added to each actor that can fight: see
    ; `FAR_GROWTH`.
    .word FAR_GROWTH, EXP_K * GROWTH_BYTES
    ; And the panorama: what it scrolled on its own, and how a `ChangePBG`
    ; left it looping and scrolling, which RM2k saves too. Saved in any map
    ; and worth something only in one that shows its panorama, where the
    ; load keeps it: see `PANO_KEEP` in pano.s.
    .word PANO_AX & $FFFF, 4
    .word PANO_FLAGS & $FFFF, 5
.if ::WINDOW_SYSTEMS > 1
    ; And the System the message window is drawn with, which RM2k saves too.
    .word .loword(WINDOW_SYSTEM), 1
.endif
    ; And the experience and level of each actor that can fight. **It goes
    ; last on purpose**: the slot screen reads the leader's level from SRAM
    ; counting from the end of the save —`EXP_LEVEL_IN_SLOT`—, and a line
    ; added after it would shift it.
    .word FAR_EXP, EXP_K * 4
    .word 0, 0

; The four tables that moved down from bank 0 on 2026-09-13, to make room for
; `op_battle`'s Game Over. The three that are indexed are read with
; `lda f:table, x` —absolute long, which does not depend on the data bank— and
; that is why they go with X and not Y: the 65816 has no `long,Y`.
; The fourth was `hdma_mask`, the HDMA table that hides the objects under the
; message window; since the window moves, on 2026-10-04, it is one per
; position, the `mask_*` of message_place.s.

; Which way each pose faces, 0 to 11: the direction is the pose divided by
; three.
pose_dir:
    .byte 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3

ppu_low:
    .byte $00,$00,$00,$00       ; $2101 OBSEL, $2102-3 OAMADD, $2104 OAMDATA
    .byte $00,$00,$00,$00       ; $2105 BGMODE, $2106 MOSAIC, $2107-8 BG1-2SC
    .byte $00,$00,$00,$00       ; $2109-A BG3-4SC, $210B-C BGxNBA
ppu_low_end:

; From $2115 to $2133: VRAM, mode 7, CGRAM, windows, visible layers and color
; math. The three that are not zero are the ones that matter.
ppu_high:
    .byte $80,$00,$00           ; $2115 VMAIN: increment after the high byte
    .byte $00,$00               ; $2118-9 VMDATA
    .byte $00,$00,$00,$00,$00   ; $211A-E mode 7
    .byte $00,$00               ; $211F-20 mode 7
    .byte $00,$00               ; $2121 CGADD, $2122 CGDATA
    .byte $00,$00,$00           ; $2123-5 window selection: window 1 is
                                ; enabled for objects by HDMA, only on the
                                ; lines of the message window
    .byte $00,$FF,$00,$00       ; $2126-9 window positions: window 1 goes
                                ; edge to edge, so it covers every object
    .byte $00,$00               ; $212A-B window logic
    .byte $00,$00               ; $212C TM, $212D TS: no layer visible
    .byte $10,$00               ; $212E TMW: the mask applies to the objects
                                ; of the main screen. $212F TSW
    .byte $30,$00               ; $2130 CGWSEL: color math off. $2131
    .byte $E0,$00               ; $2132 COLDATA: black fixed color. $2133
ppu_high_end:
zero:
    .byte $00,$00

