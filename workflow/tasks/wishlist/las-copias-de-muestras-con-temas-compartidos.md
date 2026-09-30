---
name: "Las copias de muestras con temas que comparten muestras"
description: "Un tema nuevo que comparte muestras con los viejos cambia qué copias hace rm2k-snes-audio y les baja la tasa sin MSU-1"
type: feature
---

Del hito 4 del mundo (2026-09-27): los cinco temas del capítulo comparten
muestras con temas que ya estaban, y eso cambió qué copias hace
`copies`, en `tools/rm2k-snes/rm2k-snes-audio/src/bank.rs`. Sin MSU-1 bajaron 43 pares (tema, instrumento) de 15
temas y subieron 51. Con sólo jackalstg2 bajaban 36. taro escuchó el antes y
el después y los aceptó, así que no hubo que frenar el capítulo, pero **va a
volver a pasar con cada tema que se sume**.

Lo que se probó sin recuperarlos (ver
`testing/mundo-4-el-capitulo.md`, "La música de antes, sin MSU-1"):
`TEMAS_APARTE` (los nuevos ya van solos), `SE_DE_SIEMPRE` de 70 a 130 (lo
mejor, 29 pares, y mueve la tanda de efectos que taro aprobó), `COPIA_HASTA`
en 0,85 y 0,95, sin la herencia de jackalstg2, sin el paquete del 259. El
directorio no era la causa: sin la segunda tanda para los temas nuevos queda
con lugar libre y bajan igual 42.

Lo que falta: que `copias` elija qué copiar pensando en todos los temas que
usan una muestra, no en el orden en que llegan, y medirlo par por par con
`Banco` contra el `main` de antes del capítulo (93af39f no: el `main`
455f9fc1). Lo que no se recupere sin perder otra cosa, grabado para que
taro escuche.
