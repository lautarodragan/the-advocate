### El RTP

ABL usa recursos que no vienen con el juego: 5 chipsets (`ChipSet1/2/3`,
`Basis`, `Inner`) y 17 charsets (`Chara1-4`, `Crown*`, `Future1-3`, `Men1`,
`Women1`, `People7`, `Vehicle`). Están en el **RTP de Don Miguel** (junio de
2000), que es el que se usaba fuera de Japón: su traducción del RPG Maker 2000
traía su propio RTP traducido, con archivos agregados por él que no existen en
el japonés — `Future1-3`, por ejemplo. El RTP libre de EasyRPG **no sirve**: es
un reemplazo con arte distinto y otros nombres (`Actor1-4` en vez de
`Chara1-4`).

No está en el repo, por la misma razón que el juego original —no es nuestro
para redistribuir—: se lee de la carpeta que diga `ABL_RTP_DIR`. Para
reponerlo, de `RTPE.EXE` (un SFX de RAR):

    7z x -oRTP-tmp RTPE.EXE && mv RTP-tmp/Data/RTP "$ABL_RTP_DIR" && rm -rf RTP-tmp
