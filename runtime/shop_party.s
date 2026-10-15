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
TI_P_ITEM = TI_P + 5            ; two bytes: the item, $FFFF none computed yet
TI_P_ITEMK = TI_P + 7           ; two bytes: its `k`
TI_P_K = TI_P + 9               ; four: each member's graphic, $FF none
TI_P_USABLE = TI_P + 13         ; four: whether it can equip the item
TI_P_KIND = TI_P + 17           ; four: its arrow, $FF none
TI_P_UP = TI_P + 21             ; four: the frame its slot has, $FF unknown
TI_P_PAL = TI_P + 25            ; four: 0 colour, 1 grey, $FF unknown
TI_P_END = TI_P + 29
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
; Its scratch is `temp`, which none of what it calls touches: `temp` and
; `temp + 1` the parameters' sum, `temp + 2` the member —a word, so that
; `ldx` takes it—.
.proc ti_party_compute
.a8
.i16
    ; No room for the party in this cartridge's VRAM —see `shop_party` in the
    ; screens' checks—: `ti_party_open` left it off. A constant of the
    ; cartridge's, looked at here and not with `.if` because `mapdata.inc`
    ; comes after this file.
    lda #TI_PARTY_ON
    beq off
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
off:
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
    bne changed
    sep #$20
.a8
    rts
.a16
changed:
    sta f:$7E0000 + TI_P_ITEM
    sep #$20
.a8
    lda comp_char
    pha
    rep #$20
.a16
    lda comp_col                ; and `comp_col + 1`
    pha
    lda comp_mask
    pha
    stz temp + 2                ; the member
    sep #$20
.a8
member:
    lda temp + 2
    cmp f:$7E0000 + TI_P_N
    bcc one
    jmp done
one:
    ldx temp + 2
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
    ldx temp + 2
    sta f:$7E0000 + TI_P_USABLE, x
    cmp #0                      ; `sta` keeps the `and`'s Z, but say it
    beq next
    ; Equipment only: types 1 to 5, the slot one less.
    rep #$20
.a16
    lda f:$7E0000 + TI_P_ITEMK
    tax
    sep #$20
.a8
    lda f:item_type, x
    beq next
    cmp #6
    bcs next
    dec a
    sta comp_col                ; the slot it goes in
    ; Already on, in any slot: "E". `eq_read` keeps Y.
    ldy #0
slot:
    tya
    jsr eq_read
    rep #$20
.a16
    lda comp_or23
    cmp f:$7E0000 + TI_P_ITEM
    sep #$20                    ; `sep` does not touch Z: the `beq` looks at the `cmp`
.a8
    beq on_already
    iny
    cpy #5
    bcc slot
    ; `CmpEquip`: the four parameters added up as they are, and with the item
    ; in its slot —`eq_effective` takes the other hand off as RM2k does—.
    stz comp_col + 1
    jsr four
    rep #$20
.a16
    lda temp
    pha                         ; as they are
    lda f:$7E0000 + TI_P_ITEM
    sta comp_mask
    sep #$20
.a8
    lda #1
    sta comp_col + 1            ; choosing: the slot takes the item
    jsr four
    rep #$20
.a16
    pla
    cmp temp                    ; as they are against with the item
    sep #$20
.a8
    beq same
    bcc up
    lda #TI_ARROW_DOWN
    bra kind
up:
    lda #TI_ARROW_UP
    bra kind
same:
    lda #TI_ARROW_SAME
    bra kind
on_already:
    lda #TI_ARROW_EQUIPPED
kind:
    ldx temp + 2
    sta f:$7E0000 + TI_P_KIND, x
next:
    inc temp + 2
    jmp member
done:
    rep #$20
.a16
    pla
    sta comp_mask
    pla
    sta comp_col
    sep #$20
.a8
    pla
    sta comp_char
    rts

; Attack, defense, spirit and agility with the equipment `eq_effective`
; says, each clamped, added up in `temp`.
four:
    rep #$20
.a16
    stz temp
    sep #$20
.a8
    stz comp_or01 + 2
param:
    jsl f:eq_parameter
    rep #$20
.a16
    lda comp_dup
    clc
    adc temp
    sta temp
    sep #$20
.a8
    inc comp_or01 + 2
    lda comp_or01 + 2
    cmp #4
    bcc param
    rts
.endproc

; What changed, to the PPU: whether the objects are shown, the arrows, the
; palettes and the frames. In the vblank, after the text's uploads; with A
; nonzero the screen is off and everything goes, without looking at the line.
; Returns with `rtl`. Its scratch is `temp`: `temp + 3` whether it is forced,
; `temp + 2` the frame being uploaded, `temp` and `temp + 1` the rest.
.proc ti_party_vblank
.a8
.i16
    sta temp + 3
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
    ; The four arrows' entries: x, y, tile and attributes. A member past the
    ; party has its kind at $FF since the opening.
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
    ; Each member with a graphic —past the party it is $FF since the
    ; opening—: its palette, colour or grey, and its frame, 0, 1, 2, 1, or
    ; the middle one still for whoever cannot equip the item. While the line
    ; leaves room.
    ldx #0
member:
    lda f:$7E0000 + TI_P_K, x
    cmp #$FF
    beq member_next
    lda f:$7E0000 + TI_P_USABLE, x
    eor #1                      ; 0 colour, 1 grey
    cmp f:$7E0000 + TI_P_PAL, x
    beq frames
    sta temp + 2
    lda #(TI_PARTY_LAST_SMALL - TI_PARTY_VBLANK)
    jsr room
    bcs done
    lda temp + 2
    sta f:$7E0000 + TI_P_PAL, x
    jsr palette
