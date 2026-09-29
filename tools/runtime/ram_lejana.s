; --- the RAM in bank 1 ---------------------------------------------------------
; Bank 0's BSS is full —7680 of 7680— and so is the ZEROPAGE, 256 of 256; this
; used to say the ZEROPAGE had twelve to spare and that stopped being true a
; while ago. The console has 128 KB of WRAM and the ROM uses eight: the rest
; is reached through this same window, pointing WMADD and reading or writing
; $2180 with auto-increment. It is not normal addressing —it cannot be
; indexed— so it is good for what is stored and walked a little at a time,
; not for what is drawn.
;
; Today it holds the state of the parallel interpreters: 840 bytes that did
; not fit in bank 0. The day there are RM2k variables —five thousand, ten
; kilobytes— they go here too.
FAR_PAR_ESTADO = $2000      ; EV_MAX entries of PAR_BYTES
FAR_PAR_LISTA  = $2400      ; PARALELO_MAX entries of PAR_LISTA_BYTES
; The RM2k variables, one signed word per slot. How many there are is said by
; the converter —`VARIABLES_N`—, which gives a slot only to the ones named by
; the pages of the maps in the ROM; the bytecode talks in slots. They are read
; and written with `var_leer` and `var_escribir`, and they travel in the save:
; `partida_tabla` copies them from here, which the DMA reaches just like bank
; 0 because WMADD is a seventeen-bit address.
FAR_VARIABLES  = $2600
; And the inventory, after the variables —which are at most 256, the
; converter guarantees it—: one byte per LDB item, indexed by the RM2k number
; —0 is unused— and capped at ITEM_MAX, like `Game_Party::AddItem`. It
; travels in the save and is cleared with the variables.
FAR_ITEMS      = $2800
; And the equipment of each LDB actor, by actor number: five words —weapon,
; shield, armor, helmet, accessory— with the item number or 0. It starts with
; the database's initial equipment, which `equipo_inicial_poner` copies on
; reset, and travels in the save.
FAR_EQUIPO     = $2C00
; And the random state, two bytes before: a sixteen-bit xorshift, the same as
; `azar_siguiente` in eventos.py, seeded on reset. It goes here and not in the
; direct page because the direct page ended up at 258 of 256 when that was
; tried; randomness is asked for rarely and the port does not notice.
FAR_AZAR       = $25FE
; And the hero's speed, 1 to 6, one byte before: move commands 28 and 29 of a
; forced move route raise and lower it and **it stays that way**, for the pad
; too —RM2k only restores the frequency when the move route ends,
; `original_move_frequency`; not the speed—. It travels in the save. It is
; read once per step.
FAR_HERO_VEL   = $25FD
; And the permissions, one byte before: `ChangeSaveAccess`,
; `ChangeMainMenuAccess` and `ChangeEscapeAccess` turn them off and on, and
; bit 7 is RM2k's menu request, `menu_calling`: B sets it and the hero
; handles it when standing still. The bits are stored as "forbidden" so that
; the zero from reset means "everything allowed", which is how RM2k starts.
; It travels in the save, as it does there.
;
; The escape one is stored and **nobody reads it yet**: escaping belongs to
; the battle. It is here because it is one bit and because without it 30 of
; the game's 39 pages with `EnemyEncounter` that fail today do not compile;
; see ACCESO_BIT in eventos.py.
FAR_ACCESO     = $25FC
ACCESO_SIN_GUARDAR = $01
ACCESO_SIN_MENU    = $02
ACCESO_SIN_ESCAPAR = $04
ACCESO_PEDIDO      = $80
; --- the battle: its state in far RAM -------------------------------------------
;
; **Far RAM has a map and it has to be respected.** On 2026-09-12 the picture
; was put at $30E8, which was where the MSU-1 state lived, and the ROM stopped
; detecting the chip: the music went silent and no test saw it. From $2000 to
; $30FA everything is taken —the parallel interpreters, the variables, the
; inventory, the equipment, the weather, the sound effects, the rotation, the
; picture— and from $3100 to $3600 goes the ARAM allocation. So this starts at
; $3700, which is the first place where nobody is.
;
; The HP of each LDB actor, one word per actor number. **They are real state
; since there are battles**: until 2026-09-12 nobody went below their maximum
; and `ChangeHP` compiled to nothing. They travel in the save, after the
; equipment, and reset fills them up.
FAR_HP = $3700

; Far RAM with the bank in front, for the few who read it from outside with
; `lda f:`: it is the same as `BAT_LARGO`, which kept a battle name.
FAR_LARGO = $7E0000

; And the SP, which are state for the same reason as the HP since skills can
; be used: each one costs its `sp_cost` and `Scene_Battle` deducts it from
; whoever uses it. They start full from `actor_spmax` and travel in the save,
; after the HP. `FAR_HP` is ACTORES_N words —61 actors, 122 bytes— so it
; reaches $3779; this starts at $3780 and ends before $3800.
FAR_SP = $3780

; And which graphic a `ChangeSpriteAssociation` changed each LDB actor's
; sprite to, one byte per actor number: the index in the map's graphics table
; —the same one move command 34 of a move route resolves— or $FF if it keeps
; the LDB one. It travels in the save, as in RM2k, and **survives the
; teleport**: that is what sets it apart from move command 34 on the hero,
; which is restored on load.
;
; It goes at $3800 and the battle moves to $3A00. It could have gone right
; after `FAR_HP` —today there is more than enough room up to $37FF— but then
; its address would depend on `ACTORES_N`, which the converter emits, and the
; far RAM map would be at the mercy of a number not written here. See above:
; this map was stepped on once already and the music was silent for a whole
; day.
FAR_ACTOR_GRAF = $3800
ACTOR_GRAF_NINGUNO = $FF

; And which skills each actor knows, since 2026-09-21: one bit per (actor,
; skill) pair, with the slot the converter gave each pair —see
; `HABILIDAD_RANURA` in eventos.py—. It starts with what the LDB says for the
; initial level, which `hab_inicial_poner` copies on reset, `ChangeSkills`
; sets and clears it, and it travels in the save. How many bytes it takes is
; said by `HAB_BYTES`, and the converter stops if they go past 256.
;
; **$6000 to $60FF belongs to this**: the range was reserved in advance, when
; splitting work among three jobs that ran at the same time and touched far
; RAM.
FAR_HAB = $6000

