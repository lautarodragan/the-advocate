---
name: "\\N[n] en los mensajes"
description: "Una caja con \\N[n] (el nombre de un actor) deja afuera su página; en The Frozen World eso corta la cinemática inicial en negro (mapa 4). Barato: hornear el nombre por omisión cuando ningún ChangeHeroName lo cambia"
type: feature
agents: [Aguará, Carpintero]
assignee: taro
---

Del análisis breve de Aguará (Sonnet), el 2026-10-05, sobre lo que taro vio jugando las ROMs de los otros juegos. Es lo primero que recomienda: el más barato y el más general (4 juegos).

## Hecho (Carpintero, 2026-10-05)

`with_names` en `compile.rs` hornea el nombre de la base de datos en cada
`\N[n]` cuando ningún `ChangeHeroName` del juego (mapas, tropas, eventos
comunes) toca a ese actor (`indices::hero_names`). `\N[0]` (el líder) y los
actores renombrados siguen dejando la página afuera: el compositor de la ROM
no escribe un nombre en tiempo de ejecución y no es barato dárselo. Hoy
`ChangeHeroName` tampoco compila, así que una página que renombra ya está afuera.

Verificado: prueba del crate (`an_actors_name_is_baked_into_the_text_unless_it_can_change`);
ABL no usa `\N[` en su `data/`, así que no cambia; Frozen World rearmado con
estas herramientas pasa del negro y muestra al DARK WIZARD en snes9x. La tanda
de ABL no se corrió.
