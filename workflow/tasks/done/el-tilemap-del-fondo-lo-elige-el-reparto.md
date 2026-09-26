---
name: "El tilemap del fondo lo elige el reparto"
description: "Un cuarto reparto de VRAM que baja el tilemap de BG1 a $1800 y le hace lugar al mapa 38"
type: refactor
---

La opción (d) de la pregunta 2 del 38 en `todo/lashe-city-hasta-la-carrera.md`:
que la dirección del tilemap de BG1 la elija el conversor por mapa, como ya
elige `OBSEL` y `BG12NBA`. Medido e implementado el 2026-09-25 sobre `dd73115`.

## Lo medido

**El 38 pide 476 tiles de fondo y 347 de sprite** (lo imprime el conversor con
`--map-id 38`). Los tres repartos que había daban 448/448, 480/256 y 384/512.

**El techo, enumerando todas las bases que el hardware permite** —sprites de a
$2000 palabras, fondos de a $1000, tilemaps de a $400; encima y ventana pegadas
en BG2; el tilemap de encima fijo en $7800—. El script fue descartable; lo que
sale:

    sprites                        256   320   384   448   512
    fondo, tilemap libre           544   512   480   448   416
    fondo, tilemap en $5800        544   512   480   448   416
    ídem, respetando las ranuras   544   512   448   448   416

"Respetando las ranuras" es que `RANURA_VRAM..RANURA_MAP+1024` ($2000..$4000)
no pise nada que `volver_al_mapa` no reponga (sprites, BG2, los tilemaps).

Así que **mover el tilemap no corre el techo**: para 347 sprites el máximo es
480 esté donde esté. Lo que cambia es la tercera fila. Con el tilemap clavado
hay un 480/384 —sprites en $4000, fondo en $0000, tilemap de la ventana en
$3C00— pero ese tilemap cae justo en `RANURA_MAP`, y volver del menú o de las
ranuras lo dejaría pisado. Con el tilemap libre, el 480/384 que respeta las
ranuras es:

    sprites     $0000  384 tiles     mapa        $1800  el tilemap de BG1
    tiles       $2000  480 tiles     ventana_map $5C00
    encima      $6000  128 tiles     ventana     $6800  256 tiles
    tilemap de encima $7800

**Al 38 le sobran 4 tiles de fondo y 37 de sprite.** 480 y no los ~483 de la
cuenta en bytes porque el tilemap de la ventana necesita una base múltiplo de
1024 palabras detrás del fondo: el fondo termina como mucho en $5C00.

La alternativa sin mover el tilemap —sprites en $4000 y que `volver_al_mapa`
vuelva a subir el tilemap de la ventana cuando cae en `RANURA_MAP`— daría lo
mismo, con el costo en `volver_al_mapa` y no en el streaming. No se eligió
porque lo pedido era (d), y porque su costo lo pagaría otro contrato
(`_controlar_ranuras`) en vez de una suma.

**Dos repartos de hoy están debajo del techo**: "+fondo" podría dar 544 y
"+sprite" 416. Subirlos cambia el reparto de los mapas que ya los usan, así
que no va acá; queda anotado en `docs/port/vram.md`.

## Quién suponía $5800

Todo en `rom/src/`, más el arnés:

| dónde | qué hacía | cómo quedó |
|---|---|---|
| `arranque.s`, `ppu_init` | `lda #>VRAM_MAP \| MAP_LAYOUT` a `BG1SC` | ya no lo escribe: lo pone el mapa, como `BG12NBA` |
| `cargar_mapa.s`, `puesto` | — | copia `M_VRAM_MAP` a `FAR_VRAM_MAPA` y arma `BG1SC` |
| `cargar_mapa.s`, `volver_al_mapa` | `BG1SC` venía de `ppu_init` | lo arma de `M_VRAM_MAP + 1` (la pelea lo deja en su escena) |
| `ventana_del_mapa.s`, `build_column` | `adc #VRAM_MAP` | `adc f:FAR_VRAM_MAPA` |
| `ventana_del_mapa.s`, `build_row` | `adc #VRAM_MAP` | `adc f:FAR_VRAM_MAPA` |
| `ventana_del_mapa.s`, `limpiar_tilemaps` | `ldx #VRAM_MAP` | la lee de `FAR_VRAM_MAPA` |
| `vblank.s`, `push_una_columna` | `adc #(VRAM_ABOVE_MAP - VRAM_MAP)` | `and #$07FF` / `ora #VRAM_ABOVE_MAP` |
| `vblank.s`, `push_una_fila` | `lda #(VRAM_ABOVE_MAP - VRAM_MAP - 1024)` | `and #$03FF` / `ora #VRAM_ABOVE_MAP`, y entra por `fila_en_a` |
| `pruebas/arnes/consola.py`, `ventana` | leía el símbolo `VRAM_MAP` | lee `FAR_VRAM_MAPA` de la WRAM |

