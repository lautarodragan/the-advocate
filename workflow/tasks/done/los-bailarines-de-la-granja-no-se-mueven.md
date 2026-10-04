---
name: "Los bailarines de la granja no se mueven"
description: "En el baile del 127, el 37 y la 38 tienen ruta y animación de girar, y en la ROM quedan quietos: el conversor no los cuenta entre los que caminan"
type: bug
assignee: taro
---

Lo vio Yaguareté el 2026-10-03, al meter la granja con la caché de ranuras
(`workflow/tasks/testing/la-cache-de-ranuras.md`). Es de antes de la caché y
no se siguió.

Base: herramientas `fe0f90ee`, ABL `4cd8eb6`.

# La causa

`route::own` en `rm2k-snes-events` —lo que decide si una página tiene ruta
propia, y de ahí si su evento camina para Wally (`moves.rs`)— devolvía
`None` para toda página con la animación "girar" (`AnimType_spin`, 5). Sin
ruta propia no es de los que caminan: no le tocan las doce poses, no pide
lugar de ruta, y se dibuja quieto mirando adonde dice su página.

**Era a propósito, y era un recorte de alcance**: `git blame` da la línea en
`cc001fba` y su comentario en `67a6e827` (el pase a Rust, 2026-09-29), y
`git log -S spin` lleva a `a80a37d7` (2026-09-05, "Los droides del mapa 2
caminan solos"), que la dejó afuera diciendo "el giro en el lugar
(`AnimType_spin`, dos páginas) ... ninguna de las dos páginas del juego que
lo usan está en los primeros mapas". Con el 127 en el cartucho, una sí está.

# Cuántos

Medido sobre los JSON de todos los mapas de ABL: **cuatro páginas** usan
"girar".

    mapa  evento        ruta                         velocidad  ¿en release?
    127   37 Farmer2    propia, un cuadrado, repite  3          sí
    127   38 Actress2   propia, un cuadrado, repite  3          sí
    64    3  AG7-17     ninguna (quieto)             1          sí
    227   3  AG7-17     ninguna (quieto)             1          no (>= 129)

El robot del 64 (switches 150 y 207, "Leaving Lashe City Scene") es el
mismo caso sin ruta: también se quedaba quieto.

# El arreglo

Lo que hace RM2k (`Game_Character::UpdateAnimation` y `UpdateFacing` de
EasyRPG): la cuenta sube cada cuadro y al llegar a 24, 16, 12, 8, 6 o 4
—por velocidad— mira un cuarto más en el sentido del reloj; los pasos y los
`face_*` no lo dan vuelta; la columna es la de la página y nada la anima.

* **Compilador** (`route::own`): una página que gira tiene ruta propia, con
  `"spin"` y `"pattern"` (la columna). La que gira sin ruta
  (`MoveType_stationary`) recibe una vacía que repite: la consola sólo anima
  a un evento con lugar de ruta.
* **Emisión** (`rm2k-snes-mapdata`): el byte de flags de la página (+13) está
  lleno, así que el giro va en el de la velocidad (+15): bit 7 gira, bits 4
  y 5 la columna.
* **Runtime**: `load_page_into_slot` enmascara la velocidad y pone el bit 7
  de +18 y la columna en +10; `animate_ev_route` deriva a `spin_step` (en
  FAR, `far_npcs.s`, con su tabla); `move`, el giro del salto (`oam.s`) y
  `look` no le cambian hacia dónde mira a uno que gira;
  `remove_page_from_slot` le saca el bit.

**Ni RAM nueva ni opcodes**: el bit 7 de +18 del lugar de ruta no lo usaba
nadie.

# La caché y los lugares de ruta

En el baile pasan a caminar dos más: 8 lugares de ruta de los 12, que la
celebración ya soltó. Con la caché, piden ranura propia (128 + evento) en
vez de compartir pose: el conversor cuenta 17 poses quietas en el 127 en
vez de 18, y el pico estático sigue en 33 contra 30 ranuras (la misma
advertencia de antes; la celebración pide 26). `test_granja.py`, que mira
la VRAM de cada evento cuadro por cuadro, sigue verde.

`just espacio release`, con las herramientas de main y con éstas:

                 antes      después
    bancos       78 de 127  78 de 127
    banco 0      2.810 B    2.757 B
    banco 1      6.647 B    6.583 B
    BSS          125 B      125 B

# Pruebas (en ABL, rama `bailarines`)

* `rpgmaker/test_girar.py`, nueva: los dos que bailan giran en el sentido
  del reloj cada 12 cuadros, sin cambiar de columna, y se mueven; el robot
  del 64 (switches 150 y 207) gira cada 24 y no se mueve.
* `abl/test_recorrido_granja_golden.py`: en el baile, el 37 y la 38 tienen
  que moverse y mostrar los cuatro lados.
* **El rojo**, con las herramientas de main: el recorrido falla con "en el
  baile no se movieron [36, 37]", y `test_girar.py` con "dio 0 cuartos de
  vuelta" en las dos.

Tanda de ABL con estas herramientas: todo verde, con las dos nuevas.
**Ninguna golden se movió**: las de la tanda pasan exactas, y las once del
recorrido de la granja salen byte por byte iguales a las de main —en sus
fotos los que bailan no están en pantalla, o la foto se saca antes de su
primer giro—. Capturas del baile girando en
`/shared/capturas/2026-10-04-bailarines/`.

**No lo cubre la tanda**: un `face_*` o un salto sobre uno que gira, una
ruta forzada sobre él, y una página que gira con otra columna que la del
medio (las cuatro del juego usan la del medio). El robot del 64 sólo se
mira por su fila: en ese momento de la escena no se ve en pantalla.

# Al mergear

Instalar `events`, `mapdata`, `convert` y `cartridge`: `just -f
tools/justfile install events mapdata convert cartridge` (`cartridge`
arma con el runtime).

# Qué tiene que probar taro

* El baile de la granja: que el 37 y la 38 den su cuadrado girando.
* La salida de Lashe (64) cuando el robot AG7-17 está (switches 150 y 207):
  que gire en su lugar.
