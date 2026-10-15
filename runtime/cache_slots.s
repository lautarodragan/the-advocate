.segment "FAR"
.a8
.i16

; --- a cache of slots -----------------------------------------------------------
;
; Every other map gives each event drawn a VRAM slot for the whole map: the
; walking ones one each, the still ones one per pose. A map with a crowd
; —ABL's farm, 127: twenty-nine people on one screen, and fifteen more in
; the next scene— asks for more slots than the bank has even with the still
; ones taking turns (shared_poses.s). In such a map, and only there, nobody
; owns a slot: an event asks for one when `place_npc` is about to draw it,
; and the console uploads its pose there with `vram_queue`, like every
; hot-swapped pose. Which maps, and how many slots, Wally decides:
; `sprites::cache`.
;
; What a slot holds is its key:
;
;   0 to 127    a still pose, which every still event showing it shares.
;               The row carries it in its tile byte (+6), and so do the
;               pages of the ones that change graphic; the cartridge's
;               `cache_data` says where its pose is in `npc_poses`
;   128 + e     event e's own: it walks or animates in place, and changes
;               pose by itself through `upload_npc_pose`, which asks
;               `cache_dest` where its slot is
;   $FF         nothing
;
; A slot is free when nobody drew it in the last two frames: every frame
; `build_oam` ages them all —`cache_age`—, and drawing one brings its age
; back to 0. Of the free ones, the one drawn longest ago goes. That is the
; margin: one that steps out of view and back finds its pose still up,
; unless the cache needed the slot meanwhile; and one that left this frame
; is not taken from under it by one drawn before it in the same pass.
;
; **If the cache is full** —every slot was drawn this frame or the last— the
; one asking is not drawn, and asks again next frame: it waits for someone to
; leave the screen. It never hangs, and who waits is whoever `build_oam`
; reaches last, which is the one furthest back. Wally warns when the events'
; starting places can put more on screen than the cache has; in ABL's farm
; they cannot, because its two crowds are never there together.
;
; A row that gets a slot is not drawn in the frame that queues its pose but
; in the next, with the pose up, like shared_poses.s; and the first frame of
; a map goes through `build_oam_settled`, which uploads with the screen off
; until nobody is missing. The one facing the hero is drawn from the turn
; slot and does not ask: see `turn_fire`.
;
; Whether the map has a cache is bit 7 of `SHARE_N`, so that `place_npc`
; looks at a single byte for both: no map has both, because the cache is
; what is left when taking turns is not enough.

; From `load_sprite`, after `share_load`: the loaded map's cache, and nobody
; holds anything.
.proc cache_load
.a8
.i16
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:cache_maps, x
    sta f:CACHE_REC
    tax
    sep #$20
.a8
    cpx #0
    beq none                    ; this map has no cache
    lda f:cache_data, x         ; how many slots
    sta f:CACHE_N
    lda #$80
    sta f:SHARE_N               ; `place_npc` asks the cache
    lda #$FF
    ldx #CACHE_MAX - 1
slots:
    sta f:CACHE_KEY, x
    sta f:CACHE_AGE, x          ; nobody drew it for ages
    dex
    bpl slots
    ldx #EV_MAX - 1
events:
    sta f:CACHE_EV, x
    dex
    bpl events
none:
    rtl
.endproc

; Every slot free, keeping what it holds: from `build_oam_settled`, before a
; frame that draws the screen anew —entering the map, a teleport within it,
; coming back from a battle—. What the last frame drew is no reason to keep
; a slot from whoever is on screen now, and without this the settled frame
; ended with some rows waiting: everything drawn just before the teleport
; was too recent to be taken.
.proc cache_settle
.a8
.i16
    jsr cache_last
    lda #$FF
old:
    sta f:CACHE_AGE, x
    dex
    bpl old
    rtl
.endproc

; One frame older, every slot: from `build_oam`, before drawing. $FF stays.
.proc cache_age
.a8
.i16
    rep #$20
.a16
    lda f:CACHE_N
    and #$00FF
    dec a
    tax
    sep #$20
.a8
older:
    lda f:CACHE_AGE, x
    inc a
    beq keep                    ; it was $FF
    sta f:CACHE_AGE, x
keep:
    dex
    bpl older
    rtl
.endproc

; Row X, about to be drawn in a map with a cache. Carry clear: it is drawn,
; with `obj_tile` and `obj_attr` already set. Carry set and A zero: it is not
; drawn this frame —the cache is full—. Carry set and A not zero: its pose
; goes up first —`vq_src` and `vq_dest` ready for `vram_queue`, and
; `cache_took` if it got in— and it is drawn from the next frame on.
.proc cache_want
.a8
.i16
    rep #$20
.a16
    txa
    sta f:CACHE_T_ROW
    sep #$20
.a8
    txy                         ; Y: the row, until the upload
    lda npc_buf + 8, y          ; its event
    sta f:CACHE_T_EV
    ; The one facing the hero is in the turn slot, which its row points at.
    cmp f:TURN_EV
    bne asks
    lda npc_buf + 6, y
    sta obj_tile
    lda npc_buf + 7, y
    sta obj_attr
    clc
    rtl
asks:
    ; What it asks for: the still pose its row carries, or its own.
    lda npc_buf + 9, y
    cmp #NPC_STILL
    beq still
    lda npc_buf + 8, y
    ora #$80
    bra keyed
still:
    lda npc_buf + 6, y
keyed:
    sta f:CACHE_T_KEY
    ; The slot it had, if it still holds that.
    jsr cache_event_x
    lda f:CACHE_EV, x
    cmp #$FF
    beq seek
    jsr cache_a_to_x
    lda f:CACHE_KEY, x
    cmp f:CACHE_T_KEY
    beq drawn
