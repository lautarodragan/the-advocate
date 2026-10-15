.segment "FAR"

; --- the party in the shop -----------------------------------------------------
;
; `Window_ShopParty`: in every mode of the buy layer, each party member's
; CharSet facing down and walking —frames 0, 1, 2, 1, twelve frames each—,
; still and in grey whoever cannot equip the item the cursor marks, and next
; to each one the System's arrow that says whether the item raises or lowers
; their parameters: `party.rs` in `rm2k-snes-screens` is the reference, and
; `TI_PARTY_*` its geometry.
;
; **They are objects**, 8x8: a member is twelve, three across by four down, and
; its arrow one more. The object base is the windows' —`TI_BORDER_VRAM`, which
; is a multiple of $2000— and the tiles go right after the windows', so all of
; it falls in what `load_map` restores. Each member slot has the twelve tiles
; of the frame it shows, and a new frame is uploaded over them; the System's
; sixteen arrows are all up. The OAM is written once, at opening, with the
; screen off: member `i` in entries `12 i` to `12 i + 11` with palette `i`,
; and the arrows in 48 to 51 with palette 4. After that only the arrows'
; four entries change, and the grey is the member's palette swapped for its
; grey one —`ti_party_cgram` brings both—.
;
; What changes goes up in the vblank, after the text's tilemap and pairs and
; before the text is typeset, **only if the line leaves room**: the windows
; and the text can take the vblank almost whole —see `ti_windows`—, and
; something that falls out of it is lost. What did not fit goes up the next
; frame, so a member can step a frame or two late after a key; the frame each
; one has up is `TI_P_UP`, and the arrows' phase `TI_P_SHOWN`, which is what
; the tests read.
;
; What a member is drawn with is the database's CharSet: a
; `ChangeSpriteAssociation` is not followed —the graphic it names is an index
; into the map's table, not the cartridge's—. And `IsEquippable`'s
; "two-weapon actors cannot hold a shield" is not looked at: no actor table
; of the cartridge carries `two_weapon`.
;
; Its state borrows the battle's, after the shop's list: a shop opens from a
; map page and no battle is alive while it is open.
TI_P = FAR_SHOP + 2 * SHOP_MAX + 1
TI_P_ON = TI_P                  ; whether the layer shows the party
TI_P_N = TI_P + 1               ; how many members it shows, four at most
TI_P_SUB = TI_P + 2             ; frames into the step, 0 to TI_PARTY_RATE - 1
TI_P_PHASE = TI_P + 3           ; the step, 0 to 3
TI_P_SHOWN = TI_P + 4           ; the step the arrows were last written with
TI_P_I = TI_P + 5               ; the member being looked at
TI_P_ITEM = TI_P + 6            ; two bytes: the item, $FFFF none computed yet
TI_P_ITEMK = TI_P + 8           ; two bytes: its `k`
TI_P_OLD = TI_P + 10            ; two bytes: the four parameters as they are
TI_P_NEW = TI_P + 12            ; two bytes: and with the item on
TI_P_K = TI_P + 14              ; four: each member's graphic, $FF none
TI_P_USABLE = TI_P + 18         ; four: whether it can equip the item
TI_P_KIND = TI_P + 22           ; four: its arrow, $FF none
TI_P_UP = TI_P + 26             ; four: the frame its slot has, $FF unknown
TI_P_PAL = TI_P + 30            ; four: 0 colour, 1 grey, $FF unknown
TI_P_FORCE = TI_P + 34          ; the screen is off: everything goes up
TI_P_FRAME = TI_P + 35          ; the frame or palette being uploaded
TI_P_T = TI_P + 36              ; two bytes of scratch
TI_P_T2 = TI_P + 38             ; and two more
TI_P_END = TI_P + 40
.assert TI_P_END <= FAR_BATTLE + $300, error, "the shop's party does not fit after its list"

