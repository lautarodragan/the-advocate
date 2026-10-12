.segment "CODE"

; --- the slot screen -------------------------------------------------------
;
; It is used from both ends: "Resume the Story" on the title, and the save
; point in Lashe City. It is a screen of its own and not a layer on top of the
; title, so it **shares the menu's VRAM**: when one is visible the other is
; not, and both are uploaded whole every time they are entered.
;
; All the text comes pre-rendered from the converter, including the two
; variants of each slot —empty and full—. The only thing decided on the fly
; is which block of cells each row gets, and **which block that is is said by
; a table of pointers**, not a multiplication: computing the offset with
; shifts would have put the same computation here and in the converter,
; which is the kind of bug this repo has already paid for three times.
;
; Moving the cursor rewrites **two rows** of 96 cells, not the whole tilemap.

; Whether the slot in A has a save. Returns A nonzero, and **clobbers
; `slot`**: `slots_screen` saves it on entry and restores it on exit.
;
; It looks at the magic and the format —a save from another build looks
; empty, see `slot_of_this_format`— but not at the checksum: it is for
; painting the list, and walking every slot's bytes to draw a screen would be
; overpaying. The checksum is verified by `load_game` when the player
; picks, which is where it matters.
.proc slot_full
.a8
.i16
    jsr set_slot
    jsr slot_bank
    phb
    pha
    plb
    jsr slot_of_this_format
    beq no                      ; the `plb` below clobbers Z: it is checked first
    plb
    lda #$01
    rts
no:
    plb
    lda #$00
    rts
.endproc

; Uploads a block of cells to the tilemap. X carries the block's index in
; `slot_block_lo/hi/bk`, Y the VRAM address in words and `temp` how many
; cells there are.
;
; With the screen off on entry and inside the vblank when moving the cursor:
; 192 bytes by DMA fit with room to spare in a vblank that has nothing else
; to do.
.proc slot_block_upload
.a8
.i16
    sty VMADDL
    lda #$80
    sta VMAIN
    lda f:slot_block_lo, x
    sta A1T0L
    lda f:slot_block_hi, x
    sta A1T0L + 1
    lda f:slot_block_bk, x
    sta A1B0
    rep #$20
.a16
    lda temp
    asl a                       ; cells to bytes
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Paints the row of the slot in A: with the cursor if `title_sel` points at
; it, and full if the SRAM says it is.
;
; Whether it is full is asked again on every repaint instead of being stored:
; it is four bytes of SRAM and it only happens when the cursor moves. Storing
; it would need RAM that is not there —see `slot`— and a way to invalidate
; it after saving.
.proc slot_paint
.a8
.i16
    pha
    jsr slot_full
    asl a                       ; full counts 2 in the variant index
    sta temp + 2
    pla
    pha
    cmp title_sel
    bne no_cursor
    inc temp + 2                ; and the cursor, 1
no_cursor:
    ; The block's index: the two headers first, and then four variants per
    ; slot.
    pla
    pha
    asl a
    asl a
    clc
    adc temp + 2
    clc
    adc #SLOT_BLOCK_ROWS
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; And where it goes, which the table says and not a computation.
    pla
    pha                         ; the slot, for the party afterwards
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per entry
    tay
    lda slot_vram, y
    tay
    lda #SLOT_CELLS
    sta temp
    sep #$20
.a8
    jsr slot_block_upload
    ; And on top of the row, if it has a save, the leader's name and the faces
    ; of the party it saved. `temp + 2` was left with the variant: full is 2
    ; or 3.
    pla
    lda temp + 2
    cmp #2
    bcc no_party
    jmp slot_party_paint
no_party:
    rts
.endproc

; Uploads a rectangle of cells to the tilemap, row by row. X carries the
; block's index in `slot_block_lo/hi/bk`, Y the VRAM address of its first
; cell, `temp` how many bytes each row has and `temp + 2` how many rows there
; are.
;
; **`temp` is one byte**, and the high byte of the DMA size is set to zero
; here: a tilemap row is 32 cells, 64 bytes. Until 2026-09-21 it was read as
; sixteen bits, and the two callers of `menu_party_paint` write only the low
; byte: the high one kept whatever was there, which coming from the item
; screen is the variant of its last letter —`temp + 1`, 1 if it is gray—.
; With a gray item at the end of the list, the panel's first row uploaded 256
; bytes too many over the tilemap: it is taro's "the graphics break when
; entering again". `test_la_eleccion_se_ve_igual_al_volver_a_entrar` catches
; it.
;
; A single source pointer for all rows: the DMA leaves `A1T0` pointing where
; it ended, so the next row starts from there without reloading it. What
; changes per row is the destination, which moves down 32 cells.
.proc slot_rect_upload
.a8
.i16
    lda #$80
    sta VMAIN
    lda f:slot_block_lo, x
    sta A1T0L
    lda f:slot_block_hi, x
    sta A1T0L + 1
    lda f:slot_block_bk, x
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
row:
    sty VMADDL
    lda temp
    sta DAS0L
    stz DAS0L + 1
    rep #$20
