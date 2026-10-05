---
name: "Otros juegos: el relevamiento"
description: "Siete juegos de RM2k además de ABL —El Dorado, Sunset Over Imdahl, The Book of Three, Dooms 2, The Frozen World, Desert Nightmare, Vampires Dawn—: un proyecto para cada uno, qué compila, qué rompe y un primer cartucho sin MSU-1, para encontrar lo que comparten antes de arreglar nada"
type: research
agents: [Aguará]
assignee: taro
---

De taro, el 2026-10-05: "Te dejé algunos juegos en /shared/otros-juegos/.
Todos tienen distintos desafíos. Los probaría sin MSU primero, para
simplificar todo." Copiados a disco local en `/extras/otros-juegos/`. Los
siete son de RM2k (ninguno tiene `ldb_id` 2003). The Way Episode 1 vino
como un .exe sin extraer y queda para después.

## Mientras se trabaja (Aguará, 2026-10-05)

Los proyectos van en `/extras/otros-juegos-snes/<juego>/`, cada uno su
repo; los temporales en `/extras/scratch/aguara/`.

* **Ditto**: los siete vuelven byte por byte, después de buscar
  `RPG_RT.LDB` sin mirar la caja (Sunset). Commit propio.
* **Armar un proyecto**: la primera vez, contra "missing key", hubo que
  llenar dieciséis secciones del `rm2k-snes.toml` de ABL con valores
  neutros, un caso `nada.json` y un `[cases] debug_map_entry` que no
  existe. Los otros seis salieron de un script descartable que copia el de
  El Dorado (`nuevo.py`): es lo que haría un `rm2k-snes-project new`.
* **Supuestos de ABL arreglados en la rama**: el mapa de debug obligatorio
  (1), el cartucho de un solo mapa (3), el System y las caras sólo del
  juego (5), cada uno en su commit.
* **El barrido**: un cartucho por mapa, cada mapa solo, para ver dónde se
  corta cada uno. `BOOT_FRAMES` subido a 255 **sólo en el árbol, sin
  commitear**, para que el arranque de cada mapa no tape lo de atrás.
* **Lo que tapa todo un juego**: la ventana de más de 15 colores (Dooms2,
  Frozen World, Book of Three, Vampires Dawn), el grupo vacío al empezar
  (Sunset, Desert), BMP (Dooms2). Para mirar detrás: una copia de enlaces
  del juego con el System reducido a 12 colores y las BMP pasadas a PNG
  (`juegos/granja.py`), y `party = [1]`.
* **Ojo al instalar parcial**: cada binario lee el runtime del checkout
  del que se instaló (`suite::runtime`). Con `cartridge` local y
  `rm2k-snes-audio` global, `BOOT_FRAMES` salía de dos árboles distintos.

## Resultado

El estudio, con la tabla y la recomendación:
`docs/research/2026-10-05-otros-juegos.md`. Seis de los siete arman un
cartucho que arranca; Vampires Dawn no (las variables).

**Dónde está cada cosa** (de esta máquina, por eso acá y no en el
estudio):

* los proyectos, cada uno su repo con un commit: `/extras/otros-juegos-snes/<juego>/`;
* las ROMs: `/shared/builds/otros-juegos/<juego>.sfc`;
* las hojas, original arriba y cartucho abajo:
  `/shared/capturas/2026-10-05-otros-juegos/<juego>.png`;
* las copias de enlaces con el System reducido y las BMP en PNG, que los
  cartuchos de Book of Three, Dooms 2, Frozen World y Desert necesitan para
  armar: `/extras/scratch/aguara/juegos/<juego>/`, hechas con `granja.py`
  de al lado. Se arman con `GAME_DIR=<copia> just cartuchos`.

**Qué mirar**: que el comienzo de Book of Three, Frozen World y Dooms 2
se parezca al original, y **el fondo de Desert Nightmare**, un panorama en
modo 3 que sale basura celeste: es de los panoramas recién mergeados.

**Verificado**: las pruebas de cada crate tocado —`ditto`, `cartridge`,
`screens`, `convert`, `wally`, `events`—, cada prueba nueva vista en rojo;
`just -f tools/justfile test`; y la tanda de ABL (`b28864d`→`bfe49bf`,
clon propio) con estas herramientas: 1136 en verde, `abl.sfc`
`27e94e67039533a2…`, igual que antes. La tanda no corre ninguno de los
siete juegos: lo que se dice de ellos sale del barrido y de las capturas.

**Al mergear, reinstalar**: `ditto cartridge screens convert wally events`.
No toca el runtime ni la RAM.
