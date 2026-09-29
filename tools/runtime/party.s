.segment "CODE"

; Is the actor in A in the party? Returns with Z=0 if so.
.proc in_party
.a8
.i16
    ldx #$0000
seek:
    cpx party_n                 ; party_n is 16 bits on purpose: with .i16
    beq no_is                 ; this comparison reads two bytes anyway
    cmp party, x
    beq is
    inx
    bra seek
is:
    lda #1                      ; Z=0
    rts
no_is:
    lda #0                      ; Z=1
    rts
.endproc

; Adds an actor to the party or removes one, and recomputes what the hero is
; drawn with. A = the actor, temp = 0 to add and 1 to remove.
;
; The rules are those of `Game_Party::AddActor` and `RemoveActor`: adding
; someone who is already there neither duplicates them nor moves them, adding
; with the party full does nothing, and neither does removing someone who is
; not there. The order matters because the first one is the one drawn.
.proc change_party
.a8
.i16
    ldx #$0000
seek:
    cpx party_n
    beq no_was
    cmp party, x
    beq was
    inx
    bra seek

was:
    ; `temp` is checked with A and not with `ldy temp`: with .i16 that would
    ; read two bytes and the next one is not ours. It is the index-width trap,
    ; already noted at the top of main.s, and here it gave exactly the symptom
    ; it promises: no party change had any effect and there was no error.
    pha
    lda temp
    beq was_add             ; adding one who is already there: nothing to do
    pla
    ; Removing it: the ones behind move up one place.
run:
    inx
    cpx party_n
    beq shorten
    lda party, x
    sta party - 1, x
    bra run
shorten:
    rep #$20
.a16
    dec party_n
    sep #$20
.a8
    bra ready
was_add:
    pla
    bra ready

no_was:
    pha
    lda temp
    bne was_take               ; removing one who is not there: nothing to do
    pla
    cpx #PARTY_MAX
    beq ready                   ; full: RM2k does not add it either
    sta party, x
    rep #$20
.a16
    inc party_n
    sep #$20
.a8
    bra ready
was_take:
    pla

ready:
    jsr pick_hero_graphic
    ; The new leader has other colors and shares the slot with the previous
    ; one, so the palettes have to be rebuilt. It does not touch CGRAM: it
    ; leaves everything in `cgram_shadow` and `upload_tint` uploads it in the
    ; vblank.
    jsr apply_tint
    lda #1
    sta refresh                ; the pages that ask for an actor may change
    rts
.endproc

; A: an index into the map's graphics table —the one `ruta_grafico` builds and
; `load_route_graphics` copies to `route_gfx_buf`—. Leaves `hero_poses`,
; `hero_pal` and `hero_cgram` pointing at that graphic and returns with C=1;
; if the graphic is not in this map's sprite bank it returns with C=0 and
; without touching anything.
;
; It comes cheap because the two pose tables have the same shape: an entry of
; `npc_poses` is twelve three-byte pointers to the character's poses, and the
; twelve the actor table gives the leader are written the same way. That is,
; pointing `hero_poses` thirty-six bytes into `npc_poses` is enough and
; `place_hero` still does not notice.
;
; `hero_cgram` is turned off: the leader's fifteen colors are uploaded by
; `apply_tint` **into the row `hero_pal` names**, so leaving it on with the
; new palette would write Talan's colors over the palette of the graphic it
; changed to. While the change is in effect, the hero is drawn with the new
; graphic's palette, which already lives in CGRAM with the rest of the map's
; sprites.
;
; It is used by the two things that change the hero's graphic: move command
; 34 of a move route —`graphic_hero`— and the `ChangeSpriteAssociation` on
; the actor who leads —`pick_hero_graphic`—. What each one does with C=0 is
; different and that is why it stays outside: command 34 hides the hero and
; the actor change leaves it with the LDB graphic.
.proc hero_poses_of_graphic
.a8
.i16
    asl a                       ; two bytes per entry in `route_gfx_buf`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda route_gfx_buf, x        ; its entry in `npc_poses`, or $FF
    cmp #$FF
    beq no_is
    sta temp
    lda route_gfx_buf + 1, x
    asl a
    and #$0E                    ; the palette, shifted into place in vhoopppN
    sta hero_pal
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; k times four
    sta temp + 2
    asl a
    asl a
    asl a                       ; k times thirty-two
    clc
    adc temp + 2                ; thirty-six per character: twelve three-byte
    clc                         ; pointers, like the actor table
    adc poses_ptr
    sta hero_poses
    sep #$20