.a16
    tya
    clc
    adc #32
    tay
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    dec temp + 2
    bne row
    rts
.endproc

; --- the text that depends on the actor ------------------------------------
;
; The name, the level and the max HP **are not baked** into one block of
; cells per actor: the name is composed —`tl_strip`— and the numbers go one
; letter per cell, with the glyphs in `slot_glyph_cells`. The reason is in
; "what depends on the actor" in the screens stage's `layout.rs`: the tile
; bank is a single one and deduplicated, so a block per actor made it grow
; with every one who could be in the party.

; `msg_ptr` pointing at one of the strips of the actor in A, offset by the X
; bytes of `SLOT_TEXT_NAME`, `_LEVEL` or `_MAX`. Clobbers A and X, and
; **Y stays as it was**: the caller brings it with the cell it is going to
; write to.
;
; It uses `msg_ptr` as the pointer for the same reason as the item screen:
; none of these screens opens with a message on screen, so the composer does
; not have it in use. And it has to be that one or another in the direct
; page, because `lda [dp], y` only addresses there.
.proc slot_text_of
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; SLOT_TEXT_WIDTH bytes per actor
    sta msg_ptr
    txa
    clc
    adc msg_ptr
    clc
    adc #.loword(slot_actor_text)
    sta msg_ptr
    sep #$20
.a8
    lda #^slot_actor_text
    sta msg_ptr + 2
    rts
.endproc

; A text from the slots' bank, one letter per cell: `msg_ptr` the first
; letter, Y the upper cell of the first one and A how many letters. Clobbers
; A, X, `temp` and `temp + 2`, and **leaves Y as it was**: the caller writes
; several strips on the same row by moving it along.
;
; First the upper cells of all the letters, which are contiguous in VRAM and
; make use of the auto-increment, and then the lower ones. It is the item
; screen's `text_write` with the other glyph table: they are two
; different banks and each has its own.
.proc slot_text_write
.a8
.i16
    sta temp                    ; how many letters
    lda #$80
    sta VMAIN
    phy                         ; the cell, for the second pass
    rep #$20
.a16
    lda #0
    sta temp + 2                ; the upper cells
    sty VMADDL
    sep #$20
.a8
    jsr line
    rep #$20
.a16
    lda 1, s                    ; the same cell, since `line` clobbered Y
    clc
    adc #32                     ; and the lower ones, one row down
    sta VMADDL
    lda #2
    sta temp + 2
    sep #$20
.a8
    jsr line
    ply
    rts

line:
    ldy #0
letter:
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_FIRST_CHAR
    asl a
    asl a                       ; four bytes per glyph
    clc
    adc temp + 2                ; the upper or the lower cell
    tax
    lda f:slot_glyph_cells, x
    sta VMDATAL                 ; and VRAM advances one word
    sep #$20
.a8
    iny
    tya                         ; one letter at a time: there are fewer than 256
    cmp temp
    bcc letter
    rts
.endproc

; The party of the save in the slot held in `slot`: the faces of the first
; SLOT_FACES_MAX, and the name of the first one. It is what
; `Window_SaveFile::Refresh` draws per file, minus the hit points, which this
; port does not have.
;
; The party is read from the slot's SRAM, with the data bank at the SRAM's
; just long enough to read one byte: the block tables address bank 0. An actor with no face —DummyHero— draws nothing, which is what
; `DrawFace` does with an empty name. And where each face and each name goes
; is said by two converter tables, `slot_face_vram` and
; `slot_name_vram`, like `slot_vram` for the rows: the computation lives
; on a single side.
;
; The face is a baked block and the name and the level **are not**: the name
; is composed —`tl_slot_name`— and the level goes with glyphs, see
; `slot_text_write`.
;
; The scratch space, which is tight: `temp` and `temp + 2` belong to the
; rectangle, `temp + 3` keeps how many there are, and **`title_edges`
; serves as the member index**. There is no other byte in the direct page,
; and the edges have already been looked at by the time this is reached.
.proc slot_party_paint
.a8
.i16
    jsr slot_bank
    phb
    pha
    plb
    lda SRAM_DATA + SAVE_PARTY_N, x
    plb
    cmp #SLOT_FACES_MAX
    bcc fit
    lda #SLOT_FACES_MAX
fit:
    sta temp + 3
    stz title_edges
