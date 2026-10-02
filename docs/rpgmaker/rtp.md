### El RTP

Un juego de RM2k usa recursos que no vienen con él: los del **RTP**, el
paquete de ChipSets, CharSets, músicas y efectos que el editor instala al
lado. Las herramientas lo buscan donde diga `--rtp-dir`, después del juego,
y no traen ninguno: el RTP no es nuestro para redistribuir.

**Cuál RTP depende del juego, porque los nombres cambian.** Los juegos
hechos fuera de Japón con la traducción de Don Miguel (junio de 2000) usan
el suyo, que trae archivos agregados por él que no existen en el japonés
—`Future1-3`, por ejemplo—. El **reemplazo libre de EasyRPG** tiene arte
distinto y otros nombres (`Actor1-4` en vez de `Chara1-4`): no le sirve a un
juego hecho con el de Don Miguel, pero sí a uno hecho para él, y su
licencia, archivo por archivo, es CC0 o CC-BY 4.0 —ver
`docs/research/2026-10-02-el-juego-de-pruebas.md`—.

El de Don Miguel se saca de `RTPE.EXE`, que es un SFX de RAR:

    7z x -oRTP-tmp RTPE.EXE && mv RTP-tmp/Data/RTP <destino> && rm -rf RTP-tmp

Qué usa de él A Blurred Line, en el `docs/rpgmaker/rtp.md` de su repo.