frames:
    lda #1
    sta temp + 2
    lda f:$7E0000 + TI_P_USABLE, x
    beq wanted
    lda f:$7E0000 + TI_P_PHASE
    cmp #3
    beq wanted
    sta temp + 2
wanted:
    lda temp + 2
    cmp f:$7E0000 + TI_P_UP, x
    beq member_next
    lda #(TI_PARTY_LAST_FRAME - TI_PARTY_VBLANK)
    jsr room
    bcs done
    lda temp + 2
    sta f:$7E0000 + TI_P_UP, x
    jsl f:ti_party_upload
member_next:
    inx
    cpx #TI_PARTY_MEMBERS
    bcc member
done:
    rtl

; Member X's palette to its row of the objects': from `ti_party_cgram`, 64
; bytes per graphic, the grey after the colour as `temp + 2` says. Keeps X.
palette:
    txa
    asl a
    asl a
    asl a
    asl a
    ora #$80                    ; 128 + 16 i
    sta CGADD
    lda f:$7E0000 + TI_P_K, x
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    lsr a                       ; k * 64
    sta temp
    lda temp + 2
    and #$0001
    beq colour
    lda #32
colour:
    clc
    adc temp
    adc #.loword(ti_party_cgram)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^ti_party_cgram
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts

; Carry clear if the vblank has room for something that starts by line
; `TI_PARTY_VBLANK` + A: with the screen off, always; if not, the line has to
; be in the vblank and not past that one.
room:
    pha
    lda temp + 3
    bne yes
    lda STAT78                  ; resets the counters' flip-flop
    lda SLHV
    lda OPVCT
    xba
    lda OPVCT
    and #$01
    xba
    rep #$20
.a16
    sec
    sbc #TI_PARTY_VBLANK
    sep #$20                    ; `sep` does not touch C: the `bcc` looks at the `sbc`
.a8
    bcc no                      ; still drawing, or drawing again
    xba
    bne no                      ; past the vblank
    xba
    cmp 1, s
    beq yes
    bcs no
yes:
    pla
    clc
    rts
no:
    pla
    sec
    rts
.endproc

; The rest is in `FAR2`, entered with `jsl`: bank 1 had no room for it all,
; and `FAR2` has less in a game with painted maps —Sunset over Imdahl had 555
; bytes left there on 2026-10-15—. The data bank is still 0 there, as in the
; shop. `ti_party_vblank`, above, also returns with `rtl`.
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
    ; The members' slots blank, so one without a graphic shows nothing: a
    ; fixed source of zero.
    ldx #TI_PARTY_VRAM
    stx VMADDL
    ldx #$1809
    stx temp
    ldx #.loword(zero)
    ldy #(TI_PARTY_MEMBERS * TI_FRAME_TILES * 32)
    lda #^zero
    jsr dma
    ; The arrows' tiles and palette.
    ldx #TI_ARROW_VRAM
    stx VMADDL
    ldx #$1801
    stx temp
    ldx #.loword(ti_arrow_tiles)
    ldy #(TI_ARROW_FRAMES * 4 * 32)
    lda #^ti_arrow_tiles
    jsr dma
    lda #(128 + 16 * TI_PARTY_ARROW_PAL)
    sta CGADD
    ldx #$2200
    stx temp
    ldx #.loword(ti_arrow_cgram)
    ldy #32
    lda #^ti_arrow_cgram
    jsr dma
    ; The whole OAM, which the converter lays out —`ti_party_oam`—: member
    ; `i`'s twelve objects with palette `i`, the arrows and the rest below
    ; the screen, and the high table at zero.
    stz OAMADDL
    stz OAMADDL + 1
    ldx #$0400
    stx temp
    ldx #.loword(ti_party_oam)
    ldy #544
    lda #^ti_party_oam
    jsr dma
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
    rtl

; Channel 0, once: from A:X, Y bytes, with `temp` its mode and its register
; —`DMAP0` and `BBAD0`, which are next to each other—.
dma:
    stx A1T0L
    sta A1B0
    sty DAS0L
    ldx temp
    stx DMAP0
    lda #$01
    sta MDMAEN
    rts

zero:
    .byte 0
.endproc

; Frame `temp + 2` of member X's graphic to its slot, from `ti_party_vblank`.
; Keeps X.
.proc ti_party_upload
.a8
.i16
    phx
    lda #$80
    sta VMAIN
    txa
    asl a
    asl a                       ; 4 i
    sta temp
    asl a                       ; 8 i
    clc
    adc temp                    ; 12 i
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a                       ; sixteen words per tile
    clc
    adc #TI_PARTY_VRAM
    sta VMADDL
    lda temp + 2
    and #$00FF
    asl a
    tax
    lda f:frame_offset, x
    sta temp                    ; where the frame starts in its graphic
    lda 1, s                    ; the member, from the `phx`
    tax
    sep #$20
.a8
    lda f:$7E0000 + TI_P_K, x
    rep #$20
.a16
    and #$00FF
    pha
    asl a
    clc
    adc 1, s                    ; three bytes per pointer
    tax
    pla
    lda f:ti_party_ptr, x
    clc
    adc temp
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
    rtl

frame_offset:
    .word 0, TI_PARTY_FRAME_BYTES, 2 * TI_PARTY_FRAME_BYTES
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


.segment "FAR"
