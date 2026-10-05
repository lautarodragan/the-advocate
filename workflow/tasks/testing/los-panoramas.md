---
name: "Los panoramas"
description: "Los fondos de parallax de RM2k en la SNES: un estudio de todos los mapas con panorama y un prototipo en el puente de arriba (modo 3 con la paleta repartida) y el de abajo (modo 1, tres capas)"
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
