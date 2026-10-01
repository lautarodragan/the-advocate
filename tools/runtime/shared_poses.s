.segment "FAR"
.a8
.i16

; --- the slots still events take turns in --------------------------------------
;
; A still event shows a single pose, and still events showing the same one
; share its VRAM slot. A map with a crowd —Distant Paradise: fifteen people
; facing three or four ways— asks for more slots than VRAM has even so, with
; most of them far from each other. In such a map, and only there, the
; converter puts in the same slot still events showing **different** poses
; that no position of the camera shows together: `share` in
; `rm2k-snes-map-sprites`, and the decision in
; workflow/decisiones/las-poses-se-suben-en-caliente.md.
;
; So the slot holds whichever pose the console last uploaded. `place_npc`
; asks here before drawing a row of such a map: if the slot holds another
; pose, its own is queued —with `vram_queue`, like every hot-swapped pose—
; and the row **is not drawn that frame**, but the next one, when the pose is
; up. The one that showed the other pose is off screen: the converter
; guarantees it with the same 32x32-box-against-the-screen comparison
; `build_oam` and `place_npc` discard with. A row that comes into view at
; the edge shows up a frame late, which does not show.
;
; What it does not cover: a pose queued when the vblanks have no room for
; poses two frames in a row —a window line uploading while the camera
; scrolls— is drawn before it is up, and for that frame the slot shows the
; previous pose. The hero's and the walkers' poses have the same limit.
;
; The first frame of a map, and the one after a battle, the teleport within
; the map and a load, go through `build_oam_settled`, which uploads the
; queue with the screen off until nothing is missing.
;
; The tables, `share_maps` and `share_data`, are `share_table`'s in
; `rm2k-snes-mapdata`: the record's layout is described there.

; Reset: no map loaded. `place_npc` reads `SHARE_N` and far RAM starts with
; garbage on a console and in bsnes.
.proc share_boot
.a8
.i16
    lda #0
    sta f:SHARE_N
    rtl
.endproc

; From `load_sprite`, which has just uploaded the bank: how many shared slots
; this map has, and nobody knows what they hold.
.proc share_load
.a8
.i16
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:share_maps, x
    tax
    sep #$20
.a8
    lda #0
    cpx #0
    beq set                     ; it shares nothing
    lda f:share_data + 4, x
set:
    sta f:SHARE_N
    lda #$FF
    ldx #SHARE_MAX - 1
forget:
    sta f:SHARE_OWNER, x
    dex
    bpl forget
    rtl
.endproc

; Row X, about to be drawn in a map with shared slots: does its slot hold its
; pose? Carry clear if it can be drawn as it is, with X as it came. Carry set
; if not: `vq_src` and `vq_dest` are its pose and its slot, ready for
; `vram_queue`, and Y carries the slot in its low byte and the pose in its
; high one, for `share_took`. Clobbers A.
.proc share_want
.a8
.i16
    phx
    lda npc_buf + 8, x          ; its event
    ; The one facing the hero is drawn from the turn slot, and its own is not
    ; looked at until it goes back: see `turn_fire`.
    cmp f:TURN_EV
    beq as_is
    rep #$20
.a16
    and #$00FF
    asl a
    pha                         ; 1,s: the event, times two
    lda map_current
    asl a
    tax
    lda f:share_maps, x
    pha                         ; 1,s: its record; 3,s: the event times two
    tax
    lda f:share_data, x         ; where the record's event table starts
    clc
    adc 3, s
    tax
    lda f:share_data, x         ; its slot, and its pose in the high byte
    tay
    and #$00FF
    cmp #$00FF
    beq not_shared              ; it does not take turns
    tax                         ; the slot
    tya
    xba
    sep #$20
.a8
    cmp f:SHARE_OWNER, x
    bne another
    rep #$20
.a16
not_shared:
    pla
    pla
    sep #$20
.a8
as_is:
    plx
    clc
    rtl

another:
    ; Another pose in the slot. Where this one goes: the slot's offset from
    ; the sprites' base, which is the map's.
    rep #$20
.a16
    and #$00FF
    asl a
    pha                         ; 1,s: the pose times two; 3,s: the record
    txa
    asl a
    clc
    adc 3, s
    tax
    lda f:share_data + 5, x     ; the slot's words from the sprites'
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    ; And where it comes from: its place in `npc_poses`, which is the same
    ; table the walkers and the turn read their poses from.
    lda 3, s
    tax
    lda f:share_data + 2, x     ; where the record's pose table starts
    clc
    adc 1, s
    tax
    lda f:share_data, x
    phy
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
    ply                         ; the slot and the pose, for `share_took`
    pla
    pla
    pla
    sep #$20
.a8
    plx
    sec
    rtl
.endproc

; The pose `share_want` asked for got into the queue: the slot holds it from
; the next vblank on. Y as `share_want` left it.
.proc share_took
.a8
.i16
    rep #$20
.a16
    tya
    and #$00FF
    tax
    tya
    xba
    sep #$20
.a8
    sta f:SHARE_OWNER, x
    rtl
.endproc
