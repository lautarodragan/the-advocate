---
name: "El banco 1 se llenó"
description: "Después de los comunes de Picaflor y las imágenes grandes de Aguilucho, al banco 1 de release le quedan 131 B: mudar código al banco lejano para que las features siguientes tengan lugar"
type: refactor
assignee: Pepitero
---

De taro, el 2026-10-02: "el refactor para liberar esos bancos". El banco 1
de `release` quedó con 131 B libres (`just espacio`), entre los comunes
automáticos y el `CallEvent` compartido (Picaflor) y las imágenes grandes
(Aguilucho). Es como lo que hizo Pirincho con las tablas del banco 0
(`testing/las-tablas-de-items-al-banco-1.md`), pero con código.

## Lo medido antes (2026-10-02, Pepitero, sobre `cb333da4`)

`just espacio`, banco 0 / banco 1:

    release                    1.063 B / 131 B
    test-special               1.081 B / 131 B
    test-encounter-every-step  1.077 B / 131 B

`abl.sfc` de `release`: `6643d2c1…`.

**`FAR` es el banco 1**: el `.cfg` lo carga en `BANK01`, `$01:8000`. No hay un
"banco lejano" aparte adonde mudar lo del banco 1: el código a mano tenía dos
bancos, `CODE` (el 0) y `FAR` (el 1), y los dos estaban llenos. Así que lo
primero fue **abrir un tercero**.

Lo que ocupa el banco 1, por archivo, con el `.dbg` (cada línea con su span):
la pelea son 15.589 B —`battle_scene.s` 5.261, `battle.s` 2.804,
`battle_skills.s` 2.253, `battle_troop.s` 1.548, `battle_run.s` 1.262,
`battle_victory.s` 1.123, `battle_loop.s` 953, `battle_items.s` 385—; después
`shop.s` 2.267, `msu_effects.s` 1.631, `level.s` 1.537,
`equipment_screen.s` 1.486, `big_picture.s` 1.346, `picture_far.s` 1.225,
`decompress.s` 1.189, y el resto por debajo del KB.

## El tercer banco de código: `FAR2`, en la mitad baja de `$C0`

Era el último lugar de datos de los 4 MB rápidos, y ningún cartucho lo usaba
(`release` deja libres las mitades bajas de `$C0` y `$C1`). Como mitad de
ExHiROM es rápida siempre, sin espejo: lo que vive ahí se entra con `jsl` a
su dirección, y no necesita la copia en los segundos 4 MB que tienen los
bancos 0 y 1. `banks::FAR2` en `rm2k-snes-cartridge`, y `just espacio` lo
muestra como "bank $C0".

El commit que lo abre no mueve la ROM: los tres cartuchos salen byte por byte
iguales, porque esa mitad estaba en ceros. `ld65` avisa que el segmento
`FAR2` no existe hasta que algo lo usa, en el commit siguiente.
