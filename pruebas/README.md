# Pruebas Automatizadas

Las pruebas del ROM. En Python. Usan libretro para correr el rom.

## Casos

**Cómo se agrega un caso**: un archivo en `pruebas/casos/`, y la prueba lo
pide por el nombre. Entra solo en el cartucho de pruebas. Si corre en otro
mapa que el 6, empieza con un `Teleport` a su mapa y a su celda; para el
grupo de la tanda en un mapa sin nada más están los `grupo-11-en-<mapa>`, y
para el del juego los `en-<mapa>`, con la celda donde el héroe caía cuando
ese mapa era el de arranque de su cartucho.

## ROMs

Hay 3 ROMs — una para el juego normal, y dos para tests:

* `juego`, fiel al ABL original, pero con las limitaciones actuales de este proyecto
* `pruebas`, igual que `juego` pero con extras que ayudan el testing y debugging
* `chico`, pruebas que no entran en `pruebas` o cuida una disposición del cartucho

### Notas

`ChangeEncounterSteps` no está implementado, así que los encuentros de
prueba siguen siendo un flag del cartucho chico.

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
    pruebas/arnes/         consola, tanda, cartuchos y recorrido