.a8
    lda poses_ptr + 2
    adc #0
    sta hero_poses + 2
    stz hero_cgram + 2          ; see above: nobody uploads colors on top
    sec
    rts
no_is:
    clc
    rts
.endproc

; What the hero is drawn with: the first one in the party is looked up in the
; map's actor table and its twelve poses and its palette are stored.
;
; This did not exist before: the hero was always character 0 of the sprite
; bank and each pose's tile came out of a computation. With the party
; changing on the fly that is no longer enough, and besides the tile can go
; past eight bits when there are several characters, so it is read from a
; table.
.proc pick_hero_graphic
.a8
.i16
    lda #$FF
    sta hero_pose_vram          ; another actor: its pose must be uploaded no matter what
    stz hero_pal
    rep #$20
.a16
    stz hero_poses
    stz hero_cgram
    sep #$20
.a8
    stz hero_poses + 2
    stz hero_cgram + 2
    lda party_n
    bne with_party               ; `beq no_leader` no longer reaches
    rts                         ; empty party: nothing is drawn
with_party:

    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_ACTOR_COUNT, x
    beq no_leader16
    sta temp + 2
    lda f:map_table + M_PTR_ACTOR_TABLE, x
    sta act_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_ACTOR_TABLE + 2, x
    sta act_ptr + 2

    ldy #$0000
    lda party                   ; the leader
    sta temp
each_actor:
    lda [act_ptr], y
    cmp temp
    beq lo_found
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_BYTES
    tay
    dec temp + 2
    sep #$20
.a8
    bne each_actor
    bra no_leader

lo_found:
    ; Before the LDB, whatever `ChangeSpriteAssociation` was done to this
    ; actor: it is RM2k's `actor->SetSprite`, and it lives in the actor, so it
    ; **survives the teleport**. If its graphic is not in this map's sprite
    ; bank it falls back to the LDB one, which is what the path below points
    ; at. See OP_ACTOR_SPRITE in events.py.
    phy                         ; the actor's entry, in case there is no change
    lda temp                    ; the leader
    jsr actor_gfx_read
    cmp #ACTOR_GFX_NONE
    beq no_change_sprite
    jsr hero_poses_of_graphic
    bcc no_change_sprite
    ply
    rts
no_change_sprite:
    ply
    iny
    lda [act_ptr], y            ; its palette, already shifted into place in vhoopppN
    asl a
    and #$0E
    sta hero_pal
    iny                         ; and here its fifteen colors start
    rep #$20
.a16
    tya
    clc
    adc act_ptr
    sta hero_cgram
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_cgram + 2
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_COLORS          ; and after them, the twelve pose words
    tay
    clc
    adc act_ptr
    sta hero_poses
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_poses + 2
    ; An actor with no graphic —DummyHero— brings its fifteen colors at zero
    ; and palette 0, which is not its own: it is the one of the first graphic
    ; the converter handed out, and in the cutscenes where it leads it tends
    ; to be Talan's, standing as an event. Uploading them left it black until
    ; the next map. It is recognized by the same sentinel `place_hero` looks
    ; at, the pose at $FFFF, and with `hero_cgram` off `apply_tint` uploads
    ; nothing.
    rep #$20
.a16
    lda [act_ptr], y            ; the first of its twelve poses
    cmp #$FFFF
    sep #$20                    ; `sep` does not touch Z: the `bne` looks at the `cmp`
.a8
    bne with_graphic
    stz hero_cgram + 2
with_graphic:
    rts

no_leader16:
.a16
    ; reached in sixteen; the `sep` below narrows it
    sep #$20
.a8
no_leader:
    rts
.endproc

