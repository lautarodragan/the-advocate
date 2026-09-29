.segment "CODE"

; Is the actor in A in the party? Returns with Z=0 if so.
.proc en_el_grupo
.a8
.i16
    ldx #$0000
busca:
    cpx grupo_n                 ; grupo_n is 16 bits on purpose: with .i16
    beq no_esta                 ; this comparison reads two bytes anyway
    cmp grupo, x
    beq esta
    inx
    bra busca
esta:
    lda #1                      ; Z=0
    rts
no_esta:
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
.proc cambiar_grupo
.a8
.i16
    ldx #$0000
buscar:
    cpx grupo_n
    beq no_estaba
    cmp grupo, x
    beq estaba
    inx
    bra buscar

estaba:
    ; `temp` is checked with A and not with `ldy temp`: with .i16 that would
    ; read two bytes and the next one is not ours. It is the index-width trap,
    ; already noted at the top of main.s, and here it gave exactly the symptom
    ; it promises: no party change had any effect and there was no error.
    pha
    lda temp
    beq era_agregar             ; adding one who is already there: nothing to do
    pla
    ; Removing it: the ones behind move up one place.
correr:
    inx
    cpx grupo_n
    beq acortar
    lda grupo, x
    sta grupo - 1, x
    bra correr
acortar:
    rep #$20
.a16
    dec grupo_n
    sep #$20
.a8
    bra listo
era_agregar:
    pla
    bra listo

no_estaba:
    pha
    lda temp
    bne era_sacar               ; removing one who is not there: nothing to do
    pla
    cpx #GRUPO_MAX
    beq listo                   ; full: RM2k does not add it either
    sta grupo, x
    rep #$20
.a16
    inc grupo_n
    sep #$20
.a8
    bra listo
era_sacar:
    pla

listo:
    jsr elegir_grafico_heroe
    ; The new leader has other colors and shares the slot with the previous
    ; one, so the palettes have to be rebuilt. It does not touch CGRAM: it
    ; leaves everything in `cgram_sombra` and `subir_tinte` uploads it in the
    ; vblank.
    jsr aplicar_tinte
    lda #1
    sta refresco                ; the pages that ask for an actor may change
    rts
.endproc

; A: an index into the map's graphics table —the one `ruta_grafico` builds and
; `load_ruta_graficos` copies to `ruta_graf_buf`—. Leaves `hero_poses`,
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
; `aplicar_tinte` **into the row `hero_pal` names**, so leaving it on with the
; new palette would write Talan's colors over the palette of the graphic it
; changed to. While the change is in effect, the hero is drawn with the new
; graphic's palette, which already lives in CGRAM with the rest of the map's
; sprites.
;
; It is used by the two things that change the hero's graphic: move command
; 34 of a move route —`grafico_heroe`— and the `ChangeSpriteAssociation` on
; the actor who leads —`elegir_grafico_heroe`—. What each one does with C=0 is
; different and that is why it stays outside: command 34 hides the hero and
; the actor change leaves it with the LDB graphic.
.proc hero_poses_de_grafico
.a8
.i16
    asl a                       ; two bytes per entry in `ruta_graf_buf`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta_graf_buf, x        ; its entry in `npc_poses`, or $FF
    cmp #$FF
    beq no_esta
    sta temp
    lda ruta_graf_buf + 1, x
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
no_esta:
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
.proc elegir_grafico_heroe
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
    lda grupo_n
    bne con_grupo               ; `beq sin_lider` no longer reaches
    rts                         ; empty party: nothing is drawn
con_grupo:

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ACTOR_COUNT, x
    beq sin_lider16
    sta temp + 2
    lda f:mapa_tabla + M_PTR_ACTOR_TABLE, x
    sta act_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_ACTOR_TABLE + 2, x
    sta act_ptr + 2

    ldy #$0000
    lda grupo                   ; the leader
    sta temp
cada_actor:
    lda [act_ptr], y
    cmp temp
    beq lo_encontre
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_BYTES
    tay
    dec temp + 2
    sep #$20
.a8
    bne cada_actor
    bra sin_lider

lo_encontre:
    ; Before the LDB, whatever `ChangeSpriteAssociation` was done to this
    ; actor: it is RM2k's `actor->SetSprite`, and it lives in the actor, so it
    ; **survives the teleport**. If its graphic is not in this map's sprite
    ; bank it falls back to the LDB one, which is what the path below points
    ; at. See OP_ACTOR_SPRITE in eventos.py.
    phy                         ; the actor's entry, in case there is no change
    lda temp                    ; the leader
    jsr actor_gfx_read
    cmp #ACTOR_GRAF_NINGUNO
    beq sin_cambio_de_sprite
    jsr hero_poses_de_grafico
    bcc sin_cambio_de_sprite
    ply
    rts
sin_cambio_de_sprite:
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
    adc #ACTOR_COLORES          ; and after them, the twelve pose words
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
    ; at, the pose at $FFFF, and with `hero_cgram` off `aplicar_tinte` uploads
    ; nothing.
    rep #$20
.a16
    lda [act_ptr], y            ; the first of its twelve poses
    cmp #$FFFF
    sep #$20                    ; `sep` does not touch Z: the `bne` looks at the `cmp`
.a8
    bne con_grafico
    stz hero_cgram + 2
con_grafico:
    rts

sin_lider16:
.a16
    ; reached in sixteen; the `sep` below narrows it
    sep #$20
.a8
sin_lider:
    rts
.endproc