other_member:
    lda title_edges
    cmp temp + 3
    bcs faces_ready
    jsr member_actor
    cmp #SLOT_ACTORS_N
    bcs next                    ; an actor this ROM does not know
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:slot_face_block, x
    cmp #$FF
    beq next                    ; no face
    pha                         ; the block, while the destination is built
    ; The table goes four per slot: the slot times four plus the place.
    lda slot
    asl a
    asl a
    ora title_edges
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per entry
    tax
    lda slot_face_vram, x
    tay
    lda #(SLOT_FACE_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #SLOT_FACE_ROWS
    sta temp + 2
    pla
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    jsr slot_rect_upload
next:
    inc title_edges
    bra other_member
faces_ready:
    ; The name of the leader, who is the first, and its level, on top of the
    ; row: the name composed and the level with glyphs. `temp + 3` is no
    ; longer needed, so `slot_text_write` can use `temp`.
    lda temp + 3
    beq ready                   ; an empty party has no leader
    stz title_edges
    jsr member_actor
    cmp #SLOT_ACTORS_N
    bcs ready                   ; an actor this ROM does not know
    pha                         ; the actor, for both strips
    lda slot
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda slot_name_vram, x
    tay                         ; the name's cell
    sep #$20
.a8
    pla
    pha
    ldx #SLOT_TEXT_NAME
    jsr slot_text_of
    lda #SLOT_NAME_COLS
    jsl f:tl_slot_name + FAST   ; composed once, and pointed to again
    ; And the level, which falls a few cells further along the same row. Y
    ; stayed where it was: `tl_slot_name` preserves it.
    rep #$20
.a16
    tya
    clc
    adc #SLOT_LEVEL_OFS
    tay
    sep #$20
.a8
    pla
    jsl f:text_level_saved      ; the one from the slot's save, not the current one
    lda #SLOT_LEVEL_DIGITS
    jsr slot_text_write
ready:
    rts

; The actor in place `title_edges` of the slot's party, read from SRAM.
; Returns A and clobbers X. The offset is the place, built with an `xba` and
; without touching the neighbors in the direct page: reading `title_edges`
; as sixteen bits would take `menu_open` along. The slot is the bank: see
; `slot_bank`, which is not called because it clobbers X.
member_actor:
    lda #0
    xba
    lda title_edges
    tax                         ; with sixteen-bit X, `tax` takes B too
    phb
    lda slot
    clc
    adc #SRAM_BANK
    pha
    plb
    lda SRAM_DATA + SAVE_PARTY, x
    plb
    rts
.endproc

; The whole screen: uploads it, shows it and runs it until the player picks
; or cancels. A carries the mode —0 load, 1 save— and it returns with the
; chosen slot, or **$FF if cancelled with B**.
;
; It leaves VRAM and CGRAM overwritten, so the caller restores its own: the
; title uploads its image and its menu again, and the save point reloads the
; map. It is the same thing `title_screen` does on exit, and for the same
; reason: while this screen is up there is neither map nor title to preserve.
.proc slots_screen
.a8
.i16
    ; The data bank, to 0. **From the title it already is; from the save point
    ; there is no reason it should be**: the interpreter runs with the bank
    ; set to where the event's bytecode lives. And everything below writes the
    ; PPU and DMA registers with absolute addressing, which uses the data
    ; bank, so with the bank shifted the screen was drawn black with garbage
    ; on top.
    phb
    phk
    plb
    ; And the register sizes, explicit. From the title it is reached with
    ; 8-bit A and 16-bit X/Y; **from the interpreter there is no such
    ; promise**, and an `lda #$80` taken as sixteen bits eats the next byte
    ; and throws off everything that follows.
    sep #$20
    rep #$10
    pha                         ; the mode, until the header is drawn
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM                      ; nothing visible while it is built

    jsr slot_bank_upload

    ; --- the header, according to the mode ---
    pla
    pha                         ; the mode, again: it decides where the cursor starts
    rep #$20
.a16
    and #$00FF
    tax                         ; the first two blocks are the headers
    lda #SLOT_HDR_CELLS
    sta temp
    ldy #(SLOT_MAP + SLOT_HDR_VRAM)
    sep #$20
.a8
    jsr slot_block_upload

    ; --- where the cursor starts ---
    ; Loading, on the first. Saving, on the slot in use —the one loaded from,
    ; or the one saved to last time—: it is the `index = latest_slot` of
    ; `Scene_File::Start`, which there is the one with the newest date and
    ; here, with no dates, the one in use. With no save loaded, the first.
    pla
    beq first
    lda slot
    cmp #$FF
    bne starts_there
first:
    lda #0
starts_there:
    sta title_sel

    ; `slot` onto the stack. Painting a row overwrites it —`slot_full`
    ; writes it to address the SRAM— and on exit it has to hold what it held,
    ; whether the player picks or cancels: whoever picks sets it afterwards
    ; with `set_slot`. From the title it did not matter because it held
    ; $FF and was set on picking; from the save point, cancelling would leave
    ; the save of the last painted row as the "loaded" one.
    lda slot
    pha

    ; --- and the four rows ---
    lda #0
