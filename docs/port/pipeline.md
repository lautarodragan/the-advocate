# El pipeline

    $ABL_GAME_DIR (.lmu .ldb .lmt)    --ditto unpack (just datos)-->  rom/data/ (JSON)
    rom/data/ + rom/parches/manual/
    + imágenes, MIDI y WAV            --rm2k-snes-convert-----------> rom/build/<rom>/
      ($ABL_GAME_DIR, $ABL_RTP_DIR)     (y sus etapas: wally, events,   mapdata.inc, musicdata.inc,
                                         screens, images, battle,
                                         mapdata, patches, audio)
                                                                      abl.msu (fondos de batalla),
                                                                      rom/parches/ (decisiones)
    tools/runtime/*.s + esos .inc     --rm2k-snes-assemble----------> abl.sfc + abl.sfc.sym
                                        (reparto en bancos, ca65 + ld65)
    abl.sfc + MIDI o reemplazos       --rm2k-snes-msu---------------> abl-N.pcm
                                        (fluidsynth, ffmpeg)

    just build release    todo, con las pistas de MSU-1, en rom/build/release/
    just parches          copia las decisiones de release a rom/parches/auto/