Ninguna tabla precalculada ni aritmética escondida: eran siete usos de la
constante en la ROM, dos de ellos como distancia entre los dos tilemaps. Lo
demás que toca tilemaps no mira el del fondo: la escena de batalla tiene el
suyo (`ESCENA_MAPA`, $3800) y lo repone `volver_de_batalla` con `fill_window`;
el título, el menú y las ranuras usan `TITULO_MAP` y `RANURA_MAP`; la ventana de
mensaje ya leía su tilemap del registro (`M_VRAM_VENTANA_MAP`); el HDMA y
`vblank.s` sólo reescriben `BG2SC`.

Los pasos a la capa de encima enmascaran en vez de sumar una distancia, que
dependería del mapa. Eso pide que los dos tilemaps arranquen en múltiplos de
2048 palabras: `.assert` en `vblank.s` para el de encima, `_controlar_repartos`
para el del fondo, que además se niega a un tilemap en $0000 (`col_addr` en cero
es "no hay columna").

**El registro del mapa estaba en sus 128 bytes justos**, así que `M_VRAM_MAP`
ocupa el lugar de `M_VRAM_ABOVE`: la base de BG2 es el nibble alto de
`BG12NBA_VALUE`, y `load_above` la saca de ahí. Era $6000 en todos los mapas.

**`FAR_VRAM_MAPA` es $7E6B80**, la palabra que sigue a las tiras de repuesto:
la BSS y la página directa están llenas. **Es una dirección de la RAM lejana
elegida mirando esta copia**: al mergear, mirar que ninguna otra rama haya
tomado $6B80.

## El costo en ciclos

Con el acumulador en dieciséis bits:

* `build_column` y `build_row`: `adc #imm` (3) pasa a `adc largo` (6), **+3
  ciclos por fila o columna armada**, un byte más cada una.
* `push_una_columna`: `clc` + `adc #` (5) pasa a `and #` + `ora #` (6), **+1
  ciclo por columna subida**, en el vblank.
* `push_una_fila`: `lda #` + `jsr` + `clc` + `adc abs` (16) pasa a `lda abs` +
  `and #` + `ora #` + `jsr` (17), **+1 ciclo por fila subida**, en el vblank.
* Por carga de mapa, unos cuarenta ciclos entre `puesto`, `limpiar_tilemaps` y
  `load_above`; en `volver_al_mapa`, once, menos los seis que `ppu_init` deja
  de gastar.

El peor cuadro arma dos filas y dos columnas: **doce ciclos en el lazo y cuatro
en el vblank**.

## Cómo se verificó

* **Ningún mapa de los cartuchos cambió de reparto.** Diff de los `mapdata.inc`
  de `release`, `test-main` y `test-special` contra los de `dd73115`: lo único
  que cambia en cada registro es el campo +18, que era `VRAM_ABOVE` = 24576 y es
  `VRAM_MAP` = 22528 en los 76 registros; ningún otro campo, ni `OBSEL_VALUE`,
  ni `BG12NBA_VALUE`, ni `VRAM_VENTANA_MAP`.
* **Las ROMs no salen byte por byte iguales, y no pueden**: el código que lee
  una variable en vez de una constante es otro código, y corre todo lo que
  viene después. Lo que cobra es la tanda: `just cartuchos` + `just pruebas` en
  verde, sin tocar ninguna golden.
* **El 38 en un cartucho de prueba en el scratchpad** (`--map-id 38
  --sin-titulo`): convierte, toma `LAYOUT_VENTANA_AMBOS` y la ROM deja
  `FAR_VRAM_MAPA` en $1800. Corriendo en snes9x: la captura se ve bien, sin
  tiles corridos; caminando, la cámara se movió 112 px en x y 32 en y, y
  `Partida.celdas_mal_dibujadas` dio 0 de 957; después de abrir el menú y
  guardar por las ranuras —`volver_al_mapa`—, 0 pixeles distintos y 0 celdas mal
  dibujadas. Con un `ShowMessage` de prueba la ventana se dibuja bien.
* El 38 no tiene problema de eventos horneados como el de `PawnDoorTop` en el
  37: convierte solo.

## Lo que no se verificó

* **Ningún caso de `just pruebas` corre el reparto nuevo**: el 38 no está en
  ningún cartucho. Lo de arriba es a mano, en snes9x, y nada lo va a volver a
  correr hasta que el 38 entre (la etapa de Lashe City).
* **Una pelea en el 38**: `volver_de_batalla` repone `BG1SC` por
  `volver_al_mapa`, que sí se ejecutó por el camino del menú; la pelea en sí no.
* **bsnes**: `test_cores.py` corre sobre los cartuchos de siempre, en $5800.
  `FAR_VRAM_MAPA` se escribe al cargar el mapa, antes de cualquier lectura, así
  que la basura de la WRAM no debería alcanzarla.
* **Hardware real.**
