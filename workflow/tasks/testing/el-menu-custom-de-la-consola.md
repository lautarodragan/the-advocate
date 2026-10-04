---
name: "El menú custom de la consola: el estudio y las maquetas"
description: "La Portable Console de ABL como un menú custom del motor, descripto como datos, desde el menú de pausa y a pantalla completa, en vez de sus 61 imágenes; estudio y maquetas, sin tocar la ROM"
type: research
assignee: taro
---

Nació el 2026-10-04 como "las imágenes de la consola, por el MSU-1": taro
había decidido que las más de 40 imágenes de la consola fueran sólo en el
`.msu`. Ese mismo día cambió de idea, antes de que hubiera nada
commiteado: "No tener la consola, creo, no es impedimento para jugar, pero
empeora algo la experiencia. […] creo que podemos convertir todo ese
sistema en algo custom pero genérico — una feature diseñada para armar
menús custom, que siga las mismas reglas que el resto del menú de
items/etc. Entonces no necesitaríamos ninguna imagen. O tal vez solo las
que muestran arte de los personajes". Es la idea de
`wishlist/un-menu-custom-propio.md`, sin el modo 5: hoy hay ancho variable
en baja.

Y dos decisiones suyas para el diseño: **es una opción más del menú de
pausa**, y **siempre a pantalla completa** ("este sistema no permite
renderizar sobre el mapa. Así solucionamos desafíos de VRAM etc.").

El encargo: un estudio con maquetas, **y frenar antes de tocar la ROM**,
porque es diseño y taro lo quiere ver. Lo hizo Lagartija, desde `main` en
`43b552f5`, con ABL en `5b29ba9`.

## Lo hecho

* **El estudio**: `docs/research/2026-10-04-el-menu-custom.md`. El
  inventario página por página, el diseño de la feature, lo que da la VRAM
  entera, y lo que costaría.
* **Las capturas del original y las maquetas**, en
  `/shared/capturas/2026-10-04-menu-custom/`, con su `LEEME.txt`: catorce
  capturas del original con Wine —la ventana de Talan, Arden, Sern y
  Emily, la guía de Talan, sus habilidades, cuatro tablas de auras, las
  almas de Sern y el menú de pausa— y cinco maquetas, cada una lado a lado
  con su original.
* No hay código: ni en la ROM, ni en el conversor, ni en ABL. Ninguna rama
  de ABL.

## Lo que contesta

* **Para avanzar no hace falta**: lo que la consola escribe no lo lee nadie
  más, y no elige nada —las auras no se eligen ahí—. **Para jugar bien,
  sí**: las guías y los contadores de absorción de Talan, las almas de
  Sern, las técnicas de Saldra y de Lerle.
* El diseño elegido: el motor dibuja y navega; el juego declara las
  páginas en un archivo propio que nombra el `rm2k-snes.toml`; el menú
  reemplaza al común 39, así el ítem 81 sigue abriéndolo; los comunes que
  calculan (48 y 49) corren antes de su página.

## Para taro

Mirar las cinco hojas `lado-*.png` y decidir:

* si el diseño va —sobre todo la navegación y que el motor la haga—;
* **el arte**: la cara de cada actor, que no cuesta nada, o los retratos,
  48 KB a 15 colores;
* **el rótulo**: "Console" entra en el menú de pausa, "Portable Console" no;
* si la opción aparece con el ítem 81 en el inventario, como se propone.

Con eso, la implementación es otra tarea: el conversor, la ROM, y en ABL la
transcripción de las trece páginas y seis tablas, con sus goldens.

## Lo que no se hizo

* Las maquetas están dibujadas con las funciones de `rm2k-snes-screens`,
  no capturadas de un cartucho: muestran cómo se vería con las ventanas y
  la fuente que hay, no lo que la ROM ya hace.
* La tanda no se corrió: no cambió nada que entre en una ROM.
