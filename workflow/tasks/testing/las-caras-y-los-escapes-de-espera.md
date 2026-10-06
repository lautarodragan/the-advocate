---
name: "Las caras y los escapes de espera en los mensajes"
description: "ChangeFaceGraphic y los escapes \\. \\! \\| en mitad de una caja dejan afuera su página; en Dooms 2 la escena de arranque del mapa 2 no corre y nada se dispara. Barato: aceptar la cara como deuda (sin dibujarla) y tomar los escapes como esperas"
type: feature
agents: [Aguará, Tijereta]
assignee: taro
---

Del análisis breve de Aguará (Sonnet), el 2026-10-05, sobre lo que taro vio jugando las ROMs de los otros juegos. Afecta a Dooms 2, Desert Nightmare y Sunset Over Imdahl.

## Hecho (Tijereta)

`ChangeFaceGraphic` entra en `ACCEPTED_UNDONE` y `\.`, `\!` y `\|` en el medio de una caja se descartan en `escape_tail` (`without_waits`, en `rm2k-snes-text`): la ROM no sabe esperar a mitad de caja, así que es deuda, anotada en `todo/las-caras-y-las-esperas.md`. EasyRPG sí espera (`Window_Message`), y de ahí sale la medida: `\.` 1/4 s, `\|` 1 s, `\!` una tecla.

**Verificado**: pruebas de `rm2k-snes-text` y `rm2k-snes-events`, con los casos del medio en rojo antes. ABL no usa caras ni escapes en el medio (todos son cola): `release` da `abl.sfc` `27e94e67039533a2…`, igual. La tanda no se corrió. Dooms 2: con estas herramientas la escena del mapa 2 corre (diálogo de Jack en captura de snes9x), **pero** al compilar más páginas el directorio de muestras pasó de 255 entradas (263) y el cartucho no armaba: para armarlo se excluyeron en el `rm2k-snes.toml` del proyecto los mapas 40 a 93 (salvo los ya excluidos). Habrá que decidir qué excluir de verdad.
