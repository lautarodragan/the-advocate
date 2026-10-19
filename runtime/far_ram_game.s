; --- far RAM sized by the game ----------------------------------------------
; The regions of far RAM whose size the cartridge's `.inc` says: they are
; named, with their why, in far_ram.s, which comes before the `.inc` and so
; cannot size them; here they get their `.res`, after it. Until 2026-10-16
; each one had a size chosen for any game, written by hand, and what a game
; did not use of it nobody else could.
.pushseg
.segment "FARBSS"
far_pair_state: .res EV_MAX * PAIR_BYTES
far_pair_list:  .res PARALLEL_MAX * PAIR_LIST_BYTES
; One block, in this order: see `clear_variables`.
far_msg_options: .res 1
far_access:      .res 1
far_hero_speed:  .res 1
far_random:      .res 2
far_variables:   .res VARIABLES_N * 2
far_items:       .res ITEMS_N
; By LDB actor number. **ACTORS_N is the highest number plus one**, and an
; actor number is a byte everywhere —the party, `BA_NUMBER`—, so the
; converter has to keep it under 256 for these tables to be indexed whole.
far_equipment:   .res ACTORS_N * 10
far_hp:          .res ACTORS_N * 2
far_sp:          .res ACTORS_N * 2
far_actor_gfx:   .res ACTORS_N
far_skill:       .res SKILL_BYTES
far_exp:         .res EXP_K * 4
far_page:        .res 16 + TROOP_PAGE_MAX
CACHE_N:         .res $50 + EV_MAX
FAR_EFFECT_IN:   .res SE_PLACES
NPC_ROW_SEPARATE: .res NPC_STRIDE
route_gfx_buf:    .res ROUTE_GFX_MAX * 2
route_gfx_colors: .res ROUTE_GFX_MAX
.popseg
.assert far_variables = far_msg_options + 5, error, "clear_variables walks a block that is not contiguous"
.assert ACTORS_N <= 256, error, "an actor number is a byte: the actors' tables are indexed by it"