TI_PARTY_OAM_ARROWS = TI_PARTY_MEMBERS * TI_FRAME_TILES
TI_PARTY_HIDDEN = 224           ; a y below the last visible line
TI_PARTY_PRIORITY = $30         ; over every layer
TI_PARTY_ARROW_PAL = TI_PARTY_MEMBERS
TI_PARTY_FRAME_BYTES = TI_FRAME_TILES * 32
; A member's frame is 384 bytes, some two and a half lines of DMA: it starts
; only up to this line. And the arrows and the palettes, which are a handful
; of bytes, up to the other one. The vblank of a 224-line frame runs from 225
; to 261.
TI_PARTY_VBLANK = 225
TI_PARTY_LAST_FRAME = 254
TI_PARTY_LAST_SMALL = 258
.assert TI_PARTY_OAM_ARROWS + TI_PARTY_MEMBERS <= 128, error, "the shop's party takes more objects than there are"
.assert TI_PARTY_ACTORS <= 255, error, "the shop's party names its actors with a byte"

; Who can equip the item the cursor marks and what it does to them: the
; stage's `party::shown`, for each member. From `ti_compose`, before it
; writes anything: it borrows the equipment screen's `eq_parameter`, which
; reads `comp_char`, `comp_col`, `comp_col + 1` and `comp_mask`, so those go
; on the stack and come back. Only when the item or the layer changed: the
; quantity's arrows recompose the screen and would pay for it on every key.
.proc ti_party_compute
.a8
.i16
    lda #TI_PARTY_ON
    bne with_room
    rts
with_room:
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:ti_layer_mode, x
    cmp #TI_LAYER_BUY
    beq on
    lda #0
    sta f:$7E0000 + TI_P_ON
    rep #$20
.a16
    lda #$FFFF
    sta f:$7E0000 + TI_P_ITEM   ; coming back computes again
    sep #$20
.a8
    rts
on:
    lda #1
    sta f:$7E0000 + TI_P_ON
    ; The item: none with an empty list.
    rep #$20
.a16
    stz comp_or23
    sep #$20
.a8
    lda comp_mask
    beq with_item
    jsr ti_item                 ; `eq_id` and X = k
    rep #$20
.a16
    txa
    sta f:$7E0000 + TI_P_ITEMK
    sep #$20
.a8
with_item:
    rep #$20
.a16
    lda comp_or23
    cmp f:$7E0000 + TI_P_ITEM
    sep #$20                    ; `sep` does not touch Z: the `bne` looks at the `cmp`
.a8
    bne changed
    rts
changed:
    rep #$20
.a16
    sta f:$7E0000 + TI_P_ITEM
    sep #$20
.a8
    lda comp_char
    pha
    lda comp_col
    pha
    lda comp_col + 1
    pha
    lda comp_mask
    pha
    lda comp_mask + 1
    pha
    lda #0
    sta f:$7E0000 + TI_P_I
member:
    lda f:$7E0000 + TI_P_I
    cmp f:$7E0000 + TI_P_N
    bcc one
    jmp done
one:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    sta comp_char
    lda #1
    sta f:$7E0000 + TI_P_USABLE, x
    lda #$FF
    sta f:$7E0000 + TI_P_KIND, x
    rep #$20
.a16
    lda f:$7E0000 + TI_P_ITEM
    sep #$20                    ; `sep` does not touch Z: the `bne` looks at the `lda`
.a8
    bne item
    jmp next                    ; none: in colour and without an arrow
item:
    ; `IsItemUsable`: the actor's bit in `item_actors`, eight bytes per item.
    rep #$20
.a16
    lda f:$7E0000 + TI_P_ITEMK
    asl a
    asl a
    asl a
    sta comp_and
    lda comp_char
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc comp_and
    tax
    pla
    and #$0007
    tay                         ; in sixteen bits: `tay` takes B too
    sep #$20
.a8
    lda f:item_actors, x
    cpy #0
    beq bit_ready
shift:
    lsr a
    dey
    bne shift
bit_ready:
    and #1
    sta f:$7E0000 + TI_P_T
    lda f:$7E0000 + TI_P_I
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:$7E0000 + TI_P_T
    sta f:$7E0000 + TI_P_USABLE, x
    bne usable
    jmp next
usable:
    ; Equipment only: types 1 to 5, the slot one less.
    rep #$20
