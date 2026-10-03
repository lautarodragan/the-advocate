---
name: "Los que entran caminando al auditorio"
description: "En el mapa 18 (Auditorium), WalkIn1 y WalkIn2 entran caminando en RM2k y en la ROM no"
type: bug
assignee: taro
---

De taro, el 2026-09-30, jugando: "en el auditorio hay dos NPCs que entran
caminando; en el juego original entran caminando y en la ROM no".

Son `WalkIn1` (evento 16, en (13,10)) y `WalkIn2` (evento 9, en (6,8)) del
mapa 18. Los mueve la página 1 del evento 36, automática con el switch 77:

    ChangeEventLocation 16 → (10,14)
    ControlSwitches 86 ON          ; WalkIn1 pasa a su página 2
    MoveEvent 16 (frecuencia 8): 0,0,0,0,1,1,1,12
    Wait 5
    ChangeEventLocation 9 → (8,14)
    ControlSwitches 87 ON          ; WalkIn2 pasa a su página 2
    MoveEvent 9: 0,0,0,0,0,0,3,3,12
    Wait 10
    …

Sospecha de Hornero, sin verificar: el cambio de página por el switch, justo
después del `ChangeEventLocation` y antes del `MoveEvent`, pisa la posición o
la ruta. Ver `decisiones/la-pagina-activa-se-congela-hasta-el-refresco.md`.

# Lo que se vio en la ROM

Con `grupo-11-en-18` y el switch 77 prendido desde afuera, cuadro a cuadro
(RAM: `ev_pos_buf`, `npc_buf`, `route_ev` y la OAM):

* **la posición y la ruta están bien**: el 16 aparece en (10,14), sube a
  (10,10) y dobla hasta (13,10), un paso cada 16 ticks; el 9 aparece en
  (8,14) unos 30 ticks después y termina en (6,8). La ruta forzada sobrevive
  al cambio de página —la ranura queda con el bit 0 apagado, y
  `remove_page_from_slot` no toca una forzada—. La sospecha de Hornero no era.
* **lo que no anda es el dibujo**: la fila está visible, sigue al evento y su
  objeto está en la OAM, pero la pantalla no cambia ni un pixel en todo el
  camino. El objeto dibuja un gráfico vacío.

# Lo que hace RM2k

* easyrpg, `Game_Event::RefreshPage`: un cambio de página no toca la posición
  ni la ruta forzada; cambia el gráfico (`SetSpriteGraphic`), la velocidad y
  la frecuencia.
* El RPG_RT de 2015 con Wine, con una copia del juego que arranca en el 18 con
  la escena (la página 1 del 36 sin condición y un `ControlSwitches 77`
  adelante, escrita con `ditto write`): **los dos se ven subir por los
  pasillos**, con el gráfico verde de `Future2` índice 6, de corrido.

# La causa

La página 1 de los dos dibuja `Future2` en el **índice 7, que es un hueco
vacío de la hoja** —un solo color, el transparente—, y la página 2 el índice
6. Un evento que camina y cambia de gráfico se queda con uno solo —"walking
wins", `divergencias/un-evento-que-camina-no-cambia-de-grafico.md`—, y ése
era el de su fila: como ninguna página está activa al cargar, el de la
primera página que dibuja algo, que es el hueco.

No hay un commit que lo rompiera: "walking wins" es de `403eea38`
(2026-09-08) y desde ahí el elegido era el primero. Nunca se vieron. No tiene
nada que ver con la página congelada hasta el refresco: la decisión no se
toca.

# El arreglo

En `rm2k-snes-maps`, antes de contar poses y paletas: `pin_walkers`
(`tools/rm2k-snes/map-sprites/src/npc.rs`). A un evento que camina y cambia
de gráfico, **un hueco de la hoja cuenta como "no dibuja nada"**, que es lo
que es en RM2k: la fila camina con el primer gráfico de sus páginas que tiene
pixeles, y las páginas con el hueco la esconden —van con los gráficos
`outside`, así la página no lleva pose con el bit 7—.

La prueba es `rom/pruebas/rpgmaker/test_rutas_auditorio.py`: que pasen por
la puerta y por el medio del pasillo y terminen sentados, y que donde la ROM
pone su objeto la pantalla sea distinta del pasillo vacío. Con la ROM de
antes, las de posición daban verde y las de dibujo **rojo, 0 pixeles en los
16 ticks** de cada uno.

Cambia la ROM en dos mapas: el 18 y el 44 (Talan Stats), donde Arden y
Saldra tienen el mismo patrón —página 1 con `BLPeople` índice 3, vacío;
página 2 con `Chara2`/`Chara3`—. El 44 no lo miré en pantalla.

No se movió ninguna golden. Capturas, antes, después y el RPG_RT lado a lado,
en `/shared/capturas/2026-09-30-auditorio/`.

# El mismo patrón en otros mapas

`ChangeEventLocation`, un switch que le cambia la página al mismo evento y
`MoveEvent` del mismo, en todos los mapas del volcado: **4 veces en 2
mapas**. Las dos del 18, y Drago y Sern del 167, que tienen una sola página
—el switch los hace aparecer, que la ROM ya hace— y además el 167 no está en
el cartucho. Lo que tenía en común el bug no era el patrón sino el hueco de
la hoja, y eso lo cubre el arreglo en todo el juego: el build cambia sólo el
18 y el 44.

# Queda aparte

La frecuencia: easyrpg, en `RefreshPage`, le pone al evento la frecuencia de
la página nueva (3) aunque tenga una ruta forzada de frecuencia 8, y con eso
pararía 64 cuadros entre paso y paso. En el video del RPG_RT caminan de
corrido, como la ROM, así que no se tocó; no lo medí cuadro a cuadro.

# Al mergear

Instalar `maps` en el global —`just -f tools/justfile install maps`—: el
arreglo es de `rm2k-snes-maps` y de su biblioteca `rm2k-snes-map-sprites`.
Correr `just pruebas` y `just -f tools/justfile test` sobre el árbol
mergeado.
