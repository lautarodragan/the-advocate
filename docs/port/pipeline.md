# El pipeline

    $ABL_GAME_DIR (.lmu .ldb .lmt)    --ditto unpack (just datos)-->  rom/data/ (JSON)
    rom/data/ + rom/parches/manual/           --tools/rpgmaker/lcf.py-->      el juego leído,
                                                                      con los textos rearmados
    + imágenes, MIDI y WAV            --tools/port/snes_convert.py--> rom/build/<rom>/
      ($ABL_GAME_DIR, $ABL_RTP_DIR)     (voodoo: tiles, gunter: BRR)    mapdata.inc, musicdata.inc,
                                                                      abl.msu (fondos de batalla),
                                                                      rom/parches/ (decisiones)
    tools/runtime/*.s + esos .inc     --rm2k-snes-assemble----------> abl.sfc + abl.sfc.sym
                                        (reparto en bancos, ca65 + ld65)
    abl.sfc + MIDI o reemplazos       --rm2k-snes-msu---------------> abl-N.pcm
                                        (fluidsynth, ffmpeg)

    just build release    todo, con las pistas de MSU-1, en rom/build/release/
    just parches          copia las decisiones de release a rom/parches/auto/
