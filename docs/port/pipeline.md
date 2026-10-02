# El pipeline

    --game-dir (.lmu .ldb .lmt)       --ditto unpack---------------->  data/ (JSON)
    data/ + parches/manual/
    + imágenes, MIDI y WAV            --rm2k-snes-convert-----------> build/<rom>/
      (--game-dir, --rtp-dir)           (y sus etapas: wally, events,   mapdata.inc, musicdata.inc,
                                         screens, images, battle,
                                         mapdata, patches, audio)
                                                                      <rom>.msu (fondos de batalla),
                                                                      parches/ (decisiones)
    tools/runtime/*.s + esos .inc     --rm2k-snes-assemble----------> <rom>.sfc + <rom>.sfc.sym
                                        (reparto en bancos, ca65 + ld65)
    <rom>.sfc + MIDI o reemplazos     --rm2k-snes-msu---------------> <rom>-N.pcm
                                        (fluidsynth, ffmpeg)

Las rutas de la derecha son del proyecto del juego —donde está su
`rm2k-snes.toml`, que las declara—, y `<rom>` es su `[rom] name`.
`rm2k-snes-cartridges` corre todo eso por cada cartucho que el proyecto
declare. Cómo lo llama A Blurred Line, con qué recetas y qué flags, en el
`docs/port/pipeline.md` de su repo.