; --- random encounters: their state in far RAM -------------------------------
;
; Nine bytes at $3900, which is the gap left between `FAR_ACTOR_GRAF` —61
; bytes from $3800— and the battle. **It does not travel in the save**, just
; as the HP of an unfinished battle do not: on load, the accumulated count
; starts at zero, which is the same thing that happens on entering a map.
;
; It did not fit in bank 0: the BSS is at 7680 of 7680, measured on
; 2026-09-13 by adding a `.res 64` and looking at the assembler's cut.
FAR_ENCUENTRO = $3900
ENC_N     = FAR_ENCUENTRO + 0   ; steps taken since the last encounter
ENC_IDX   = FAR_ENCUENTRO + 1   ; the table row, which never goes down
ENC_PIDE  = FAR_ENCUENTRO + 2   ; one came up and is collected next frame
ENC_SEM   = FAR_ENCUENTRO + 3   ; word: the xorshift, with its own seed
ENC_BASE  = FAR_ENCUENTRO + 5   ; word: 1/steps in 1/65536; 0 is off
ENC_REG   = FAR_ENCUENTRO + 7   ; this map's record, or ENC_SIN
; A map with no troops of its own and no areas covering it.
ENC_SIN   = $FF
; The eight rows of `UpdateEncounterSteps`'s table, and how many threshold
; bytes each record carries: seven —row 0's is 0 and is not stored— plus one
; of padding, so that the index is a shift and not a multiplication.
ENC_FILAS  = 8
ENC_STRIDE = 8
; The current map's thresholds, copied from `enc_umbral_n` on entry: the step
; at which each row is crossed, from 1 to 7. They live in RAM and are not
; read from the table because `ChangeEncounterSteps` changes them along with
; `ENC_BASE`: the chance and the rows come from the same `encounter_steps`.
;
; $7E79C0 to $7E79C7, out of what was allotted to world milestone 2 on
; 2026-09-27 —$79C0 to $79DF—. Like the rest of the encounters, with a
; sixteen-bit address: it is read with the data bank at $7E.
ENC_UMB   = $79C0
.assert ENC_UMB + ENC_STRIDE <= $79E0, error, "the thresholds overflow their range"

; --- experience and level: their state in far RAM ----------------------------
;
; Four bytes per actor who can fight, in the order of the converter's
; `experiencia_ranuras` —`actor_exp_k` says which one each actor number gets,
; or $FF—: the 24-bit experience, which in RM2k reaches 999999, and the level.
; Having the level right next to the experience is what makes the save carry
; a single line for both. It starts from `exp_inicial` on reset and travels
; in the save.
;
; $6200 to $63FF is the place given to this on 2026-09-21, split among three
; branches: the map above ends at the battle, which does not go past $3CFF.
FAR_EXP     = $6200
EXP_NIVEL   = 3             ; the level, the fourth byte
; And, at the end of the same place, eight bytes where `texto_nivel` and its
; siblings compose the level and the maximum the menu writes: they are
; numbers from the save and no longer strips from the cartridge. The slots
; reach 128 before stepping on them, and the converter stops much earlier:
; see `experiencia_asm`.
EXP_TEXTO   = $7E63F8
; RM2k's `MaxExpValue()`, in its two halves.
EXP_TOPE_HI = $0F
EXP_TOPE_LO = $423F

; --- troop pages: their state in far RAM --------------------------------------
;
; $6400 to $65FF is the place given to this on 2026-09-21. **It does not
; travel in the save**, like nothing in the battle. It is named with a
; sixteen-bit address, same as `FAR_BATALLA`, because the battle code reads
; it with the data bank at $7E; the bridge from bank 0 puts `BAT_LARGO` in
; front of it.
FAR_PAG       = $6400
BA_PAG_N      = FAR_PAG + 0     ; how many pages this battle's troop brings
BA_PAG_INI    = FAR_PAG + 1     ; word: the first, in the `tpag_*` tables
BA_PAG_COD    = FAR_PAG + 3     ; word: where the running one starts, in the
                                ; bank of `tropa_codigo`
BA_PAG_CUR    = FAR_PAG + 5     ; word: its cursor, its own `ev_cur`
BA_PAG_ACT    = FAR_PAG + 7     ; whether it has not finished yet: its `ev_activo`
BA_PAG_MSG    = FAR_PAG + 8     ; word: the message it asked for and is on
                                ; screen, in `mensajes_tropa`, or $FFFF
BA_PAG_VUELTA = FAR_PAG + 10    ; where the battle goes on when none are left:
                                ; 0 the next action, 1 ask for the commands
BA_PAG_I      = FAR_PAG + 11    ; which one the sweep is on
BA_PAG_G      = FAR_PAG + 12    ; word: that same one, in the `tpag_*` tables
BA_PAG_HECHA  = FAR_PAG + 16    ; TROPA_PAG_MAX bytes: already ran this turn
; And what the turn and HP conditions and the commands that come with them
; added, on 2026-09-28: $7E7A10 to $7E7A3F, which is what was allotted to
; this. With a sixteen-bit address, like the rest of the battle.
BA_TURNO      = $7A10           ; word: the turn, `Game_Party::GetTurns`
BA_PAG_ESPERA = $7A12           ; word: frames left in the wait of the
                                ; running page
BA_PCT_MIN    = $7A14           ; the HP range, in percent, that is checked
BA_PCT_MAX    = $7A15
BA_P24        = $7A16           ; three bytes: what `ba_mul24` leaves
BA_P_HP       = $7A19           ; three bytes: a hundred times the HP checked
BA_PAG_FL     = $7A1C           ; the triggers of the page being tested
; And its header, copied from in front of its code: `eventos.cabecera_de_tropa`,
; in the same order.
BA_COND       = $7A20
BA_COND_BASE  = 0               ; word: the turn base, `turn_b`
BA_COND_MULT  = 2               ; word: and its multiple, `turn_a`
BA_COND_ENE   = 4               ; the enemy's place in the troop
BA_COND_EMIN  = 5               ; and its HP range, in percent
BA_COND_EMAX  = 6
BA_COND_ACT   = 7               ; the actor, by LDB number
BA_COND_AMIN  = 8
BA_COND_AMAX  = 9
.assert BA_COND + TPAG_CABECERA <= $7A40, error, "the pages' state overflows its range"