.a16
    lda f:$7E0000 + TI_P_ITEMK
    tax
    sep #$20
.a8
    lda f:item_type, x
    beq not_equipment
    cmp #6
    bcc equipment
not_equipment:
    jmp next
equipment:
    dec a
    sta comp_col                ; the slot it goes in
    ; Already on, in any slot: "E".
    lda #0
    sta f:$7E0000 + TI_P_T
slot:
    jsr eq_read                 ; A: the slot
    rep #$20
.a16
    lda comp_or23
    cmp f:$7E0000 + TI_P_ITEM
    sep #$20                    ; `sep` does not touch Z: the `beq` looks at the `cmp`
.a8
    beq on_already
    lda f:$7E0000 + TI_P_T
    inc a
    sta f:$7E0000 + TI_P_T
    cmp #5
    bcc slot
    bra compare
on_already:
    lda #TI_ARROW_EQUIPPED
    jmp kind
compare:
    ; `CmpEquip`: the four parameters added up as they are, and with the item
    ; in its slot —`eq_effective` takes the other hand off as RM2k does—.
    stz comp_col + 1
    jsr four
    rep #$20
.a16
    lda f:$7E0000 + TI_P_NEW
    sta f:$7E0000 + TI_P_OLD
    lda f:$7E0000 + TI_P_ITEM
    sta comp_mask
    sep #$20
.a8
    lda #1
    sta comp_col + 1            ; choosing: the slot takes the item
    jsr four
    rep #$20
.a16
    lda f:$7E0000 + TI_P_NEW
    cmp f:$7E0000 + TI_P_OLD
    sep #$20
.a8
    beq same
    bcc down
    lda #TI_ARROW_UP
    bra kind
same:
    lda #TI_ARROW_SAME
    bra kind
down:
    lda #TI_ARROW_DOWN
kind:
    pha
    lda f:$7E0000 + TI_P_I
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    pla
    sta f:$7E0000 + TI_P_KIND, x
next:
    lda f:$7E0000 + TI_P_I
    inc a
    sta f:$7E0000 + TI_P_I
    jmp member
done:
    pla
    sta comp_mask + 1
    pla
    sta comp_mask
    pla
    sta comp_col + 1
    pla
    sta comp_col
    pla
    sta comp_char
    rts

; Attack, defense, spirit and agility with the equipment `eq_effective`
; says, each clamped, added up in `TI_P_NEW`.
four:
    rep #$20
.a16
    lda #0
    sta f:$7E0000 + TI_P_NEW
    sep #$20
.a8
    stz comp_or01 + 2
param:
    jsl f:eq_parameter
    rep #$20
.a16
    lda comp_dup
    clc
    adc f:$7E0000 + TI_P_NEW
    sta f:$7E0000 + TI_P_NEW
    sep #$20
.a8
    lda comp_or01 + 2
    inc a
    sta comp_or01 + 2
    cmp #4
    bcc param
    rts
.endproc

; The rest is in `FAR2`, entered with `jsl`: bank 1 had no room for it. The
; data bank is still 0 there, as in the shop.
.segment "FAR2"

; At opening, with the screen off and after `ti_screen_upload`: the object
; base, the arrows' tiles and palette, each member's graphic and the whole OAM.
.proc ti_party_open
.a8
.i16
    ; No room for it in this cartridge's VRAM —see `shop_party` in the
    ; screens' checks—: the shop shows no party, and never turns it on. A
    ; constant of the cartridge's, looked at here and not with `.if`
    ; because `mapdata.inc` comes after this file.
    lda #TI_PARTY_ON
    bne with_room
    sta f:$7E0000 + TI_P_ON
    rtl
with_room:
    lda #(TI_BORDER_VRAM / $2000)  ; 8x8 and 16x16, from the windows' base
    sta OBSEL
    ; The objects' window mask, which `TMW` always applies, is whatever the
    ; last line of the message window's HDMA left: on, if the shop opened
    ; right after a message, and then it hides every object. The map's
    ; vblank sets it again.
    stz WOBJSEL
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TI_ARROW_VRAM
    sta VMADDL
    lda #.loword(ti_arrow_tiles)
    sta A1T0L
    lda #(TI_ARROW_FRAMES * 4 * 32)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_arrow_tiles
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #(128 + 16 * TI_PARTY_ARROW_PAL)
    sta CGADD
    rep #$20
