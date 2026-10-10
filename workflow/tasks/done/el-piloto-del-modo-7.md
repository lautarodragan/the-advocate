---
name: "El piloto del modo 7, para el zoom de las fotos Diff"
description: "Una ROM de prueba que haga el zoom de 100 a 0 % de una foto Diff en modo 7, con las variantes que entren en sus 256 tiles, para que taro la vea en la tele"
type: research
assignee: taro
---

De taro, el 2026-10-02, después de ver el video de Bandurria
(`/shared/capturas/2026-10-01-escenas-diff/`): "me gustaría explorar usar el
modo 7. Lo descartamos porque es muy breve el uso, pero ahora que vi el
video, me doy cuenta que es emocionalmente impactante, y el zoom ayuda
mucho más a transmitir la emoción". El estudio de Jilguero lo había
descartado (opción F): el mapa del modo 7 admite 256 tiles de 8 bits y una
foto entera necesita 896.

Hecho por Chimango, desde `main` en `cb333da4`.

## Lo medido del original

De la grabación cruda de Bandurria (`raw.mkv`, 60 cuadros por segundo),
cuadro a cuadro, en el 212 y el 213, con el ancho de lo que no es negro:

* **El destello** es un `FlashScreen` blanco de fuerza 31 y 0,2 s
  (`11040 [31, 31, 31, 31, 2, 0]` en el 213, el 214 y el 216; el 212 no
  lo tiene, y lo que destella ahí es la animación de batalla 93 de las
  explosiones, encima de la foto). La foto aparece **debajo** del blanco,
  en el mismo cuadro: el brillo medio va de 246 a 102 en 12 cuadros, en
  línea recta.
* **La foto se queda quieta 93 cuadros** en el 213 (el `Wait` de 1,5 s más
  los cuadros de los comandos; en el 212, 118, con la animación de las
  explosiones encima) y **el zoom es lineal**: el ancho baja 1/120 por
  cuadro, de 640 a 0 en 120 cuadros justos, con el centro en el centro de
  la pantalla. No hay aceleración ni frenado: escala = 1 − t/120. Medido
  igual en el 212 y en el 213.
* **El recorte**: los cuatro mapas son de 20x15 —la pantalla de RM2k
  entera—, así que la cámara de RM2k está en (0, 0) y la de la ROM
  (`follow_camera`) donde la deja el héroe, que entra por un `Teleport` y
  no se mueve: PhoneCallDiff y SurlGravesDiff se recortan desde (8, 16) y
  SurlBroDiff y ThreeRubbleDiff desde (0, 16), a 256x224. Lo calcula
  `recorte()` en `armar.py`; la comparación con capturas que pide
  `todo/las-fotos-diff-recortadas-y-el-montaje.md` no se hizo.

## La ROM

`just zoom-modo-7` la arma (`rom/experimentos/zoom-modo-7/`) y la verifica
en snes9x, bsnes y mesen-s; `just zoom-modo-7-videos <originales>
<salida>` graba cada combinación al lado del original. Muestra las
**cuatro fotos** —no sólo PhoneCallDiff: las otras tres tienen ruido, 896
tiles distintos de 896, y son el caso difícil— con **cuatro variantes**
cada una, en loop: negro, la foto con el destello, quieta, el zoom, negro.
Arriba y abajo cambian de foto, izquierda y derecha de variante, B esconde
los dos números de la esquina (foto y variante), Start pausa e Y es cámara
lenta (×8).

1. **media**: la foto a 128x112, promediando de a 2x2 —188 tiles en
   PhoneCallDiff, 225 en las otras—, agrandada al doble con la matriz. Toda
   la escena en modo 7: la foto quieta ya se ve borrosa y pixelada.
2. **híbrida, media**: quieta en modo 1, entera a 4 bits, como la muestra
   hoy el juego (Adeleine en siete paletas, Voodoo), y al primer cuadro del
   zoom pasa a modo 7 con la textura de la 1.
3. **vq**: la foto a resolución completa con 255 tiles distintos, por
   cuantización vectorial: los 896 tiles se agrupan en 255 por su forma
   —promediados de a 2x2, para que el ruido del pasto no decida— y cada
   lugar muestra el tile de la foto más representativo de su grupo. Toda la
   escena en modo 7.
4. **híbrida, vq**: quieta en modo 1 y el zoom con la textura de la 3.

**El destello** es `COLDATA` sumado a BG1 y al fondo, y la tabla de cuánto
blanco va en cada uno de los 12 cuadros se elige por foto para que el
brillo medio siga a RM2k, que mezcla hacia el blanco en vez de sumar. Está
en las cuatro fotos, aunque el 212 original no lo tiene.

### Lo que no se pudo: la híbrida con umbral