; --- a medicine outside battle: its scratch space in far RAM -----------------
;
; $6800 to $68FF belongs to this, reserved on 2026-09-21 when splitting.
; **It does not travel in the save**: it lasts as long as one A press in the
; actor choice. It is named with a sixteen-bit address because
; `medicina_usar` runs with the data bank at $7E.
FAR_MED       = $6800
MED_ACTOR     = FAR_MED + 0     ; the actor, by LDB number
MED_BANDERAS  = FAR_MED + 1     ; the item's `item_medicina` bits
MED_USADO     = FAR_MED + 2     ; whether it worked: easyrpg's `was_used`
MED_REVIVIO   = FAR_MED + 3     ; word: 1 if it revived it, the `revived`
MED_HP_MAX    = FAR_MED + 5     ; word: the max HP for its level
MED_SP_MAX    = FAR_MED + 7     ; word: and the SP
MED_HP        = FAR_MED + 9     ; word: the `hp_change`
MED_SP        = FAR_MED + 11    ; word: the `sp_change`
MED_P         = FAR_MED + 13    ; four bytes: the product, and the quotient
MED_R         = FAR_MED + 17    ; word: the remainder
MED_ID        = FAR_MED + 19    ; word: the item's RM2k number
; The `item_medicina` bits, which the converter emits. `medicina_usar` writes
; them by number; the battle, which reads them since 2026-09-26, by name.
MED_KO_ONLY   = $01             ; only on a fallen one
MED_LEVANTA   = $02             ; removes the dead state: revives the fallen one

; What `par_ev` holds while a troop page runs: neither the foreground ($FF)
; nor a map event, which are fewer than EV_MAX. It is what tells
; `op_message` that the message belongs to the battle. See `ba_t_pagina`.
PAR_PELEA = $FE
.assert EV_MAX < PAR_PELEA, error, "PAR_PELEA must not be an event"

; And the battle state, which does **not** travel in the save: a battle cannot
; be saved in RM2k either.
FAR_BATALLA = $3A00
; The same address but long, for the few who touch it from outside the
; battle: `op_battle` runs with the bytecode's data bank.
BAT_LARGO = $7E0000
; **Everything here is named with a sixteen-bit address, not a long one**,
; and the battle code runs with the data bank at $7E. That is what lets it use
; absolute addressing: `inc`, `stz`, `ldx` and `cpy` have no long mode, so
; with `f:` each one would have to go through the accumulator. And it costs
; nothing to the rest: in bank $7E the addresses $0000 to $1FFF **are** bank
; 0's low RAM, so `temp`, `comp_*` and `grupo` are still read as always. What
; does change are the ROM tables, which go with `f:`.
BA_TROPA   = FAR_BATALLA + 0      ; the troop, as an RM2k number
BA_RESULT  = FAR_BATALLA + 2      ; 0 victory, 1 escape, 2 defeat
BA_SEM     = FAR_BATALLA + 3      ; the battle's xorshift, with its own seed
BA_NACT    = FAR_BATALLA + 5      ; how many actors
BA_NENE    = FAR_BATALLA + 6      ; how many enemies
BA_MODO    = FAR_BATALLA + 7
BA_ACTOR   = FAR_BATALLA + 8      ; who is being asked for a command
BA_ORDEN   = FAR_BATALLA + 9      ; which command the cursor marks
BA_BLANCO  = FAR_BATALLA + 10     ; which enemy the cursor marks
BA_HUIDA   = FAR_BATALLA + 11     ; the chance to escape, which rises on failing
BA_I       = FAR_BATALLA + 12     ; which one of the execution the turn is on
BA_ESPERA  = FAR_BATALLA + 13     ; frames the message has left
BA_MTIPO   = FAR_BATALLA + 14     ; what the message says
BA_MQUIEN  = FAR_BATALLA + 15
BA_MBLA    = FAR_BATALLA + 16
BA_MDANO   = FAR_BATALLA + 17     ; word
BA_NACC    = FAR_BATALLA + 19     ; how many actions the turn has
BA_T0      = FAR_BATALLA + 20     ; scratch words, which anyone clobbers
BA_T1      = FAR_BATALLA + 22
BA_T2      = FAR_BATALLA + 24
BA_S0      = FAR_BATALLA + 26     ; and the ones that survive a `jsr`
BA_S1      = FAR_BATALLA + 28
BA_S2      = FAR_BATALLA + 30
BA_S3      = FAR_BATALLA + 32
BA_S4      = FAR_BATALLA + 34
BA_S5      = FAR_BATALLA + 36
BA_S6      = FAR_BATALLA + 38
; Whether the line being composed also shows the max HP, that is, whether it
; belongs to the party. It has its own byte and not a borrowed `BA_T2 + 2`,
; which is what it was and it landed right on top of `BA_S0`: the enemy loop
; restarted by itself and the screen never got to appear.
BA_CONMAX  = FAR_BATALLA + 40
; The battle's audio, in the bytes that were left loose before `BA_ACC`.
; `BA_TEMA_ANT` is the song that was playing on the map —$FF if nothing was—,
; which is RM2k's `before_battle_music`: when the battle ends it comes back.
; `BA_SE2` is the sound effect still to fire in the current message, or
; $FFFF: RM2k plays two per hit —the attack's and the damage's, separated by
; a wait— and here the second goes out when `BA_ESPERA` reaches
; `BA_SE2_CUADROS`.
BA_TEMA_ANT = FAR_BATALLA + 41
BA_SE2      = FAR_BATALLA + 42     ; word
; Whether there is a scene in BG1 —0— or this battle goes on black —$FF—: no
; background and no battler. See `escena_subir`.
BA_ESCENA   = FAR_BATALLA + 44
; And at which place in `tropa_id` this battle's troop landed, which is what
; `escena_tropa_fondo` indexes. $FF: the cartridge does not carry it.
BA_TROPA_K  = FAR_BATALLA + 45
; And the item being used, since 2026-09-13. It goes **after `BA_UNO`**,
; which ends at +575, because between +40 and +48 nothing is left and moving
; `BA_ACC` would mean moving everything else.
;
; It was at +320 until `BA_BYTES` went from 18 to 40 —the SP and the four
; parameter modifiers of the skills— and `BA_UNO` ran into it.
BA_ITEM_N    = FAR_BATALLA + 576   ; how many are in the list
BA_ITEM_SEL  = FAR_BATALLA + 577   ; which one the cursor marks
BA_ITEM_ARR  = FAR_BATALLA + 578   ; the first one visible
BA_ITEM_BLA  = FAR_BATALLA + 579   ; which actor it is given to; since 2026-09-13
                                   ; also the target of a healing skill,
                                   ; which picks with the same mode