.a16
    lda #.loword(ti_arrow_cgram)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^ti_arrow_cgram
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; Who is shown, and with which graphic.
    lda party_n
    cmp #TI_PARTY_MEMBERS
    bcc n_ready
    lda #TI_PARTY_MEMBERS
n_ready:
    sta f:$7E0000 + TI_P_N
    lda #0
    sta f:$7E0000 + TI_P_ON
    sta f:$7E0000 + TI_P_SUB
    sta f:$7E0000 + TI_P_PHASE
    sta f:$7E0000 + TI_P_SHOWN
    rep #$20
.a16
    lda #$FFFF
    sta f:$7E0000 + TI_P_ITEM
    sep #$20
.a8
    ldx #0
member:
    lda #$FF
    sta f:$7E0000 + TI_P_UP, x
    sta f:$7E0000 + TI_P_PAL, x
    sta f:$7E0000 + TI_P_KIND, x
    sta f:$7E0000 + TI_P_K, x
    txa
    cmp f:$7E0000 + TI_P_N
    bcs next_member
    lda party, x
    cmp #TI_PARTY_ACTORS
    bcs next_member             ; past the table: nobody has a graphic there
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:ti_party_k, x
    plx
    sta f:$7E0000 + TI_P_K, x
next_member:
    inx
    cpx #TI_PARTY_MEMBERS
    bcc member
    ; The OAM: each member's twelve, the arrows, and the rest below the screen.
    stz OAMADDL
    stz OAMADDL + 1
    ldx #0                      ; the member
oam_member:
    ldy #0                      ; its tile
oam_tile:
    lda f:$7E0000 + TI_P_K, x
    cmp #$FF
    bne drawn
    stz OAMDATA
    lda #TI_PARTY_HIDDEN
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    bra oam_next
drawn:
    ; x: X0 + 32 i + 8 (tile mod 3); y: Y0 + 8 (tile div 3).
    txa
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 i
    sta temp
    tya
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:frame_x, x
    clc
    adc temp
    adc #TI_PARTY_X0
    sta OAMDATA
    lda f:frame_y, x
    clc
    adc #TI_PARTY_Y0
    sta OAMDATA
    plx
    ; The tile: TILE0 + 12 i + its own.
    txa
    asl a
    asl a                       ; 4 i
    sta temp
    asl a                       ; 8 i
    clc
    adc temp                    ; 12 i
    sta temp
    tya
    clc
    adc temp
    adc #TI_PARTY_TILE0
    sta OAMDATA
    txa
    asl a                       ; palette i, in vhoopppN
    ora #TI_PARTY_PRIORITY
    sta OAMDATA
oam_next:
    iny
    cpy #TI_FRAME_TILES
    bcc oam_tile
    inx
    cpx #TI_PARTY_MEMBERS
    bcc oam_member
    ; The arrows, hidden until the first vblank says which.
    ldx #TI_PARTY_MEMBERS
arrow:
    stz OAMDATA
    lda #TI_PARTY_HIDDEN
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    dex
    bne arrow
    ldx #(128 - TI_PARTY_OAM_ARROWS - TI_PARTY_MEMBERS)
rest:
    stz OAMDATA
    lda #TI_PARTY_HIDDEN
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    dex
    bne rest
    ldx #32                     ; the high table: x below 256, all small
high:
    stz OAMDATA
    dex
    bne high
    rtl

; Each tile's place inside its 24x32 frame, by rows.
frame_x:
    .byte 0, 8, 16, 0, 8, 16, 0, 8, 16, 0, 8, 16
frame_y:
    .byte 0, 0, 0, 8, 8, 8, 16, 16, 16, 24, 24, 24
.endproc

