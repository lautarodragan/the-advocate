---
name: "El fundido del tema calla los efectos"
description: "Sin MSU-1, un FadeOutBGM deja en cero el volumen general del DSP y los efectos quedan mudos hasta el próximo tema"
type: bug
---

Anotado como divergencia el 2026-09-26
(`workflow/divergencias/el-fundido-del-tema-calla-los-efectos.md`) por el
agente de los efectos, sin arreglar. Sin MSU-1, `FadeOutBGM` baja el volumen
general del DSP (`MASTER`) en vez del de las voces de la música, así que los
efectos (que tocan en las mismas voces del DSP con su propio volumen) quedan
mudos hasta que arranca otro tema. Grabando dio cero muestras. Pasa con el
trueno del final del mapa 3 y con `Wind1`/`clap` en el 18.

El arreglo probable: fundir el volumen de las voces de la música, no el
general. Medirlo con la bitácora de la música o grabando, y cobrarlo con una
prueba.

## Hecho, el 2026-09-26

Sin MSU-1, `bgm_fundido_tick` (`rom/src/musica.s`) ya no toca el volumen
general: baja VOL_L y VOL_R de cada voz de la música que tocó en el tema, y
`mus_escribir` escala los que el stream escribe en medio del fundido. El
factor va de 256 —el volumen sin tocar— a 0, y cada cuadro se reescribe sólo
el volumen que cambió respecto del anterior. Las cuentas las hace el
multiplicador del PPU (el del modo 7), que pasa a ser de `irq_musica`: el de
la CPU no se puede usar en la interrupción. Las voces con un efecto no se
tocan: el valor va a su sombra por `dsp_musica`. El volumen general queda fijo
en el del arranque, así que el techo por tema (`techos.toml`) y el de los
efectos siguen midiendo lo mismo.

Dos cosas más del mismo error:

* **La pantalla de título callaba su tema con el volumen general en cero**
  hasta el primer `PlayBGM`, y los efectos de la apertura de antes de ese
  `PlayBGM` quedaban mudos. Ahora suelta las voces con KOF.
* **Un tema que daba la vuelta en medio del fundido lo cancelaba** y volvía a
  sonar entero: `music_start_ya` —que es también la vuelta— ponía
  `bgm_fundido` en cero. Eso pasó a `music_start`, que es el `PlayBGM`.

Con MSU-1 el fundido estaba bien, y sigue igual: baja `MSU_VOLUMEN` y al
llegar a cero para la pista.

Lo cobra `pruebas/rpgmaker/test_fundido_del_tema.py`, con el caso nuevo
`efecto-tras-el-fundido`: `Switch1` antes del primer tema, durante el fundido
de `evilrhys` y después. Picos medidos con snes9x:

    antes del tema     0  →  9267
    durante (15%)   1782  →  9470
    después            0  →  9267

Y `test_con_msu_el_fundido_para_la_pista_y_los_efectos_siguen`
(`pruebas/abl/test_msu.py`) mira lo mismo con MSU-1; ésa pasaba también
antes. La divergencia `divergencias/el-fundido-del-tema-calla-los-efectos.md`
se borró: dejó de serlo.

Lo que tiene que escuchar taro, sin MSU-1: el trueno del final del mapa 3
—la secuencia de "Core...?"—, que viene después de un fundido; los efectos
del mapa 18 (`Wind1`, `clap`); y que los fundidos del tema sigan sonando
parejos y no a escalones.