BA_MITEM     = FAR_BATALLA + 580   ; the `k` of the current message's item
BA_ACTOR2    = FAR_BATALLA + 581   ; an actor counter `BA_S0` cannot be
BA_MCURA     = FAR_BATALLA + 582   ; word: how much it healed
BA_ACC_ITEM  = FAR_BATALLA + 584   ; the `k` each actor chose, one per byte
BA_ITEM_LISTA = FAR_BATALLA + 592  ; the list, one `k` per byte
BA_ITEM_MAX = 64
; --- skills, since 2026-09-13 ---------------------------------------------
;
; After `BA_ITEM_LISTA`, which ends at +656.
BA_HAB_N     = FAR_BATALLA + 656   ; how many the one giving commands knows
BA_HAB_SEL   = FAR_BATALLA + 657   ; which one the cursor marks
BA_MHAB      = FAR_BATALLA + 658   ; the `k` of the current message's one
BA_ACC_HAB   = FAR_BATALLA + 660   ; the `k` each actor chose, one per byte
BA_HAB_LISTA = FAR_BATALLA + 672   ; their list, one `k` per byte
BA_HAB_MAX   = 16                  ; BA_HAB_FILAS times BA_HAB_COLUMNAS, with room to spare
BA_MEFECTO   = FAR_BATALLA + 688   ; signed word: how much the last one did
BA_ACC     = FAR_BATALLA + 48     ; two bytes per combatant: command and target
BA_EJEC    = FAR_BATALLA + 72     ; the execution order, one combatant per byte
BA_CAND    = FAR_BATALLA + 88     ; the living on one side, to pick a target
BA_UNO     = FAR_BATALLA + 96     ; the combatants, BA_BYTES each
; Whether the current message's item revived a fallen one: the second line
; changes. **Outside `FAR_BATALLA`**, at $7E7850-$7E785F, which is what was
; allotted to this on 2026-09-26 —other agents were choosing RAM at the same
; time—. Like everything in the battle, with a sixteen-bit address and the
; data bank at $7E.
BA_MREVIVIO = $7850

; The combatants: the first four are the party and the next eight the troop.
; That the place is fixed and not a compacted list is what keeps a dead one
; visible in its line, as on the screen.
BA_GRUPO_MAX = 4
BA_ENEMIGOS_MAX = 8
BA_COMB_MAX = BA_GRUPO_MAX + BA_ENEMIGOS_MAX
; It was 18 until 2026-09-13, which is when the SP came in along with the
; four parameter modifiers that two of the party's seven skills move. 40 is
; also convenient: the offset comes out of five `asl` and an addition, see
; `ba_x`.
BA_BYTES  = 40
BA_HP     = 0               ; word
BA_HPMAX  = 2
; **The four parameters here are the effective ones**, that is,
; game_battler.cpp's `AdjustParam`: `clamp(base + modifier, 1, 999)`. The
; base and the modifier live further down and are stored whole because a
; modifier that survives the clamp cannot be recovered from the subtraction;
; `ba_mod` recomputes them.
BA_ATK    = 4
BA_DEF    = 6
BA_AGI    = 8
BA_SORT   = 10              ; the `agi + random` the turn is sorted by
BA_TXT    = 12              ; the text number of its name
BA_HIT    = 14              ; byte
BA_CRIT   = 15
BA_FLAGS  = 16
BA_NUMERO = 17              ; the LDB actor, or the place in the troop
BA_SP     = 18              ; word: the SP it has left
BA_SPMAX  = 20
BA_MATK   = 22              ; the four modifiers, signed
BA_MDEF   = 24
BA_MSPI   = 26
BA_MAGI   = 28
BA_BATK   = 30              ; and the four bases
BA_BDEF   = 32
BA_BSPI   = 34
BA_BAGI   = 36
BA_SPI    = 38              ; the effective spirit, which `CalcSkillEffect` asks for
BAF_DEF   = $01             ; it is defending
BAF_ACTOR = $02             ; it belongs to the party
BAF_HAY   = $04             ; the slot is taken
; A hidden enemy —`invisible` in the troop— takes its place but **does not
; have `BAF_HAY`**: that way everything that looks at who is there
; —`ba_vivo`, and with it the target, the actions, the victory and the
; scene— skips it without knowing anything about hidden ones, which is what
; `Exists()` does in easyrpg. `ShowHiddenMonster` swaps one bit for the
; other: see `ba_mostrar_oculto`.
BAF_OCULTO = $08

; The three results and the three commands, in the order of `tools/port/batalla.py`.
BA_VICTORIA = 0
BA_HUIDA_R  = 1
BA_DERROTA  = 2
BA_ATACAR   = 0
BA_DEFENDER = 1
BA_HUIR     = 2
BA_ITEM     = 3
BA_HABILIDAD = 4
; The screen modes, like `pantallas.BA_ELIGE_ORDEN` and company. **The order
; matters**: more than one place asks `cmp #BA_M_MENSAJE / bcs` to say
; "message or end", so the ones that choose something all go first.
BA_M_ORDEN  = 0
BA_M_BLANCO = 1
BA_M_ITEM   = 2
BA_M_ACTOR  = 3
BA_M_HAB    = 4
BA_M_MENSAJE = 5
BA_M_FIN    = 6
; Running a troop page, with or without its message on screen: see
; `modo_pagina`. It goes after the message ones because it chooses nothing.
BA_M_PAGINA = 7
; What the message says.
BA_MSG_ATAQUE = 0
BA_MSG_DEFIENDE = 1
BA_MSG_NO_HUYO = 2
BA_MSG_HUYO = 3
BA_MSG_VICTORIA = 4
BA_MSG_DERROTA = 5
BA_MSG_ITEM = 6
BA_MSG_HAB = 7
; How many frames a message stays if nobody presses A. Two seconds, which is
; how long a line takes to read, and A skips it.
BA_MSG_CUADROS = 120
; When the hit's second sound effect goes out: `Scene_Battle_Rpg2k` plays the
; attack's when the action starts and the damage's in the message sub-state,
; with a `SetWait(4,4)` in between. Here the message lasts `BA_MSG_CUADROS`
; and the second sound effect goes out twenty-four frames later. The
; twenty-four were chosen when sound effects had a single voice and the new
; one cut off the previous one's voice, so they had to stay apart by ear;
; since 8c9c182 they are two voices —see `efectos_de_sonido.s`— and two
; different sound effects no longer cut each other off; the same sound effect
; twice does, because `sonido_tocar` fires it again on the voice that is
; already playing it.
BA_SE2_CUADROS = BA_MSG_CUADROS - 24
; The hit rate of an actor with no weapon that changes it:
; `Game_Actor::GetHitChance`.
BA_ACIERTO_ACTOR = 90
; The damage cap —RM2k's `MaxDamageValue()`— and the cap on the average
; agility that goes into the escape computation: two hundred times the
; average has to fit in sixteen bits, and the game's most agile enemy has
; 300.
BA_DANO_MAX = 999
BA_AGI_TOPE = 320
; The cap on an effective parameter: `Game_Actor::GetAtk` and its siblings,
; that is, RM2k's `MaxStatBattleValue`.
BA_PARAM_MAX = 999
; `rpg::Skill::Type_switch`, the one that turns on a switch and does nothing
; else. It is the only type this port tells apart from normal: the seven the
; intro party knows are either `normal` or `switch`.
BA_HAB_TIPO_SWITCH = 3
; The five scopes of `rpg::Skill::Scope`, which is what `hab_alcance` carries.
; Only `enemy` and `ally` ask for a target when chosen; for the other three
; the scope decides it: see `batalla.blancos_de_la_habilidad`.
BA_ALCANCE_ENEMIGO  = 0
BA_ALCANCE_ENEMIGOS = 1
BA_ALCANCE_UNO      = 2
BA_ALCANCE_ALIADO   = 3
BA_ALCANCE_GRUPO    = 4
; An enemy action that is not a skill: the basic attack, in `eacc_hab`, and
; what `ba_accion_enemiga` answers when it has none left. See
; `batalla.accion_del_enemigo`.
BA_EACC_ATACAR = $FF
BA_EACC_NADA   = $FE
BA_EACC_NO_EFECTIVA = $80       ; the `eacc_peso` bit

