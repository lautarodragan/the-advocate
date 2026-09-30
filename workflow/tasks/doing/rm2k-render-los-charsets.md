---
name: "rm2k-render dibuja los CharSets"
description: "La primera parte de que rm2k-render dibuje todo lo de RPG Maker: las poses de un CharSet y los hechos con un tile, que hoy dibuja el conversor en Python"
type: refactor
assignee: Yaguarundí
---

De taro, el 2026-09-30: "vamos a por los CharSets en rm2k-render". Es la
primera parte de `todo/rm2k-render-dibuja-todo-rm2k.md`, y va después de
Adeleine en Rust porque los CharSets pasan por Adeleine antes de llegar a
Voodoo.

El criterio de qué va a `rm2k-render` sale de la decisión
(`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): dibujar lo
que dibujaría RPG Maker, sin saber de la SNES. Lo que el port decide por la
consola —la trama o el horneado de los translúcidos, que la SNES no tiene,
los CharSets opacos— no es de `rm2k-render`: se queda del lado del
conversor, o de Adeleine si es decidir colores. La prueba para saber de qué
lado va algo: ¿lo haría igual un visor de RM2k en una PC?