seek:
    ; A still pose someone else already has up.
    lda f:CACHE_T_KEY
    bmi evict                   ; one's own is nobody else's
    jsr cache_last
seek_one:
    lda f:CACHE_KEY, x
    cmp f:CACHE_T_KEY
    beq found
    dex
    bpl seek_one
evict:
    ; The free one drawn longest ago: two frames or more.
    lda #1
    sta f:CACHE_T_AGE
    lda #$FF
    sta f:CACHE_T_SLOT
    jsr cache_last
oldest:
    lda f:CACHE_AGE, x
    cmp f:CACHE_T_AGE
    bcc younger
    beq younger
    sta f:CACHE_T_AGE
    txa
    sta f:CACHE_T_SLOT
younger:
    dex
    bpl oldest
    lda f:CACHE_T_SLOT
    cmp #$FF
    bne upload
    lda #0                      ; full: it waits
    sec
    rtl

found:
    ; It is its slot from now on.
    txa
    pha
    jsr cache_event_x
    pla
    sta f:CACHE_EV, x
    jsr cache_a_to_x
drawn:
    ; Drawn: its age back to 0, and its tile with the row's attributes.
    lda #0
    sta f:CACHE_AGE, x
    jsr cache_tile
.a16
    sta temp
    lda f:CACHE_T_ROW
    tax                         ; X as it came
    sep #$20
.a8
    lda temp
    sta obj_tile
    lda temp + 1
    and #$01                    ; bit 8 of the tile lives in the attributes
    sta obj_attr
    lda npc_buf + 7, x
    and #$FE
    ora obj_attr
    sta obj_attr
    clc
    rtl

upload:
    ; Where it goes: the slot's tile times sixteen words from the sprites'
    ; base, which is the map's.
    jsr cache_a_to_x
    jsr cache_tile
.a16
    asl a
    asl a
    asl a
    asl a
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    ; And where it comes from: its place in `npc_poses`, (k * 12 + pose) * 3.
    lda f:CACHE_T_KEY
    bmi own
    rep #$20
.a16
    and #$00FF
    asl a
    sta temp
    lda f:CACHE_REC
    tax
    lda f:cache_data + 1, x     ; where the map's still poses start
    clc
    adc temp
    tax
    lda f:cache_data, x
    bra source
.a8
own:
    ; Its pose is the one its row last asked for; a row nobody refreshed
    ; since the map loaded faces where its page says, standing.
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tax
    sep #$20
.a8
    lda npc_buf + 12, x
    cmp #$FF
    bne with_pose
    lda npc_buf + 10, x
    sta temp
    asl a
    clc
    adc temp                    ; the direction times three
    inc a                       ; the middle column
with_pose:
    sta f:CACHE_T_POSE
    rep #$20
.a16
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; the pose times three
    sta temp
    lda npc_buf + 9, x
    and #$00FF
    asl a
    asl a                       ; times four
    sta temp + 2
    asl a
    asl a
    asl a                       ; times thirty-two
    clc
    adc temp + 2                ; thirty-six per character
    clc
    adc temp
source:
.a16
    tay
    lda [poses_ptr], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [poses_ptr], y
    sta vq_src + 2
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tax                         ; X as it came
    sep #$20
.a8
    lda #1
    sec
    rtl
.endproc

; The pose `cache_want` asked for got into the queue: the slot holds it from
; the next vblank on, and it is the row's.
.proc cache_took
.a8
.i16
    lda f:CACHE_T_SLOT
    jsr cache_a_to_x
    lda f:CACHE_T_KEY
    sta f:CACHE_KEY, x
    lda #0
    sta f:CACHE_AGE, x
    jsr cache_event_x
    lda f:CACHE_T_SLOT
    sta f:CACHE_EV, x
    lda f:CACHE_T_KEY
    bpl ready
    ; Its own: the pose in the slot is the one `upload_npc_pose` compares.
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tax
    sep #$20
.a8
    lda f:CACHE_T_POSE
    sta npc_buf + 12, x
    lda #1                      ; and if it animates standing still, its
    sta f:still_dirty           ; column goes up next frame: animated_stills.s
ready:
    rtl
.endproc

; Where row Y's own slot is, for `upload_npc_pose`: carry clear and
; `vq_dest` set, or carry set if it has none —it is out of view, and the pose
; it asked for waits in its row for `cache_want`—. Y as it came.
.proc cache_dest
.a8
.i16
    lda npc_buf + 8, y
    sta f:CACHE_T_EV
    jsr cache_event_x
    lda f:CACHE_EV, x
    cmp #$FF
    beq none
    jsr cache_a_to_x
    lda npc_buf + 8, y
    ora #$80
    cmp f:CACHE_KEY, x
    bne none                    ; someone else's by now
    jsr cache_tile
.a16
    asl a
    asl a
    asl a
    asl a
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    clc
    rtl
none:
    sec
    rtl
.endproc

; X: the event in `CACHE_T_EV`, to index `CACHE_EV`. Keeps A.
.proc cache_event_x
.a8
.i16
    pha
    rep #$20
.a16
    lda f:CACHE_T_EV
    and #$00FF
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; X: A, a slot.
.proc cache_a_to_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; X: the cache's last slot, to walk them down to 0.
.proc cache_last
.a8
.i16
    rep #$20
.a16
    lda f:CACHE_N
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    rts
.endproc

; Slot X's first tile in the sprite bank, in A, which comes back in sixteen
; bits.
.proc cache_tile
.a8
.i16
    rep #$20
.a16
    txa
    asl a
    clc
    adc f:CACHE_REC
    tax
    lda f:cache_data + 3, x
    rts
.endproc

.assert CACHE_EV + EV_MAX <= $7E7D00, error, "the cache's events overflow its RAM"