; Cursor (2), wait (2), whether it is running (1) and from which page (2).
; **Eight and not seven**: the index comes out of three `asl` instead of an
; `x * 8 - x`, which is six bytes of bank 0 and a few cycles for every
; parallel and every frame. EV_MAX times eight is 960 bytes, so it still fits
; below `FAR_PAR_LISTA`.
PAR_BYTES = 8
; And the eighth, which was spare, is the event's move route slot plus one,
; or zero if it has none: `ranura_anotar` sets it when one is given, and
; `limpiar_paralelos` clears it when loading the map, next to `load_npcs`,
; which is where they are all freed. Within a map a slot is never released.
; It is what saves each parallel from looking for its own every frame: see
; `un_paralelo`.
PAR_RANURA = 7

; And what the parallel list keeps for each one: the event (1), the pointer
; to its bytecode (3) and which page it came from (2). The last three are
; what used to be fetched again from the cartridge every frame and for every
; parallel, with `pagina_desde_eleg`: twenty-four bytes of page header read
; through the bank window, to answer the same as the time before. The list is
; rebuilt whole in `aplicar_paginas`, that is, exactly when the active page
; may have changed, so recording it there is the same answer and only once.
; Eight for the same reason as `PAR_BYTES`: the two spare ones are paid for
; in far RAM, of which there is plenty, and saved in bank 0 and in cycles.
; PARALELO_MAX times eight is 384 bytes and up to `FAR_AZAR` there are 508.
PAR_LISTA_BYTES = 8
WMADDL   = $2181
WMADDM   = $2182
WMADDH   = $2183

; VRAM is addressed in words and it is 64 K in total. How it is split among
; the background tiles, the upper layer's, the sprites' and the two tilemaps
; is not here: the converter decides it map by map and it arrives in
; mapdata.inc, together with the already-built values of OBSEL and BG12NBA.
;
; It is not a convenience: the map that spends the most background tiles
; needs 620, and another with many characters needs 512 for sprites. The two
; together do not fit, and neither of the two layouts works for every map.

; Mode 3's priority order, front to back, is
;   objects 3 / BG1 1 / objects 2 / BG2 1 / objects 1 / BG1 0 / objects 0
; so with the map on BG1 priority 0, the hero on objects priority 1 and the
; upper layer on BG2 priority 1, RM2k's order comes out of the hardware
; without any trick. Events marked "above" go on objects priority 2, which is
; the only thing left above BG2.
; In the OAM attribute byte —vhoopppN— the priority is bits 5 and 4, so the
; value is shifted four places: priority 1 is $10 and not $20. With $20 the
; hero ended up on priority 2, which in this order is *in front of* BG2 1,
; and so it was drawn over the layer that was supposed to cover it.
;
; Both values are built by the converter —each NPC's already comes in its
; attribute byte— and the hero's arrives as HERO_PRIORITY in mapdata.inc.
; Having them here as well was the usual duplication: two sides that can be
; wrong the same way and a comparison that gives zero. The hero's is $10 in
; every ROM except `snes-encima`'s, which raises it to $20 to exercise
; priority 2.

; RM2k poses are 24x32 and the SNES has no such size, so the 32x32 object is
; used and a bit is left over on the sides. The OBSEL value, which carries
; that size and the tile page, is built by the converter.

; The 12 poses: 3 walking frames times 4 directions. In RM2k the directions
; go 0=up, 1=right, 2=down, 3=left, and the middle frame is the standing
; pose.
DIR_UP    = 0
DIR_RIGHT = 1
DIR_DOWN  = 2
DIR_LEFT  = 3

; At speed 4, which is the hero's, it moves two pixels per frame and the
; animation changes frame every six.
; WALK_SPEED no longer exists: the hero moves according to its speed, see
; `paso_medio_por_vel`. The line stays so nobody goes looking for it.
; ANIM_FRAMES = 6 was how many frames the walking frame changed every; now it
; depends on the hero's speed: see `anim_por_vel`.

; The sprite is drawn centered over its 16x16 cell and resting on its feet.
; From the 32 object the 4 spare on each side have to be subtracted as well.
SPRITE_OFF_X = 8
SPRITE_OFF_Y = 16

; --- the map window --------------------------------------------------------
; The PPU tilemap is 64x32 cells, that is 512x256 pixels, and the screen is
; 256x224. The whole map does not fit: the game's go up to 1000x80 cells.
; What is in VRAM is a window that moves with the camera.
;
; The window does not shift: it is treated as a torus. Map cell (mx,my)
; always lives in slot (mx mod 64, my mod 32), and the hardware scroll
; already wraps around by itself because 1024 —the register's maximum— is a
; multiple of 512. So when the camera crosses a cell edge, only the column or
; row that just came in has to be rewritten: the one going out is 32 columns
; or 4 rows off screen and nobody looks at it in the meantime.
WINDOW_COLS = 64
WINDOW_ROWS = 32