El encargo pedía resolución completa en otro modo **mientras la escala
baja hasta un umbral** (60 o 50 %) y el modo 7 de ahí para abajo. **No se
puede**: ni el modo 1 ni el 3 escalan, y achicar una foto de 256x224 por
cuadro en la CPU pide subir decenas de KB por cuadro. Lo único que se puede
mostrar a resolución completa en otro modo es la foto **quieta**, y por eso
las híbridas cambian al empezar el zoom. Y lo que el umbral buscaba —que el
zoom arranque nítido y la falta de resolución aparezca cuando ya no se
nota— lo da la textura vq: es de resolución completa, así que no hay umbral
que esperar. Por debajo del 53 % cualquier textura de 256 tiles alcanza (la
pantalla muestra menos pixeles de los que tiene), y por eso cambiar de
textura a mitad del zoom no aportaría: costaría además tres o cuatro
vblanks de basura, porque los 256 tiles se pisan mientras se ven.

### Lo medido en la ROM

* **La foto quieta**, pixel por pixel a 15 bits contra la esperada: igual
  en las dieciséis combinaciones y los tres cores. Eso cubre la textura
  entera en la VRAM, la matriz a escala 1 y el centro.
* **La curva**: el ancho y el alto de lo que no es negro, en doce cuadros
  del zoom, contra 256·(1 − t/120) por 224·(1 − t/120): dentro de un pixel
  y centrado, en todas. Por ejemplo, t = 30: 191x167 (media) y 193x168
  (vq) contra 192x168; t = 60: 128x112 justo; t = 120: nada.
* **Las híbridas** suben la textura del modo 7 en **8 o 9 vblanks** de 4 KB
  con la foto en pantalla (el mapa de 128x128 entero y los tiles: 30 KB), y
  el cambio de modo con la paleta de 256 colores entra en un vblank: **cero
  cuadros en negro**. El vblank más largo termina en la línea 251 de 261.
* **Los tres cores dan lo mismo** en cada cuadro mirado.
* **Cuánto se parece a la foto**, en dB (pixel a pixel / promediadas de a
  4x4, que mide la forma y no el grano), lo imprime la receta:

      PhoneCallDiff    modo 1 42.5/47.3   media 30.8/42.4   vq 32.7/44.5
      SurlBroDiff      modo 1 27.8/34.1   media 19.3/34.5   vq 17.8/30.5
      SurlGravesDiff   modo 1 33.0/39.5   media 18.3/35.8   vq 16.8/30.1
      ThreeRubbleDiff  modo 1 33.1/37.7   media 16.8/36.1   vq 15.0/27.5

  En PhoneCallDiff, la sepia con zonas lisas, vq gana en todo. En las de
  ruido, media conserva mejor la forma y vq el grano: vq a la vista se ve
  "foto" pero con tiles cambiados de lugar —una lápida o un pedazo de árbol
  que no es el suyo—, y media se ve lavada. Eso lo decide la tele.
* **El salto de las híbridas** es esa misma diferencia: de 42,5 dB (modo
  1) a 30,8 (media) o 32,7 (vq) en PhoneCallDiff. Con media se ve que la
  foto se ablanda en el primer cuadro del zoom; con vq el grano sigue y el
  salto se nota menos.
* **La textura media más grande que entra** en 256 tiles, deduplicando, es
  de 152x136 en PhoneCallDiff y de 136x120 en las otras tres: un 6 % más de
  resolución que 128x112 en las de ruido. No vale una variante.

### Lo que se ve distinto de RM2k

* **La foto recortada achica lo recortado**: en RM2k, al achicarse, se ve
  la foto entera de 320x240; en la ROM, la parte de 256x224 que estaba en
  pantalla. Con la foto chica no se nota; al 80 % sí, si uno compara.
* **El centro** es el de la pantalla de la ROM, que no es el de la foto de
  RM2k: por el recorte, el centro de la foto cae 24 pixeles a la derecha y
  8 arriba del de la pantalla, en PhoneCallDiff. La foto se achica hacia el
  centro de lo que se ve.
* **El modo 7 no filtra**: al achicarse, el grano de las fotos con ruido
  titila de un cuadro al otro, más con vq —que tiene todo el grano— que con
  media. Si en RM2k titila igual, no se midió: está en los videos.
* **El destello suma**: arranca y termina como el de RM2k, y en el medio
  sigue su brillo medio, pero los claros saturan antes.

## El costo de llevarlo al juego

Lo que hoy hace `big_picture.s` con las fotos: los tiles de la foto en modo
1 desde la palabra 0 hasta `$3FFF`, su tilemap en `$4000`, la ventana de
mensajes corrida a `$4800`, sus tiles y los de BG2 arriba de `$5000`; dos
cuadros con la pantalla apagada al mostrarla y catorce al borrarla, que
recarga el mapa. **El modo 7 es dueño de `$0000`-`$3FFF` y no se mueve**:
el mapa de 128x128 en los bytes bajos y los 256 tiles en los altos.

