---
name: "La pantalla de título comprimida"
description: "El título ocupa 31,7 KB sin comprimir; en LZ2, por el mismo camino que el Game Over, serían 15,2 KB sin cambiar un pixel"
type: refactor
assignee: Chajá
---

De taro, el 2026-09-28, después de la pantalla de Game Over
(`testing/la-pantalla-de-game-over.md`). Carpincho dejó `pantalla_subir` y
`tools/port/pantalla_completa.py` sin saber qué pantalla suben, para que el
título los use, y midió:

    hoy, sin comprimir                  31.744 B
    LZ2, sin cambiar un pixel           15.241 B   (ahorra 16,5 KB)
    liviana en la ROM + calidad en .msu  2.483 B   (ahorra 29 KB)

taro eligió la segunda: sólo comprimir. La pantalla de título tiene que salir
igual pixel por pixel: la golden `titulo` no cambia.

2026-09-28, en `testing/`: hecho por Chajá en su rama, sobre `main` en
2df404b7. Lo que queda es de taro: ver "Qué tiene que probar taro".

# Qué tiene que probar taro

* **Mirar** el título al encender, sin y con MSU-1: tiene que ser el de
  siempre, y aparecer igual de rápido. Y volver de "Resume the Story" con B:
  el título tiene que volver sin un parpadeo largo.
* Empezar y cargar una partida desde el título, y un Game Over que vuelva al
  título: la pista del título que sigue al empezar
  (`done/la-pista-del-titulo-sigue-al-empezar.md`) no se tocó, pero pasa por
  el mismo lugar.

# Lo que se hizo

* **La imagen viaja por el camino de la de Game Over**: un flujo LZ2 con los
  tiles, el tilemap y los colores (`tools/port/pantalla_completa.py`), y una
  segunda fila en `pantallas_tabla`. `titulo_tiles`, `titulo_celdas` y
  `titulo_cgram` no existen más; el menú sigue sin comprimir, aparte.
* **Los colores del menú van en el mismo flujo**, debajo de los de la imagen
  (`comprimida(..., debajo=)`): CGRAM entera en un DMA, como antes, y sin
  otro DMA en el banco 0.
* **El tilemap de la imagen se mudó** de $4000 a `PANTALLA_MAPA` ($7C00), que
  es donde lo pone `pantalla_subir`. Lo que se ve no cambia; dos `.assert` en
  `titulo.s` cuidan que la imagen y el menú no se pisen en la VRAM.
* **`pantalla_subir` se partió en dos**: `pantalla_descomprimir` (a
  `PANTALLA_BUFFER`) y `pantalla_subir` (de ahí a la VRAM y CGRAM). El Game
  Over llama a las dos seguidas.
* **El título se descomprime en el arranque, antes de la espera de
  BOOT_CUADROS**, y `titulo_subir` sólo lo sube. Ver "Los cuadros".
* **`pantalla_subir` deja el PPU como `ppu_reset`, no en cero.** Ponía
  TMW y CGWSEL en cero, que al Game Over no le importa porque le sigue el
  reset; al título le sigue el mapa, y con TMW en cero la ventana de mensaje
  dejaba de tapar a los objetos: nueve goldens en rojo (`ventana`,
  `hablar-60`, `apertura-830`…), en verde otra vez con TMW en $10 y CGWSEL
  en $30, los valores de `ppu_altos`.

# Los cuadros

Medido con snes9x, cuadro por cuadro desde el reset, contra la golden
`titulo` (scripts descartables):

                                         antes   descomprimiendo   en el
                                                 al mostrarlo      arranque
    el título aparece, desde el reset      43          52             43
    vuelve, desde el B en las ranuras       2          11              2

Descomprimir los 34.304 B son unos nueve cuadros. Hacerlo al mostrar el
título eran nueve cuadros más de negro en los dos caminos, así que se movió
al arranque, que tenía cuadros de sobra esperando BOOT_CUADROS; y al volver
de las ranuras no se descomprime de nuevo, porque nada de lo que corre en el
título escribe el banco $7F. En `release` el buffer termina de llenarse en el
cuadro 42, o sea que **el arranque de una ROM con título se pasa de
BOOT_CUADROS** por uno o dos cuadros: no importa, porque lo que cuenta
cuadros desde el reset es el lazo, y a él se llega después del título. La
cuenta del conversor (`cuadros_del_arranque`) no lo suma, a propósito: cuida
a las ROMs sin título.

# Espacio

`just espacio release`, antes (2df404b7) y después:

    bancos de datos  115 de 124, 9 libres        115 de 124, 9 libres
    huecos           15.250 B                    32.139 B
    banco 0          50 B                        175 B
    banco 1          5.135 B                     5.122 B

El flujo del título son 17.407 B (la imagen, el tilemap y los colores, de
34.304 crudos) contra los 34.304 sin comprimir de antes: los 16,9 KB que se
liberan quedan como hueco en los bancos usados y no alcanzan para liberar un
banco entero. El banco 0 gana 125 B: tres DMA de `titulo_subir` que se fueron.

# Pruebas

Ninguna nueva y ninguna golden cambió. `titulo`, `titulo-2`,
`titulo-ranuras`, `titulo-ranuras2`, `game-over` y las `CINEMATICAS` salen
iguales.

**Un camino que `just pruebas` no ejecuta**: cancelar con B la pantalla de
ranuras y volver al título, que ahora sube la imagen **sin** descomprimirla
de nuevo. Ninguna prueba vuelve al título por ahí. Lo corrí a mano con un
script descartable —la captura sale igual a la golden `titulo`, dos cuadros
después del B, como antes— pero con la SRAM vacía: con ranuras llenas la
pantalla dibuja más cosas, y ninguna escribe el banco $7F según el código,
no según una prueba.