; How many 8x8 cells the screen can touch. Exactly 32 and 28 plus one,
; because the scroll almost never lands squarely on a cell.
VIEW_COLS = 33
; How many extra columns are kept loaded on each side of the screen. It is
; for the screen shake, which moves the drawing up to 19 pixels without
; moving the camera: with no margin, the column peeking in from the left is a
; torus slot nobody wrote. Four are 32 pixels, and the torus has 64 columns
; for 33 visible, so there are plenty to spare.
MARGEN_COLS = 4

; --- the spare strips, in far RAM -------------------------------------------
;
; The camera uncovers up to **two** rows or two columns per tick —see
; `stream_map`—, so two strips have to be built at once and the vblank
; uploads both. The second set lives here and not in bank 0 because it does
; not fit there: the BSS has 84 bytes left and this asks for 384.
;
; $6A00 to $6B7F belongs to this, reserved on 2026-09-22. **It does not
; travel in the save**: it lasts one frame.
FAR_TIRA_ROW  = $7E6A00         ; WINDOW_COLS * 2
FAR_TIRA_ROW2 = $7E6A80         ; and the upper layer, adjacent as in bank 0
FAR_TIRA_COL  = $7E6B00         ; WINDOW_ROWS * 2
FAR_TIRA_COL2 = $7E6B40
; Adjacent, which is what `push_una_fila` takes advantage of to reach the
; upper layer's by adding the length of the other, same as with the bank 0
; ones.
.assert FAR_TIRA_ROW2 = FAR_TIRA_ROW + WINDOW_COLS * 2, error, "row strips not adjacent"
.assert FAR_TIRA_COL2 = FAR_TIRA_COL + WINDOW_ROWS * 2, error, "column strips not adjacent"

; --- where the background tilemap is, in far RAM ----------------------------
;
; The VRAM word of the loaded map's BG1 tilemap. `cargar_mapa` copies it from
; `M_VRAM_MAP` and `build_column` and `build_row` add it, since they cannot
; read the table because X is in use. It is $5800 in every layout but one:
; see LAYOUT_VENTANA_AMBOS. It does not fit in the BSS.
;
; $6B80 and $6B81 belong to this, reserved on 2026-09-25. **It does not
; travel in the save**: loading it loads the map, and that sets it again.
FAR_VRAM_MAPA = $7E6B80

; --- the flash palettes, in far RAM -----------------------------------------
;
; One per flash slot, thirty-two bytes each, and the vblank uploads all the
; ones left pending. It has to be one per slot: with a single one, two live
; flashes in the same frame overwrote each other, the last one's was
; uploaded, and the frame that turns off the first never reached CGRAM. They
; do not fit in the BSS.
;
; $6900 to $69FF belongs to this, reserved on 2026-09-23. **It does not
; travel in the save**: it lasts one frame.
FAR_FLASH_PAL = $7E6900         ; FLASH_MAX * 32
.assert FLASH_MAX * 32 <= $100, error, "the flash palettes overflow their range"

; --- the music decoder, in far RAM -------------------------------------------
;
; The state of `music_frame`, which expands the per-note stream into DSP
; writes: see "el formato por nota" in tools/audio/snes_music.py. It is read
; and written by `irq_musica`, which lands at any point in the main code, so
; it is reached with long addressing and never through the WMADD window.
;
; $6C00 to $6FFF belongs to this, reserved on 2026-09-26. **It does not
; travel in the save**: starting the song zeroes it.
;
;   MUS_SOMBRA   the last thing the stream wrote to each voice register,
;                indexed by the register number —$v0 to $v7—, and in $v8,
;                which is ENVX and is not written, the release GAIN of the
;                sound of the voice's last note
;   MUS_ESPERA   word: how many frames until the stream is read
;   MUS_KON      the voices that got a note in the frame being read
;   MUS_SONANDO  the ones keyed on when the previous one closed: released on opening
;   MUS_BASE     word: where the song's sounds start in `musica_sonidos`
;   MUS_VISTAS   the voices that have had a note since the song started
;   MUS_GAINS    the ones that have already received a GAIN
;   MUS_BIT      the voice bit of the event being read
;   MUS_T        scratch word
FAR_MUSICA   = $7E6C00
MUS_SOMBRA   = FAR_MUSICA
MUS_ESPERA   = FAR_MUSICA + $80
MUS_KON      = FAR_MUSICA + $82
MUS_SONANDO  = FAR_MUSICA + $83
MUS_BASE     = FAR_MUSICA + $84
MUS_VISTAS   = FAR_MUSICA + $86
MUS_GAINS    = FAR_MUSICA + $87
MUS_BIT      = FAR_MUSICA + $88
MUS_T        = FAR_MUSICA + $89
; The bytes from MUS_ESPERA to MUS_T, which `musica_limpiar` zeroes.
MUS_ESTADO_BYTES = $0B
; The log of what the stream asks of the DSP: `dsp_musica` records each
; (register, value) pair here if MUS_BITACORA_SI is not zero, and
; MUS_BITACORA_I is where the next one goes, in bytes. It is the net of
; `test_musica_escrituras.py`: the test turns it on and reads it frame by
; frame. It wraps around at 512 bytes, 256 writes, and a music frame does not
; go past a hundred. Each music frame starts with a mark, register
; MUS_BITACORA_MARCA —which the DSP does not have—: the IRQ of a heavy frame
; ends after the emulator has delivered the frame, and without the mark its
; last writes would look like they belong to the next one.
MUS_BITACORA_MARCA = $FF
MUS_BITACORA_SI = FAR_MUSICA + $F0
MUS_BITACORA_I  = FAR_MUSICA + $F2     ; word
MUS_BITACORA    = FAR_MUSICA + $200
MUS_BITACORA_LARGO = $200
.assert MUS_BITACORA + MUS_BITACORA_LARGO <= $7E7000, error, "the log overflows its range"

; The `FadeOutBGM` factor on the voices' volume, from 0 to 256 —256 is full
; volume—: this frame's and the previous one's, which is the one the DSP has.
; `bgm_fundido_tick` writes them and the music reads them, both inside
; `irq_musica`. See `volumen_al_dia`.
;
; $7860 to $7863, out of what was allotted to this on 2026-09-26 —$7860 to
; $786F—: other agents were choosing RAM at the same time.
FUNDIDO_N     = $7E7860          ; word
FUNDIDO_ANTES = $7E7862          ; word

; --- the battle animation frame, in far RAM ---------------------------------
;
; The 2 KB of the frame the vblank uploads to the box. The cartridge does not
; store them whole —only the tiles that are not all zero, see
; `cuadro_sin_vacios` in snes_convert.py— and `anim_cuadro_armar` rebuilds
; them here, outside the vblank. The DMA in `animacion_dibujo_dma` comes from
; here and not from the cartridge.
;
; $7000 to $77FF belongs to this, reserved on 2026-09-26. **It does not
; travel in the save**: loading a map zeroes it.
ANIMB_BUF = $7E7000

