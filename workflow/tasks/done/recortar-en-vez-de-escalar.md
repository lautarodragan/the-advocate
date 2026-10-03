---
name: "Recortar una imagen en vez de escalarla"
description: "Una opción del motor para que una imagen de pantalla completa se recorte a la ventana de la consola en vez de escalarse; ABL la usa en las cuatro fotos Diff, que son capturas del mapa"
type: feature
assignee: taro
---

De taro, el 2026-10-02 (la tarea del juego está en ABL:
`workflow/tasks/todo/las-fotos-diff-recortadas-y-el-montaje.md`): las fotos
Diff son capturas del mapa a 320x240, y el original las usa para un efecto
de "en vivo a foto". Escaladas a 256 ya no coinciden con el mapa de la ROM.
Recortadas sí, porque la ROM no escala el mapa.

Va encima de `sin-resample` (Corbatita): con `image` en lugar del LANCZOS de
Pillow, las fotos escaladas eligen otros colores al reducirse y la sombra del
árbol pasa de verde a azul. Recortadas no pasan por el escalador. Hornero
propuso esperar a esto antes de mergear `sin-resample`, para que esa versión
no entre nunca, y taro dijo que vaya con lo que le parezca bien. El montaje
del 217 queda para después del piloto del modo 7.

Hecha por Golondrina, desde `main` en `3a188d9f` con la rama de Corbatita
mergeada encima (`2b76713c`); `main` se movió a `ef5f8133` con el mismo
merge, y está mergeado antes de entregar.

## Dónde vive la opción: `[graphics] cropped_pictures`

En `rm2k-snes.toml`, una tabla por nombre de imagen, con el pixel de la
imagen desde donde se corta la pantalla de la consola:

    [graphics.cropped_pictures]
    PhoneCallDiff = [8, 16]

Por qué ahí y no en un parche versionado: los parches son **lo que el
conversor decide perder** —colores fusionados, efectos que no entran— y los
escribe él; esto es una decisión del juego sobre cómo se presenta una
imagen, que el conversor no puede tomar solo porque depende de dónde está
la cámara cuando la escena la muestra. Es la misma clase de cosa que
`[graphics] opaque`: una perilla del motor que el juego prende, por nombre,
sin distinguir mayúsculas como RM2k. Y como toda clave del archivo de
proyecto, **es obligatoria** (vacía, `{}`, en un juego que no recorta nada):
el conversor no tiene valores por omisión para lo que dice el juego.

Lo que hace, de punta a punta:

* `rm2k-snes-convert` la lee al leer el juego (`pictures::Cropped`, en
  `Game`) y le pasa el recorte a la etapa de las imágenes grandes. Una
  imagen recortada **siempre es grande** —es la pantalla—, salvo que su
  `ShowPicture` la ponga por variables, que sigue yendo a los objetos.
* `rm2k-snes-images background` recibe `"crop": [x, y]` en la petición, y
  sólo cuando hay recorte, así la petición de las escaladas es la de
  siempre. Con recorte no escala: el lienzo es la pantalla de la consola,
  cortada de la imagen desde ese pixel, dondequiera que la ponga el
  `ShowPicture`. Se niega si la ventana se sale de la imagen o si el zoom
  no es 100 (el recorte es en los pixeles del archivo).
* Nada más cambia: ni la emisión, ni el runtime, ni el compilador.

El montaje del 217 muestra las mismas cuatro fotos, así que también van
recortadas: es la misma imagen con el mismo nombre.

## El recorte, verificado contra la ROM

Los cuatro mapas son de 20x15, la pantalla de RM2k entera, así que la foto
es lo que mostraba RM2k con la cámara en (0, 0). La ROM centra al héroe
—que llega por un `Teleport` y no se mueve— contra el borde del mapa: de
Chimango, `PhoneCallDiff` y `SurlGravesDiff` desde (8, 16), y `SurlBroDiff`
y `ThreeRubbleDiff` desde (0, 16).

Para verificarlo, en un clon aparte de ABL (no commiteado), un cartucho de
prueba con los mapas 212 a 217 y una página por mapa que entra con el
`Teleport` del juego —(8, 10), (6, 10), (8, 9) y (7, 11)—: la escena de
verdad corre y pone la foto. Se guardó cada cuadro hasta la foto, y se
midió, a 15 bits:

