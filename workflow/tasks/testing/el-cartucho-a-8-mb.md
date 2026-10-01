---
name: "El cartucho a 8 MB, ExHiROM"
description: "Primero una ROM de prueba de ExHiROM para el FX Pak; después mudar release, con las goldens quietas"
type: feature
assignee: taro
---

De taro, el 2026-10-01: `decisiones/el-cartucho-pasa-a-8-mb.md`. Lo que
cambia, según `docs/research/2026-10-01-el-juego-entero-sin-msu-1.md`
(Tucu-tucu): `memoria.cfg` a bancos de 64 KB (`banks.rs` ya está
parametrizado), la cabecera en `$40FFB0`, las tablas del banco 0 vistas como
32 KB en `$80`, lo que cruza bancos a mano (`.crossbank`, las muestras de
`emit.rs`) porque el banco empieza en `$0000`, y la SRAM a `$20-$3F:6000`.
No cambian la WRAM, la RAM lejana ni el `.msu`. Sin verificar: que Mednafen
arme ExHiROM.

## Fase A: la ROM de prueba (Ceibal, 2026-10-01)

`just exhirom` (`rom/experimentos/exhirom/`): un archivo de 8 MB de bytes
pseudoaleatorios con el código dos veces, que suma tramos de todo el mapa y
pinta nueve franjas; la SRAM se escribe por `$20:6000`, se lee por
`$A0:6000` y deja una marca para el arranque siguiente. Entregada en
`/shared/experimentos/2026-10-01-exhirom/`, con el `LEEME.txt` de qué
mirar; **falta que taro la pruebe en el FX Pak**.

Lo que dieron los emuladores, dos arranques cada uno:

- **snes9x y bsnes**: todo como el cartucho.
- **mesen-s** —y Mesen2 sin "strict board mappings", que es su opción por
  omisión, y el módulo `snes` de Mednafen—: ponen la SRAM de LoROM en
  `$70-$7D:0000-7FFF` también en ExHiROM. **Esas 14 mitades bajas, 448 KB,
  no se pueden usar para datos.** Lo dice el código de los dos Mesen
  (`BaseCartridge.cpp`, "some old romhacks seem to depend on this").
- **Mednafen `snes_faust`**, el que juega taro: arma ExHiROM, pero lee
  `$80-$BF:8000-FFFF` de los segundos 4 MB (`cart.cpp` le suma 4 MB a todo
  banco menor que `$C0`). El cartucho y el FX Pak (`address.v`:
  `{!A23, A21:0}`) los leen de los primeros. **Por eso el código del juego
  va dos veces**: en `$008000`/`$018000` del archivo —lo que la consola ve
  en `$80`/`$81`— y en `$408000`/`$418000` —lo que ve Mednafen, y donde la
  consola busca los vectores, en `$00`—. Cuesta 64 KB y deja el `FAST` y
  los `jsl` del runtime como están.
- FastROM anda en los cinco: el mismo bucle tarda 76 líneas desde `$C0` y
  99 desde `$40`. **Los segundos 4 MB son siempre lentos** —MEMSEL sólo
  acelera `$80-$FF`—: lo que la CPU lee byte a byte conviene en los
  primeros.

## Fase B: el juego mudado (Ceibal, 2026-10-01)

Commit `ExHiROM: el cartucho pasa a 8 MB`; el porqué de cada parte está en
la documentación de `tools/rm2k-snes/cartridge/src/banks.rs` y en la
sección nueva del README, "El cartucho es ExHiROM, de 8 MB". En corto:

- Datos en bancos de 64 KB desde `$0000`: primero `$C2-$FF` (rápidos),
  después `$42-$6F` (lentos), y las mitades que quedan para piezas de hasta
  32 KB. Lo que cruza a mano sólo cruza entre dos bancos que se siguen.
- Los bancos 0 y 1 siguen enlazados en `$00:8000`/`$01:8000`, como en
  LoROM, y el armado los copia a `$408000`/`$418000`: el runtime no se
  enteró del cambio, salvo lo que cruza bancos a mano y los `ora #^FAST`
  sobre bancos de datos, que se fueron.
- SRAM en `$20:6000`, 8 KB; cabecera `$35`, `$0D`, `$03`. Las partidas de
  LoROM no cargan.
- **Las goldens no se movieron**: la tanda pasa contra las de antes.
- `test_musica_techos.py[dcbest]` recorta **una** muestra: no corrí
  `just techos`, queda para medir al mergear.
- `release` cabe en los bancos rápidos y deja libres los 46 bancos lentos
  de 64 KB y 20 mitades: `just espacio`, medido en este commit. Ningún
  dato va todavía a los lentos; cuando vaya, lo que la CPU lee byte a byte
  —el stream de la música, las muestras, el bytecode— conviene que siga en
  los rápidos, y el reparto hoy no distingue qué es cada pieza.
- El caso `empujon` creció 32 KB: con bancos de 64 KB, el bloque de textos
  de `test-special` tenía que pasar de un banco para que `test_texto`
  siguiera cruzando el borde.

**Para Timbó** (ya terminó, así que no hizo falta pasarle nada): la emisión
no tuvo que cambiar. Sólo dos comentarios de `rm2k-snes-mapdata` (`asm.rs`,
`record.rs`) que decían que lo que sigue a un banco es el espejo de la WRAM;
el de `map_table` que se emite al `.inc` quedó, porque cuenta lo que pasó en
LoROM y lo dice así.

### Al mergear

- Instalar `cartridge` y `rm2k-snes-audio` (`rm2k-snes-volume-ceilings`
  parcha las dos copias del código). `mapdata` cambió sólo en comentarios:
  no hace falta.
- Medir los techos (`dcbest`).
- Lo que falta, y no es de esta tarea: que taro pruebe en el FX Pak la ROM
  de prueba (`/shared/experimentos/2026-10-01-exhirom/`) y después el juego;
  y en Mesen2, que los nombres de rutina se vean con el `.dbg` nuevo —el
  código está en `$008000` del archivo, que Mesen2 muestra en `$80:8000`—.
- Las partidas de antes no cargan: hay que empezar de nuevo.