; On closing, with the screen off: the map's object base and its object
; palettes, which the shop wrote over. The OAM is the map's again with its
; first `push_oam`.
.proc ti_party_close
.a8
.i16
    lda #$80
    sta INIDISP
    ldx map_ofs
    lda f:map_table + M_OBSEL_VALUE, x
    sta OBSEL
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_shadow + 2 * 128)
    sta A1T0L
    lda #(128 * 2)
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the shadow lives in bank 0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; One frame of the walk: a step every `TI_PARTY_RATE`.
.proc ti_party_tick
.a8
.i16
    lda f:$7E0000 + TI_P_SUB
    inc a
    cmp #TI_PARTY_RATE
    bcc keep
    lda f:$7E0000 + TI_P_PHASE
    inc a
    and #3
    sta f:$7E0000 + TI_P_PHASE
    lda #0
keep:
    sta f:$7E0000 + TI_P_SUB
    rtl
.endproc

; What changed, to the PPU: whether the objects are shown, the arrows, the
; palettes and the frames. In the vblank, after the text's uploads; with A
; nonzero the screen is off and everything goes, without looking at the line.
.proc ti_party_vblank
.a8
.i16
    sta f:$7E0000 + TI_P_FORCE
    lda f:$7E0000 + TI_P_ON
    bne shown
    lda #$03                    ; BG1 and BG2: `screen_ppu_on`
    sta TM
    rtl
shown:
    lda #$13                    ; and the objects
    sta TM
    lda #(TI_PARTY_LAST_SMALL - TI_PARTY_VBLANK)
    jsr room
    bcc arrows
    rtl
arrows:
    ; The four arrows' entries: x, y, tile and attributes.
    lda #<(2 * TI_PARTY_OAM_ARROWS)
    sta OAMADDL
    stz OAMADDL + 1
    lda f:$7E0000 + TI_P_PHASE
    sta f:$7E0000 + TI_P_SHOWN
    ldx #0
arrow:
    txa
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 i
    clc
    adc #(TI_PARTY_X0 + TI_ARROW_DX)
    sta OAMDATA
    lda f:$7E0000 + TI_P_KIND, x
    cmp #$FF
    beq hidden
    txa
    cmp f:$7E0000 + TI_P_N
    bcs hidden
    lda #(TI_PARTY_Y0 + TI_ARROW_DY)
    sta OAMDATA
    ; Its tile: TILE0 + 4 kind + the frame; "already on" walks 0, 1, 2, 1.
    lda f:$7E0000 + TI_P_KIND, x
    asl a
    asl a
    sta temp
    lda f:$7E0000 + TI_P_KIND, x
    cmp #TI_ARROW_EQUIPPED
    lda f:$7E0000 + TI_P_PHASE
    bcc frame                   ; carry from the `cmp`: `lda` does not touch it
    cmp #3
    bne frame
    lda #1
frame:
    clc
    adc temp
    adc #TI_ARROW_TILE0
    sta OAMDATA
    lda #(TI_PARTY_PRIORITY | (TI_PARTY_ARROW_PAL << 1))
    sta OAMDATA
    bra arrow_next
hidden:
    lda #TI_PARTY_HIDDEN
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
arrow_next:
    inx
    cpx #TI_PARTY_MEMBERS
    bcc arrow
    ; The palettes: colour, or grey for whoever cannot equip it.
    ldx #0
palette:
    txa
    cmp f:$7E0000 + TI_P_N
    bcs palettes_done
    lda f:$7E0000 + TI_P_K, x
    cmp #$FF
    beq palette_next
    lda f:$7E0000 + TI_P_USABLE, x
    eor #1                      ; 0 colour, 1 grey
    cmp f:$7E0000 + TI_P_PAL, x
    beq palette_next
    sta f:$7E0000 + TI_P_PAL, x
    ; From `ti_party_cgram`: 64 bytes per graphic, the grey after the colour.
    sta f:$7E0000 + TI_P_FRAME
    lda f:$7E0000 + TI_P_K, x
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    lsr a                       ; k * 64
    sta f:$7E0000 + TI_P_T
    lda f:$7E0000 + TI_P_FRAME
    and #$0001
    beq colour
    lda #32