paint_all:
    pha
    jsr slot_paint
    pla
    inc a
    cmp #SRAM_SLOTS_N
    bcc paint_all

    jsr slot_ppu_on
    lda #1
    sta menu_open

wait:
    jsr wait_vblank
    jsr read_pad

    lda pad
    eor pad_prev
    and pad
    sta title_edges
    and #PAD_UP
    beq no_up
    lda title_sel
    bne uploads
    ; From the first, up wraps around, but only on a single press: the repeat
    ; stops at the end. It is easyrpg's `Scene_File::Update`, which unlike
    ; `Window_Selectable` asks for `IsTriggered` to wrap around; see
    ; `arrows_repeat`.
    lda arrows_repeated
    and #PAD_UP
    bne wait
    lda #SRAM_SLOTS_N
uploads:
    dec a
    jsr move_cursor
    bra wait
no_up:
    lda title_edges
    and #PAD_DOWN
    beq no_down
    lda title_sel
    inc a
    cmp #SRAM_SLOTS_N
    bcc low
    lda arrows_repeated         ; the same going down: repeating does not wrap
    and #PAD_DOWN
    bne wait
    lda #0
low:
    jsr move_cursor
    bra wait
no_down:
    lda title_edges
    and #PAD_B
    beq check_a
    jsr close
    lda #$FF                    ; cancel
    rts
check_a:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                    ; it was already held: not an edge
    jsr close
    lda title_sel
    rts

; What the two exits have in common: `slot` as it was, the data bank as it
; was, the marker down. And `nmi_seen` up to date, so that `count_lost`
; does not count as lost the frames the player spent choosing: from the save
; point this runs inside one tick of the loop, and without this the tick
; would measure hundreds of frames and saturate the counter.
;
; The stack holds, top to bottom: this `jsr`'s return address, `slot` and
; the bank. The return address is pulled first to get at the other two.
close:
    plx                         ; the return address, set aside
    pla
    sta slot
    plb
    phx
    ; And the B and A edges, consumed: the one that closed the screen belongs
    ; to it. Without this, from the save point, the B for cancelling reached
    ; `request_menu` in the same tick —if the page ended there— and opened the
    ; pause menu; and the A for picking could talk to an event.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    stz menu_open
    lda boot_frames
    sta nmi_seen
    rts

; The cursor to the slot in A: **the two rows that change** are repainted and
; no others. Inside the vblank, which is where we are on leaving
; `wait_vblank`.
move_cursor:
    sta temp + 3                ; the new one
    lda title_sel
    pha                         ; and the old one, onto the stack
    lda temp + 3
    sta title_sel
    pla
    jsr slot_paint              ; the cursor is erased from where it was
    lda title_sel
    jmp slot_paint              ; and painted where it goes
.endproc

; Uploads the tile bank of the slot screen and the menu, blanks the tilemap
; and uploads their colors. With the screen off. It came out of
; `slots_screen` the day the pause menu started using the same bank.
.proc slot_bank_upload
.a8
.i16
    ; --- the tiles ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #SLOT_VRAM
    sta VMADDL
    lda #(SLOT_TILES * 32)
    sta DAS0L
    lda #<(slot_tiles)
    ora #(>(slot_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(slot_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; --- the tilemap, blank ---
    ; A DMA with a **fixed** source address —bit 3 of DMAP— repeating a zero
    ; word. The source is the bank's first tile, which is the transparent one
    ; and therefore 32 bytes of zero: no separate block is needed to have two
    ; zeros at hand.
    rep #$20
.a16
    lda #SLOT_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(slot_tiles)
    ora #(>(slot_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(slot_tiles)
    sta A1B0
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$01
    sta MDMAEN

    ; --- the colors ---
    ; Palette 0 for the text and one per face: SLOT_CGRAM_N entries, in a row.
    stz CGADD
    rep #$20
.a16
    lda #(SLOT_CGRAM_N * 2)
    sta DAS0L
    lda #<(slot_cgram)
    ora #(>(slot_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(slot_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; And the names composed over it start from its first free tile.
    jsl f:tl_strip_reset + FAST
    rts
.endproc

; BG2 with the slot screen's tilemap, and the screen on.
.proc slot_ppu_on
.a8
.i16
    ; --- the PPU ---
    jsl f:pano_mode3            ; the screens draw in mode 3
    lda #(SLOT_MAP / 1024 * 4)
    sta BG2SC
    lda #(SLOT_VRAM / 4096 * 16)
    sta BG12NBA                 ; only BG2; BG1 is not drawn
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    lda #$02
    sta TM
    lda #$0F
    sta INIDISP
    rts
.endproc

