---
name: "Mundo 9: la celebración en la granja"
description: "La granja (127) y la arboleda (128) en release: la celebración entra por la caché de ranuras de VRAM, y el fin de la demo pasa a la noche de la celebración"
type: feature
assignee: taro
---

De taro, el 2026-10-03, junto con la caché de ranuras de las herramientas
(`workflow/tasks/*/la-cache-de-ranuras.md` de allá, Yaguareté): "meté el 127
en release si entra". Entra.

Base: ABL `57ef34d`, herramientas `60097b1a`.

# Qué mapas, y dónde corta la demo

    108 "se me hizo tarde": la salida a la granja, el evento 20 (382)
    127 la celebración, la automática del 31 (383): Pierson presenta a
        Talan y le hace la Pregunta dos veces; los de la profesión que
        elige saltan en su lugar. La escena apaga el 383, prende el 389 y
        salta dentro del mapa
    127 el baile (389): Isabella, el 46 (390), y la salida a la arboleda,
        el 27, donde espera Emily
    128 la arboleda: la automática del 2, la orquesta y Pierson; vuelve al
        108 con el 395
    108 Emily da las buenas noches, la automática del 47 (395) —"What a
        day."—, que salta a la casa de Talan con el 396: ahí empieza el día
        siguiente, el trabajo de cada profesión

**El corte es la vuelta de la arboleda**: el fork del 108 cambia el
`Teleport` del 47 a la casa de Talan por el cartel ("END OF THE DEMO / The
next day in Paradise is / not in the cartridge yet. / Thanks for playing!")
y la vuelta al título, y la salida a la granja (eventos 20 y 21) vuelve a
ser la del juego. **La regla**: `below = 129`.

Del 127 no compilan las páginas que saltan al 152 y al 158 (tandas
posteriores), como las puertas del mundo cuyo destino no está.

# Lo que pidió de las herramientas

* **La caché de ranuras**: el 127 no entraba en la VRAM ni con los quietos
  turnándose. Ahora nadie tiene ranura fija: el que entra en pantalla pide
  una. Ver la tarea de allá.
* **Las rutas terminadas sueltan su lugar**: el 127 manda a caminar a
  dieciocho eventos distintos —Pierson y las cuatro profesiones de la
  celebración, los seis que pasean en el baile, Emily y Radin— y la ROM
  tiene doce lugares de ruta. Ahora el tope es doce moviéndose a la vez:
  ver `divergencias/las-rutas-terminadas-sueltan-su-lugar.md` de allá.

# Pruebas

* `abl/test_granja.py`: la celebración cuadro por cuadro, eligiendo
  granjero —siete saltan—, y cada cinco cuadros que cada evento en pantalla
  tenga en la VRAM, en su ranura de la caché, los bytes de su pose en el
  cartucho (`arnes/cache_de_ranuras.py`). Con golden al empezar, con los
  granjeros en el aire y en el baile.
* `abl/test_recorrido_granja_golden.py`: del 108 al cartel del fin y el
  título, con once fotos con golden. En el baile mira además que los seis
  que pasean se muevan: usan los lugares de ruta que la celebración dejó.
* `abl/test_recorrido_paradise_dia_golden.py` termina ahora al llegar a la
  granja: sus dos fotos del cartel y del título se fueron, y la de la
  granja es nueva.
* `rpgmaker/test_cores.py::test_la_cache_de_ranuras`: la celebración en
  snes9x y en bsnes.
* `parches/auto/mapas/`: dos parches nuevos, el 127 y el 128.
* `parches/auto/musica/techos.toml`: rehecho con `just techos`, porque los
  temas nuevos movieron el reparto de las muestras y
  `test_musica_techos.py` daba rojo.

**El rojo**: sin subir la pose al tomar una ranura, las dos de la granja
fallan en el primer cuadro mirado; sin que las rutas terminadas suelten su
lugar, el recorrido falla porque dos de los que pasean no se mueven.

# Lo que no está hecho, y lo que se ve distinto

* **Los del baile aparecen uno o dos cuadros tarde** después del salto
  dentro del mapa: el refresco de páginas que los muestra viene después de
  armar ese cuadro, y piden ranura en el siguiente. Pasa con la pantalla
  recién subida.
* **Los dos que bailan en el lugar** —el 37 y la 38, con ruta propia y la
  animación "girar"— no se mueven en la ROM: el conversor no los cuenta como
  de los que caminan. No es de la caché; no lo seguí.
* La rama de defensor y la de actor no las juega ninguna prueba: la tanda
  elige granjero, que es la que más gente hace saltar.
* La música del 127 y del 128 no se escuchó.

# Al mergear

Herramientas: instalar `wally`, `mapdata`, `convert` y `cartridge`.

# Qué tiene que probar taro

* Desde la salida del pueblo a la granja: la celebración entera, eligiendo
  cada profesión (las tres ramas hacen saltar a gente distinta); el baile,
  hablar con Isabella, y la salida con Emily; la arboleda, y las buenas
  noches con el cartel del fin.
* Que nadie de la celebración aparezca tarde o con la pose de otro, sobre
  todo en el salto al baile.