colour:
    clc
    adc f:$7E0000 + TI_P_T
    adc #.loword(ti_party_cgram)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    txa
    asl a
    asl a
    asl a
    asl a
    clc
    adc #128                    ; palette i of the objects
    sta CGADD
    lda #^ti_party_cgram
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
palette_next:
    inx
    cpx #TI_PARTY_MEMBERS
    bcc palette
palettes_done:
    ; The frames: 0, 1, 2, 1, and the middle one still for whoever cannot
    ; equip it. One member at a time, while the line leaves room.
    ldx #0
member:
    txa
    cmp f:$7E0000 + TI_P_N
    bcs members_done
    lda f:$7E0000 + TI_P_K, x
    cmp #$FF
    beq member_next
    lda #1
    sta f:$7E0000 + TI_P_FRAME
    lda f:$7E0000 + TI_P_USABLE, x
    beq wanted
    lda f:$7E0000 + TI_P_PHASE
    cmp #3
    beq wanted
    sta f:$7E0000 + TI_P_FRAME
wanted:
    lda f:$7E0000 + TI_P_FRAME
    cmp f:$7E0000 + TI_P_UP, x
    beq member_next
    lda #(TI_PARTY_LAST_FRAME - TI_PARTY_VBLANK)
    jsr room
    bcs members_done
    lda f:$7E0000 + TI_P_FRAME
    sta f:$7E0000 + TI_P_UP, x
    jsr upload
member_next:
    inx
    cpx #TI_PARTY_MEMBERS
    bcc member
members_done:
    rtl

; Frame `TI_P_FRAME` of member X's graphic to its slot. Keeps X.
upload:
    phx
    lda #$80
    sta VMAIN
    rep #$20
.a16
    txa
    and #$00FF
    asl a
    asl a                       ; 4 i
    sta f:$7E0000 + TI_P_T
    asl a                       ; 8 i
    clc
    adc f:$7E0000 + TI_P_T      ; 12 i
    asl a
    asl a
    asl a
    asl a                       ; sixteen words per tile
    clc
    adc #TI_PARTY_VRAM
    sta VMADDL
    lda f:$7E0000 + TI_P_FRAME
    and #$00FF
    asl a
    tax
    lda f:frame_offset, x
    sta f:$7E0000 + TI_P_T      ; where the frame starts in its graphic
    lda 1, s                    ; the member, from the `phx`
    and #$00FF
    tax
    sep #$20
.a8
    lda f:$7E0000 + TI_P_K, x
    rep #$20
.a16
    and #$00FF
    sta f:$7E0000 + TI_P_T2
    asl a
    clc
    adc f:$7E0000 + TI_P_T2     ; three bytes per pointer
    tax
    lda f:ti_party_ptr, x
    clc
    adc f:$7E0000 + TI_P_T
    sta A1T0L
    lda #TI_PARTY_FRAME_BYTES
    sta DAS0L
    sep #$20
.a8
    lda f:ti_party_ptr + 2, x
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    plx
    rts

frame_offset:
    .word 0, TI_PARTY_FRAME_BYTES, 2 * TI_PARTY_FRAME_BYTES

; Carry clear if the vblank has room for something that starts by line
; `TI_PARTY_VBLANK` + A: with the screen off, always; if not, the line has to
; be in the vblank and not past that one.
room:
    sta f:$7E0000 + TI_P_T
    lda f:$7E0000 + TI_P_FORCE
    beq look
    clc
    rts
look:
    lda #0
    sta f:$7E0000 + TI_P_T + 1
    rep #$20
.a16
    lda f:$7E0000 + TI_P_T
    clc
    adc #TI_PARTY_VBLANK
    sta f:$7E0000 + TI_P_T
    sep #$20
.a8
    lda STAT78                  ; resets the counters' flip-flop
    lda SLHV
    lda OPVCT
    xba
    lda OPVCT
    and #$01
    xba
    rep #$20
.a16
    cmp #TI_PARTY_VBLANK
    bcc no                      ; still drawing, or drawing again
    cmp f:$7E0000 + TI_P_T
    beq yes
    bcs no
yes:
    sep #$20
.a8
    clc
    rts
.a16
no:
    sep #$20
.a8
    sec
    rts
.endproc

.segment "FAR"
