---
name: "Los panoramas"
description: "Los fondos de parallax de RM2k en la SNES: el estudio, el prototipo en el puente, y todos los mapas con el camino que el conversor elige solo"
type: research
agents: [Cardón]
assignee: taro
---

De taro, el 2026-10-05: los panoramas se ven negros. Algunos se pueden
resolver con parches creativos —el emitter room como un tile o CharSet
animado, la ventana de la oficina del director y Talan como ChipSet—, pero
otros "son bastante importantes … sobre todo cuando sí tienen efecto
parallax y se mueven a distinta velocidad que el mapa". Los que nombró:

* el puente, arriba —"sólo tiene eventos dibujados sobre el cielo… con dos
  capas debería alcanzar", y "lo mismo aplica para toda la parte de
  arriba"— y abajo —"requiere 3 capas sí o sí, porque el piso es como una
  reja, con porciones transparentes, y están talan y los cofres … se mueve
  distinto el fondo … y se scrollea constantemente"—;
* el techo de Lashe City, escapando de los agentes;
* la intro con Kersh: el cielo nocturno con nubes, y lluvia.

# Lo hecho (Cardón, 2026-10-05)

El estudio está en `docs/research/2026-10-05-los-panoramas.md`: los 45
mapas con panorama medidos —cuánto se ve, cómo se mueve, qué tienen encima
del héroe, qué pierden en cada camino—, el techo y la intro, y el costo.

El prototipo anda en los dos del puente, que en ABL se prenden con
`[maps] panoramas = [259, 255]` en `rm2k-snes.toml`:

* **259, arriba, en modo 3**: el panorama en BG2 a 4 bits, con las paletas
  que el fondo deja. Cae en el mismo pixel que en el RPG_RT.
* **255, abajo, en modo 1**: el mapa a 4 bits en BG1, la capa de encima y la
  ventana en BG2, y el panorama en BG3 a 2 bits, moviéndose solo en
  diagonal.

Lo que salió, en corto:

* el B tal como se pidió sirve para el 255 y no para los del RTP: a 2 bits
  las nubes quedan en 4 colores. **Casi siempre conviene modo 3 con lo de
  encima dibujado abajo**: en el techo de Lashe (33) son dos celdas. Está
  en `wally` para medir (`"mode": 3`), no en el proyecto;
* los mapas de una pantalla que no se mueven —la oficina del director,
  entre otros— se pueden **hornear** en el fondo sin capa: eso es también
  el parche de la ventana;
* **la lluvia ya convive** con el panorama: es de objetos. En modo 1 sube
  una prioridad, como todos los objetos.

RAM: `$7E7E00` a `$7E7EDF` de la lejana, entre el crecimiento y
`CARRY_MAP`. Opcodes: ninguno (el `0x46` no hizo falta).

## Para jugar

En el 259 y el 255: caminar el puente de punta a punta mirando el cielo y
el mar, y abajo quedarse quieto para ver el agua correrse. Lo que más
interesa que se pruebe a mano, porque ninguna prueba de la tanda lo hace:
**abrir el menú, guardar y pelear desde el 255** —el modo 1 tiene que
volver al 3 para las pantallas y al 1 al cerrarlas—. El menú y una pelea
los probé con un caso descartable y andan; guardar y cargar, no.

## Las goldens y los parches

Cambian cinco goldens, todas de estos dos mapas —`capitulo-259-llegada`,
`capitulo-255-llegada` y las tres de `texto`—, y el parche versionado de
cada uno (`parches/auto/mapas/0255.toml` y `0259.toml`: la reja a 4 bits
fusiona 17 colores). **Las goldens no están bendecidas**: van lado a lado
con el original en `/shared/capturas/2026-10-05-panoramas/`. Los parches sí
están regenerados, en su commit de la rama de ABL.

## Al mergear

Reinstalar lo de Rust que cambió y lo que lo compila adentro: `voodoo`,
`adeleine`, `rm2k-render`, `wally`, `images`, `screens`, `mapdata` y
`convert` —`just -f tools/justfile install voodoo adeleine rm2k-render
wally images screens mapdata convert`—. El runtime lo arma
`rm2k-snes-cartridges` del checkout.

# Todos

taro, el 2026-10-05, después del prototipo: "vamos por todos". Los 45 mapas
con panorama, cada uno con el camino que el estudio le asignó, y lo que el
estudio dejó pendiente.

## Lo hecho (Cardón, 2026-10-05, segunda vuelta)

