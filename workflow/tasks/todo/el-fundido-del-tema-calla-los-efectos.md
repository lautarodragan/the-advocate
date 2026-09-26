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