**Variantes 1 y 3, sólo modo 7** —lo más barato—:

* VRAM: **cero de más**. La textura ocupa exactamente el lugar de los tiles
  de la foto de hoy, y la ventana no se toca.
* CGRAM: la paleta del modo 7 es de 256 y pisa la de la ventana (la 0):
  la textura se limita a los colores 16 a 255 —240; en el piloto ninguna
  pasa de 239— y la ventana queda como estaba.
* ROM: por foto, media son 12 a 14 KB de tiles, 1,8 KB de filas del mapa
  (casi todo ceros: con LZ2, casi nada) y 512 bytes de
  paleta; vq, 16 KB, 3,5 KB y 512. **Las cuatro: unos 62 KB con media y 80
  con vq**, más de un banco de 64 KB. Las versiones en modo 1 se quedan,
  porque el montaje del 217 usa las cuatro fotos.
* `big_picture.s`: una entrada de `big_table` con la textura del modo 7;
  `big_load` que la suba —tres DMA: filas por los bytes bajos, el resto del
  mapa en cero con la fuente fija, tiles por los altos— con la pantalla
  apagada, como hoy; `BGMODE` 7, `M7SEL` en `$80`; y `big_move` que, con la
  rampa de magnificación, escriba A y D en el vblank: **una división del
  hardware por cuadro**, K·d / (d − t) con K = 128 (media) o 256 (vq) —16
  bits entre 8—, que es la tabla del piloto sin tabla. Al llegar a 0, BG1
  apagado y `BGMODE` 1, para que los mensajes que siguen en negro vean la
  ventana.
* El conversor (`rm2k-snes-images`): media es un promedio de 2x2 y reducir
  a 240 colores, que es Adeleine `merge`; vq es k-medias determinístico
  sobre los tiles promediados y elegir representantes, unas cien líneas
  nuevas en Rust.
* **Cuadros en negro: los mismos de hoy.** Dos al mostrarla —debajo del
  destello en el 213, el 214 y el 216; sobre el mapa en el 212, el parpadeo
  que ya tiene—, ninguno en el zoom ni al terminar, y los catorce del
  `ErasePicture`, sobre negro.

**Variantes 2 y 4, híbridas**, todo lo anterior y además:

* VRAM: las dos fotos a la vez. La del modo 1 se tiene que ir de
  `$0000`-`$3FFF` a `$4000`-`$7FFF` —28 KB de tiles con ruido, y su
  tilemap—, que **pisa la ventana y los tiles de BG2**. En las cuatro
  escenas no hay mensaje mientras la foto está, así que se puede, si la
  ventana se repone después: unos 10 KB en dos o tres vblanks durante el
  `Wait` de 1 s que sigue al zoom en las cuatro páginas.
* La subida de la textura del modo 7 en el vblank mientras la foto está
  quieta: en el piloto, 8 o 9 vblanks de 4 KB; en el juego el vblank ya
  hace otras cosas, y a 2 KB serían unos 16, contra los 93 cuadros de foto
  quieta. Y el cambio de paleta y de modo en el vblank del primer cuadro
  del zoom, que en el piloto entra.
* ROM: lo mismo que 1 y 3; la foto del modo 1 ya está.
* `big_picture.s`: además, el otro lugar de la foto en modo 1 para estas
  cuatro, la cola de la subida, el cambio, y reponer la ventana.
* **Cuadros en negro: los mismos de hoy**, y cero en el cambio.

**Aparte del modo 7**: el destello con `COLDATA` sirve también para la foto
en modo 1 de hoy —el blanco del 213, 214 y 216 que hoy se corta al
aparecer la foto, `divergencias/lo-que-las-imagenes-grandes-no-modelan.md`—
y para el montaje del 217 de `todo/las-fotos-diff-recortadas-y-el-montaje.md`.

## Qué hay en `/shared/experimentos/2026-10-02-modo-7/`

La ROM, un `LEEME.txt` con las fotos, las variantes, los botones y qué
mirar en la tele, y `videos/`: dieciséis, uno por foto y variante, con el
original a la izquierda y la ROM a la derecha.

**Falta**: que taro la vea en la tele y elija variante —o ninguna—. Al
mergear no hay nada que instalar: no toca Rust ni `tools/`.

# Lo que dijo taro en la tele

El 2026-10-03, después de verla en la SNES: "el modo 7 es definitivamente
la forma de encarar las fotos". Falta elegir variante —media, híbrida
media, vq o híbrida vq— para llevarlo al juego.

taro eligió la **híbrida vq** (variante 4), el 2026-10-03. Va al motor en
`las-fotos-en-modo-7.md`, en el repo de las herramientas.