| mapa | foto | la ROM contra el mapa de RM2k | el siguiente |
|---|---|---|---|
| 212 | PhoneCallDiff (8, 16) | 99,5 % idénticos | — |
| 213 | SurlBroDiff (0, 16) | 99,2 % | 81,0 % en (16, 16) |
| 214 | SurlGravesDiff (8, 16) | 83,7 % | 76,1 % en (40, 16) |
| 216 | ThreeRubbleDiff (0, 16) | 96,0 % | 66,7 % en (16, 16) |

"El mapa de RM2k" son sus dos capas dibujadas por `rm2k-render layers`, sin
eventos; lo que no coincide son los personajes (el 214 tiene cien tumbas
que son eventos). El cuadro es el último antes de la foto sin el destello
blanco que la escena pone justo antes. **La cámara de la ROM es exactamente
el recorte de Chimango en los cuatro.**

Y que la foto sea la pantalla de RM2k sin correrse: la correlación de los
bordes entre la foto y el mapa de RM2k da el máximo sin correrla en el 212,
el 213 y el 216, y en el 214 a un pixel por muy poco (0,122 contra 0,116):
es la foto que más cambió respecto del mapa —otras tumbas—. Los bordes de
la pantalla de la ROM contra cada recorte de la foto también dan el máximo
en el recorte, en los cuatro. **Pixel por pixel no coinciden, ni pueden**:
las fotos están retocadas —suavizadas y con grano, el 212 en sepia— y son
otro momento de la escena, que es el punto del efecto; y la ROM reduce los
colores. Lo que coincide es el fondo, sin corrimiento.

La golden nueva de `imagen-grande-foto-5` es, pixel por pixel, la pantalla
de la ROM en el 212 de verdad con la foto arriba; la de
`imagen-grande-fotos-5`, la del 213.

## En ABL

En `/extras/scratch/golondrina/abl`, rama `fotos-recortadas`, encima de
`a64eab2` (los dos commits de Corbatita, que son los de `/shared/abl-snes`):

* `26fc753` pide el recorte en `rm2k-snes.toml`, con los cuatro;
* `a942b02` las goldens, sólo goldens: **siete**, las que muestran las
  fotos —`imagen-grande-foto-5` y `-140`, `imagen-grande-fotos-5`, `-65` y
  `-125`, `imagen-grande-montaje-fotos-3` y `-9`—. Ninguna otra se mueve,
  tampoco las 68 de Corbatita.

`abl.sfc` pasa de `0072d314…` a `8c9e670f…`; los dos cartuchos de prueba
quedan iguales (no llevan las fotos). `just espacio` sobre `release`: 43
bancos libres, igual que antes; los huecos de los bancos usados bajan de
62.373 B a 59.217 B: las fotos recortadas piden unos 3 KB más que las
escaladas (por qué, no lo medí).

Lado a lado —antes de `sin-resample`, con `sin-resample` y recortada, y el
mapa justo antes de cada foto contra la foto— en
`/shared/capturas/2026-10-02-fotos-recortadas/`, con su `LEEME.txt`.
**El merge espera el visto bueno de taro a las siete goldens.**

## Los números

* `just pruebas` en el clon de ABL, con las herramientas de esta rama
  adelante en el PATH —y `main` mergeado, que no cambió nada del árbol—:
  **993** en verde con las goldens nuevas, incluida
  `test_musica_techos.py`. Sin ellas, las tres pruebas de las fotos en rojo
  y nada más.
* `NO_CACHE=1 just cartuchos` y el armado con caché dan el mismo
  `abl.sfc`, `8c9e670f…`.
* `just -f tools/justfile test`: 32.
* `cargo test -p rm2k-snes-images -p rm2k-snes-convert`: en verde, con
  cuatro pruebas nuevas —el recorte en `background.rs`, y la tabla en
  `pictures.rs`—.

## Al mergear

* Instalar `images` y `convert`: `just -f tools/justfile install images
  convert`. Nada de Python cambió.
* **Antes de instalarlos, `/shared/abl-snes` necesita la tabla**: el
  conversor nuevo se niega a correr sin `[graphics] cropped_pictures`. Traer
  primero los dos commits de la rama `fotos-recortadas` del clon
  (`/extras/scratch/golondrina/abl`), que van por fast-forward sobre
  `a64eab2`.