**El camino lo elige Wally, mapa por mapa**, con lo que dicen el mapa y su
panorama y nada más: `Way` en `background/panorama.rs` y `convert` en
`wally/src/layers.rs`. En orden: oculto si la capa de abajo lo tapa entero;
horneado en el fondo si no se mueve contra el mapa —una pantalla de RM2k,
sin desplazamiento propio ni `ChangePBG`—; modo 3 si el mapa no dibuja nada
encima del héroe; **aplanado** si dibuja poco —lo de encima al fondo, y las
celdas de 8x8 que cubre en más de la mitad a la prioridad 1 de BG1, adelante
del héroe—; modo 1 si dibuja más; negro si nada entra. "Poco" es
`ABOVE_LOST_MAX`: a lo sumo cuatro celdas de RM2k de pixeles del lado
equivocado del héroe. El `conversor.log` dice el de cada mapa y por qué no
los anteriores; `parches/auto/mapas/` lo escribe en `[panorama]`.

**`[maps] panoramas` se fue.** Queda `[maps] panorama_ways`, opcional, que
fuerza el camino de un mapa por su nombre: sirvió para medir —forzar el 6
aplanado, el 255 en negro— y ABL no lo usa. Por qué no la lista: taro pidió
que la elección sea del conversor, y una lista de mapas es justamente lo que
no generaliza a otro juego.

Lo que eligió para los de `release` —ver el `conversor.log`—: oculto el 8 y
el 76; horneados la oficina del director y los suyos (19, 34, 43, 45, 82) y
los del recuerdo de Pierson (175, 176); modo 3 el 13, 16, 51, 64, 94, 99,
259 y 313; aplanados la intro (1), el 2, **el techo (33)**, el 95, 109 y 126;
modo 1 el 3, el 6, **la terraza del Hover-Tram (32)**, el 105 y el 255. Los
17 que no están en ningún cartucho se deciden igual cuando entren.

Ninguno quedó en negro. El 64 no entra horneado —611 tiles— y va en modo 3.

Lo pendiente del estudio:

* **La partida** guarda lo que el panorama se corrió solo y cómo lo dejó un
  `ChangePBG`, y la carga lo conserva (`PANO_KEEP`).
* **`ChangePBG`** es `OP_PANORAMA` (0x46): cambia los bucles y la velocidad;
  la imagen no. En el juego hay uno solo, el viaje del Hover-Tram, siempre con
  la misma imagen.
* **El tinte en modo 1** llega al fondo de la pantalla (`pano_backdrop`).
* **Los cuadros perdidos del 255 no son del panorama**: caminando un
  cuadrado se pierde uno cada vez que se baja a (66,8), y con el panorama en
  negro igual. No lo arreglé; lo anoto acá.
* **`adeleine::try_pack`**: en su commit, aparte. Medido sobre los 328 mapas
  del volcado, una celda de más colores que una paleta la tiene sólo la capa
  de encima del 159, que no está en ningún cartucho.
* **`parches/`**: el camino, los tiles que quedaron de los distintos, los
  colores y las fusiones de cada panorama.

Lo que hubo que agregar en el camino: tres repartos de VRAM para modo 3 con
más fondo (la intro aplanada pide 395 tiles), el canal 6 del HDMA para tapar
BG1 debajo de la ventana en un mapa aplanado, las filas de `TileSubstitution`
dibujadas debajo de un mapa aplanado (la intro tiene una en la capa de
encima), y `load_above` que no sube nada a la base de BG2 con el panorama en
modo 3.

**El espacio**, con `just espacio` en ABL: `release` pasa de 29 bancos
libres a 23. Entra entero en la ROM; no hizo falta el `.msu`.

**RAM**: `$7E7EE0` a `$7E7EE6` de la lejana, además de lo del prototipo.
**Opcode**: el `0x46`.

## Las pruebas

En ABL, `pruebas/rpgmaker/test_panorama_golden.py`: la llegada a cada mapa
que muestra su panorama (24 goldens), dos fotos a distinto tiempo en el 94
(modo 3) y el 255 (modo 1) con `PANO_AX` avanzando, los cuatro `ChangePBG`
del Hover-Tram en orden, y guardar y cargar en el 255 —en rojo sin
`PANO_KEEP`—.

Cambian unas 340 goldens: las del 6, el banco de pruebas de la tanda, que
va en modo 1; las de los mapas con panorama; y las de los recorridos que
pasan por uno, que cargan en otros cuadros y se corren un poco después. Dos
pruebas dependían del cuadro exacto y se arreglaron en ABL: la lista larga
de la pelea —escribía el grupo antes de que el caso lo armara— y la carga
descomprimida, que no sabía de la caché de ranuras ni del panorama en BG2.
Todo lado a lado, con el original, en
`/shared/capturas/2026-10-05-panoramas-todos/`.

## Para jugar

La intro, la terraza y el techo del depósito (32, 33), el viaje del
Hover-Tram, abajo del puente, y guardar en cualquiera de ésos y cargar.

## Al mergear

Reinstalar `adeleine` —y lo que lo compila: `wally`, `screens`, `images`—,
`wally`, `mapdata`, `convert`, `events`, `bytecode` —lo compilan `events`,
`convert` y `cartridge`—, `cartridge` y `patches`: `just -f tools/justfile
install adeleine wally screens images mapdata convert events cartridge
patches`.