; --- LZ2: what the cartridge carries compressed, in WRAM --------------------
;
; See `lz2_descomprimir` in descomprimir.s. Reserved on 2026-09-26:
;
;   $7E7800  the literal's `mvn` trampoline, four bytes built with each
;            call's banks, and the output bank
;   $7F0000  the load buffer: each tile block is decompressed here and
;            uploaded to VRAM with the same DMA as before. It is valid only
;            while loading; the battle scene uses all of bank $7F —see
;            `ESC_LIMPIO`—, and nothing here has to outlive it
;   $7F6000  the drawings of the map's ChipSet animation, which `anim_subir`
;            uploads every time the clock changes: **they live as long as
;            one is on the map**, and that is why they go above the buffer
;            and are decompressed after the background tiles and before the
;            upper layer and the sprites. What does take them away is the
;            battle, and `volver_al_mapa` decompresses them again
;
; The limits of each block are enforced by `descomprimir.s` against the ones
; the converter emits.
LZ2_TRAMPA_LIT = $7E7800        ; mvn output, stream; rtl
LZ2_BANCO      = $7E7804        ; the output bank

; --- what the victory counts -------------------------------------------------
;
; $7E7810 to $7E781F, reserved on 2026-09-26: the "N EXP" and "Level up!"
; pages of `batalla_victoria.s`. Like `FAR_BATALLA`, they are named with a
; sixteen-bit address because the battle reads them, with the data bank at
; $7E. `ba_vic_empezar` writes all of them on winning and nobody reads them
; before, so there is no need to set them to anything at startup.
BA_VIC        = $7810
BA_VIC_ACTOR  = BA_VIC + 0      ; whose page it is, or $FF the first
BA_VIC_ANTES  = BA_VIC + 1      ; the level before winning, one per party
                                ; slot; 0 if it has no experience
BA_VIC_SALTEAR = BA_VIC + 5     ; the skill lines from earlier pages of the
                                ; same actor
BA_VIC_SIG    = BA_VIC + 6      ; this one's and the earlier ones': what
                                ; the next one skips
BA_VIC_MAS    = BA_VIC + 7      ; whether skills were left for another page
BA_VIC_FIN    = BA_VIC + 8
.assert BA_VIC_FIN <= $7820, error, "the victory's state overflows its range"

; --- what the enemies dropped ------------------------------------------------
;
; $7E79E0 to $7E79FF, reserved on 2026-09-27: the items the victory won, so
; its page can list them. Like `BA_VIC`, with a sixteen-bit address, and
; `ba_vic_botin` writes them on winning before anyone reads them.
BA_BOTIN      = $79E0
BA_BOTIN_N    = BA_BOTIN + 0    ; how many
BA_BOTIN_K    = BA_BOTIN + 1    ; the `k` of each one, in troop order:
                                ; its name is text `3k`
BA_BOTIN_FIN  = BA_BOTIN_K + BA_ENEMIGOS_MAX
.assert BA_BOTIN_FIN <= $7A00, error, "what the enemies dropped overflows its range"

; --- experience in the menu --------------------------------------------------
;
; $7E7A40 to $7E7A4F, reserved on 2026-09-28: the thirteen letters of the
; experience line of a party row, which `menu_exp_pintar` builds before
; turning them into sprites. It lives as long as that routine.
MENU_EXP_TEXTO = $7E7A40
MENU_EXP_TEXTO_FIN = $7E7A50

; --- the MSU-1 tracks that were missing --------------------------------------
;
; $7E7820 to $7E782F, reserved on 2026-09-26: one bit per song, set when the
; song had a track and the MSU-1 could not play it —it was not on the card,
; or it did not finish opening it in time— and it played through the SPC700.
; See `tema_por_msu` in paquete_de_audio.s. `msu_detectar` clears it on
; reset; it does not travel in the save, because what it says is about the
; card and not about the game.
MSU_FALTA      = $7E7820
MSU_FALTA_BYTES = 16
LZ2_BUFFER     = $7F0000
ANIM_DIBUJOS   = $7F6000
ANIM_DIBUJOS_FIN = $7F8000

; --- sound effects with MSU-1 ------------------------------------------------
;
; $7E78B0 to $7E78CF, reserved on 2026-09-26. See `efectos_con_msu.s`: voices
; 0 to 5 when the SPC700 is not playing music, and the `.msu`'s quality sound
; effects. `se_limpiar` zeroes it, on reset; it does not travel in the save.
EX_CUADROS  = $7E78B0           ; six words: how many frames the sound effect
                                ; on each voice has left, from 0 to 5
EX_IDX      = $7E78BC           ; six words: its row in `sonido_tabla`
EX_PEND     = $7E78C8           ; one bit per voice: the sound effect has not started yet
EX_OCUP     = $7E78C9           ; one bit per voice: it belongs to a sound effect
                                ; —pending, playing or being handed back— and
                                ; not to the music
EX_DEVOLVER = $7E78CA           ; one bit per voice: it finished, and next frame
                                ; it is handed back to the music
MSU_SE      = $7E78CB           ; 0 not checked, 1 the `.msu` is this
                                ; cartridge's, 2 it is not or there is no MSU-1
MSU_SE_SIG  = $7E78CC           ; three bytes: where the `.msu` stream was left
EX_FIN      = $7E78CF
.assert EX_FIN <= $7E78D0, error, "the MSU-1 sound effects overflow their range"

; --- which sound effect is in each directory place ---------------------------
;
; $7E78D0 to $7E78FF, reserved on 2026-09-26: one byte for each of the
; SE_LUGARES of the SPC700 directory that the sound effects share, with the
; number of the sound effect recorded there, or $FF. Several sound effects go
; to the same place —the ones that are never in the same package: see
; `lugares_de_efectos` in tools/audio/snes_music.py— and the directory does
; not say which one is there. See `anotar_efecto` in paquete_de_audio.s.
; `aram_limpiar` sets it to $FF; it does not travel in the save.
FAR_EFECTO_EN = $7E78D0
.assert FAR_EFECTO_EN + SE_LUGARES <= $7E7900, error, "the sound effect places do not fit in FAR_EFECTO_EN: see SE_LUGARES_MAX in snes_music.py"

; --- the battle transition ---------------------------------------------------
;
; $7E7840 to $7E784F, reserved on 2026-09-26. See `fundido_de_pelea.s`.
PELEA_PRENDIDA = $7E7840        ; 1 if the battle got to turn its screen on

