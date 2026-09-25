# Pruebas Automatizadas

Las pruebas del ROM. En Python. Usan libretro para correr el rom.

## Casos

**Cómo se agrega un caso**: un archivo en `pruebas/casos/`, y la prueba lo
pide por el nombre. Entra solo en `test-main`. Si corre en otro
mapa que el 6, empieza con un `Teleport` a su mapa y a su celda; para el
grupo de la tanda en un mapa sin nada más están los `grupo-11-en-<mapa>`, y
para el del juego los `en-<mapa>`, con la celda donde el héroe caía cuando
ese mapa era el de arranque de su cartucho.

## ROMs

Son tres, y la tanda corre sobre los tres. Se arman con `just build <cual>`,
y `just pruebas` los arma solos antes de correr:

* `test-main`, con todos los casos de `pruebas/casos/`: las pruebas normales
* `test-special`, lo que no entra en `test-main` o cuida una disposición del
  cartucho
* `release`, la ROM que se juega: las pruebas que juegan —el recorrido, el
  título, las escenas de la apertura— corren sobre ella

Qué lleva cada uno, y por qué, en `tools/ensamblado/cartuchos.py`.

### Notas

`ChangeEncounterSteps` no está implementado, así que los encuentros de
prueba siguen siendo un flag de `test-special`.

## Cosas sin Pruebas

Ver UNTESTED.md

## Limitaciones

Los emuladores tienen diferencias entre ellos.
`pruebas/rpgmaker/test_cores.py` existe para ayudar con esto.

Los emuladores permiten cosas que el hardware real no.
La prueba manual siempre deberá acompañar cambios grandes o peligrosos.

Casos conocidos:
- snes9x:
  - La carga de la SRAM —un modo de direccionamiento—, 
  - el PPU que se quedaba con los registros del título, 
  - el reset no borra la WRAM

## 

**Un paso intermedio, sin juego golden todavía** —de taro, el 2026-09-18—: las
pruebas se separan en carpetas por **qué** prueban, aunque todas sigan usando
ABL como material. **Hecho** el 2026-09-19, después del 9f:

    pruebas/rpgmaker/      lo que el motor tiene que hacer igual que RM2k
    pruebas/abl/           lo propio del juego: el recorrido, las piedras,
                           el recuerdo, el cartel, las escenas y cinemáticas
    pruebas/herramientas/  las que no corren ninguna ROM
    pruebas/arnes/         consola, tanda, recorrido y video; y lo que
                           comparten varias pruebas: menu, batalla, datos,
                           dibujo y piedras

## Una `Partida` viva por vez

El core de libretro es **uno solo por proceso**, así que dos `Partida` vivas a
la vez comparten la consola: la segunda se lleva puesta a la primera y las dos
corren sobre el mismo estado. Una prueba que quiera comparar dos corridas tiene
que correr una entera, guardarse lo que mire, y recién después arrancar la
otra. Ver `capturas` en `rpgmaker/test_sustitucion.py`.

No falla con un error: falla pareciendo ruido. Lo que se vio la primera vez
fueron 28 pixeles de 57.344 distintos entre dos corridas que tenían la misma
OAM, la misma CGRAM y el mismo `vueltas` —o sea, imposible—, y tablas de RAM
que no eran las suyas.
