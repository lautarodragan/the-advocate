---
name: "La segunda etapa de partir main.s"
description: "Mover las rutinas que el corte dejó en el archivo del vecino, y partir interprete.s"
type: refactor
---

El corte del 2026-09-25 (`391930c`, ver `done/partir-main.s.md`) partió
`rom/src/main.s` en tramos contiguos **sin reordenar**, porque partir no
cambia la ROM y mover sí. Así que quedaron rutinas en un archivo que no es el
suyo. La lista, medida por el plan de esa tarea —verificarla antes de mover,
porque `main` se movió—:

* `poner_switch` en `ruta_del_heroe.s` → `variables.s`;
* `volver_al_mapa`, `volver_de_batalla` y `poses_npc_olvidar` al final de `items.s`;
* `sonido_de_codigo`, `sonido_tocar` y `destello_de_codigo` al final de
  `quietos_que_animan.s` → `efectos_de_sonido.s` y `destello_de_personaje.s`;
* `menu_hp_escribir` en `equipo_desde_eventos.s` (FAR; `menu.s` es banco 0:
  no se puede juntar sin cambiar la llamada);
* `exp_sumar` y `aprender_del_nivel` en `batalla_lazo.s` → `nivel.s` (los dos FAR);
* `titulo_subir_menu`, `hp_inicial_poner` y `actor_nivel_de` en `banco1.s`;
* comentarios huérfanos arriba de una marca de sección, que son del tramo
  anterior o de nada.

**Mover cambia la ROM**, así que cada mudanza se verifica con `just pruebas`
**sin ninguna golden cambiada** —cambian las direcciones, no el
comportamiento—, y sólo se puede mover **dentro del mismo segmento**: pasar
algo del banco 0 al 1 cambia cómo se lo llama (`jsr` contra `jsl`, el banco de
datos) y es un cambio de código, no una mudanza. Una mudanza por commit, para
que `git blame -C --diff-algorithm=histogram` la siga.

**Y lo que más vale, que no es una mudanza: `interprete.s`** es un solo
`.proc correr_codigo` de unas 2.300 líneas con todos los manejadores de
opcode adentro, y es el archivo que más commits recibe. Partirlo es cortar
**adentro** del `.proc` —un `.include` por familia de opcodes—, que sale byte
por byte igual (probado en el plan del corte), pero deja archivos que empiezan
a mitad de un scope, con etiquetas locales de otro archivo. Es una decisión de
legibilidad: conviene medir cuánto se toca cada familia (`git log` sobre el
`main.s` de antes y `interprete.s`) y proponerla antes de hacerla.
