# El pipeline

    /extras/abl-rm (.lmu .ldb .lmt)   --ditto unpack (just datos)-->  data/ (JSON)
    data/ + parches/manual/           --tools/rpgmaker/lcf.py-->      el juego leído,
                                                                      con los textos rearmados
    + imágenes, MIDI y WAV            --tools/port/snes_convert.py--> rom/build/<rom>/
      (/extras/abl-rm, /extras/rtp)     (voodoo: tiles, gunter: BRR)    mapdata.inc, musicdata.inc,
                                                                      parches/ (decisiones)
    rom/src/*.s + esos .inc           --ca65 + ld65 (ensamblar.py)--> abl.sfc + abl.sfc.sym
    abl.sfc + MIDI o /extras/msu      --tools/audio/msu.py-->         abl.msu + abl-N.pcm

    just build release    todo, con las pistas de MSU-1, en rom/build/release/
    just parches          copia las decisiones de release a parches/auto/