; --- the teleport transition ------------------------------------------------
;
; $7E7920 to $7E793F, reserved on 2026-09-27: the transition with which the
; teleport erases the screen and the one with which it shows it again, which
; `ChangeScreenTransitions` changes —`op_transition`— and `fundido_mosaico`
; and `fundido_desde` read: TRANSICION_MOSAICO, TRANSICION_CORTE (only for
; erasing), or anything else for the fade.
;
; `transicion_de_arranque` sets them to the fade, on reset: bsnes starts WRAM
; with garbage, and without that the first teleport could come out as mosaic.
; **It does not travel in the save**, and in RM2k it does. That is on
; purpose: the two places in the game that change it are chains of autorun
; pages that set it back to the fade when they finish —Boss Wick's hideout,
; from the mosaic of page 1 of 42 to the fade of page 4 of 40, and Eisen's
; story, from "none" in 93 to the fade of page 5 of 6 of 81—, and saving it
; would mean changing the save format for a value that in nearly every saved
; game holds the same.
;
; The "nearly" is the minigame on 95, which is inside Eisen's story and has a
; save point: a game saved there comes back with the fade instead of the cut,
; and the only thing that notices is the jump with which 95 sends Eisen back
; to the start when his fortitude runs out. The one that leaves the minigame
; asks for the cut itself before jumping.
TRANSICION_BORRAR  = $7E7920
TRANSICION_MOSTRAR = $7E7921

; --- the memorized song -------------------------------------------------------
;
; $7E7940 to $7E795F, reserved on 2026-09-27. `MemorizeBGM` records here
; which song was playing —its index in `Temas`, or $FF if none— and
; `PlayMemorizedBGM` plays it again: see `op_memorized_bgm`. Reset leaves it
; at $FF.
;
; **It does not travel in the save**, and in RM2k it does (`memorized_bgm`,
; in the system part). The two commands always go together in the same
; autorun page —the game's four tutorials, 58 and 162 to 164—, with no menu
; in between, so there is nowhere to save between one and the other.
TEMA_RECORDADO = $7E7940

; --- the weapons' SP, and the target of multi-target skills -----------------
;
; $7E7960 to $7E797F, reserved on 2026-09-27 for Lashe City milestone 4.
; `ba_armar` builds it at the start of each battle, so it does not travel in
; the save and there is no need to set it on reset.
BA_ARMA_SP = $7E7960            ; BA_GRUPO_MAX bytes: what attacking costs
                                ; each party place, `batalla.sp_del_arma`
BA_HAB_I   = $7E7964            ; which combatant a multi-target skill is on:
                                ; `ba_hab_usar` calls `ba_hab_uno` for each
                                ; one, and that one clobbers the `BA_S*`
.assert BA_HAB_I < $7E7980, error, "milestone 4 overflows its range in far RAM"

; --- an NPC row, set aside ---------------------------------------------------
;
; $7E7980 to $7E799F, reserved on 2026-09-27 for the race's milestone 2.
; `acomodar_lejos` keeps here the row that changes place while it moves the
; others; it lasts as long as that routine.
NPC_FILA_APARTE = $7E7980           ; NPC_STRIDE bytes

; --- the Game Over screen ------------------------------------------------------
;
; $7E7A30 to $7E7A3F, reserved on 2026-09-28. See tools/runtime/game_over.s.
GO_PIERDE  = $7E7A30            ; word: where losing the battle being fought
                                ; leads; $FFFF is Game Over
GO_ESPERA  = $7E7A32            ; 1 while the screen waits for the button: it is
                                ; what the harness looks at, which has no other clock
GO_NIVEL   = $7E7A33            ; the fade's brightness
GO_CUADROS = $7E7A34            ; how many frames each fade level lasts

; --- the map grid, in WRAM --------------------------------------------------
;
; **$7E8000 to $7EFFFF belongs to the grid**, and it continues at $7F8000 if
; it goes past 32 KB: the upper half of the two banks, which has the shape of
; two consecutive LoROM banks —see `ptr_mas`—. `lz2_grilla` decompresses it
; when loading the map and everyone who asks about a cell reads it. Reserved
; on 2026-09-26, and it is a decision with a cost: it was half of the far RAM
; that was still free. What is lost, how it is reverted and what catches it,
; in workflow/decisiones/la-grilla-vive-en-la-wram.md;
; `test_reservas_de_la_wram.py` fails if another symbol lands inside.
;
; It shares the $7F half with `ESC_ESCENA`: the battle overwrites it, and
; `volver_de_batalla` decompresses the whole grid again.
GRILLA      = $7E8000
GRILLA_FIN  = $7F0000
GRILLA_ALTA = $7F8000

; On which frame startup ends, counted from reset. Startup —loading the map,
; uploading the driver to the SPC700 and the map's audio package— takes as
; long as it takes, and that changed with every code or data change: one more
; loop and the main loop started a frame later, and every recipe that
; compares frames in motion carries that number measured by hand. Now it
; waits until this frame and the loop always starts on the same one. A ROM
; whose startup takes longer than this goes without waiting, later, but just
; as fixed for it.
;
; It is sized for the startup map's package, and **the converter stops if it
; does not fit**: the estimate, on the high side, is `cuadros_del_arranque` in
; tools/audio/snes_music.py. Measured on 2026-09-26: `release`'s work ends on
; frame 30 and the estimate gives 34. It was 112 until that day, meant for
; uploading a full ARAM through the IPL; see
; workflow/decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md.
BOOT_CUADROS = 40
VIEW_ROWS = 29

; The message window: 256x80 flush with the bottom of a 224-line screen, that
; is, the ten cell rows going from 18 to 27. The same numbers are in
; `tools/port/ventana.py`, which is where they come from: 80 high and flush
; with the bottom, the way RM2k places it.
VENTANA_FILA  = 18
VENTANA_FILAS = 10
VENTANA_LINEA = VENTANA_FILA * 8        ; and in scanlines: 144
LINEAS = 224

; BG2's vertical scroll while the window is drawn. On the first scanline the
; PPU shows line `vofs + 1`, so for row 0 of its own tilemap to land on line
; 144 it takes `vofs + 1 + 144 = 0` modulo 256, which is the height of a
; 32x32 tilemap. Hence the 111. The horizontal one is zero.
VENTANA_VOFS = 111

; The 64x32 tilemap is two 32-wide screens side by side, and the second one
; does not live 32 words further on but 1024.
VIEW_COLS_TILEMAP = 32

