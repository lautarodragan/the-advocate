# Pruebas Automatizadas

Las pruebas del ROM. En Python. Usan libretro para correr el rom.

    just pruebas                  todas, en paralelo
    just pruebas-rpgmaker         una carpeta: también -abl y -herramientas
    just pruebas -k menu          lo de siempre de pytest pasa tal cual
    PROCESOS=0 just pruebas ...   en serie, para --pdb o -s

Cuántas son y cuántas pasan lo dice la corrida; `python3 -m pytest pruebas
--collect-only -q` las lista sin correrlas.

## Carpetas

    pruebas/rpgmaker/      lo que el motor tiene que hacer igual que RM2k
    pruebas/abl/           lo propio del juego: el recorrido, las piedras,
                           el recuerdo, el cartel, las escenas y cinemáticas
    pruebas/herramientas/  las que no corren ninguna ROM
    pruebas/arnes/         consola, tanda, recorrido y video; y lo que
                           comparten varias pruebas: menu, batalla, datos,
                           dibujo y piedras. Ninguna prueba importa de otra
    pruebas/casos/         las páginas de prueba, una por archivo
    pruebas/golden/        las capturas congeladas: `tanda/` y `playthrough/`
    pruebas/snapshots/     lo que dejó la última corrida en rojo, para mirar
                           al lado de lo esperado. No va a git

Todas usan ABL como material, aunque `rpgmaker/` pruebe el motor: es la
separación que dejaría sacar el juego el día que haya uno golden —ver
`workflow/tasks/wishlist/un-juego-golden-y-dos-repos.md`—.

## Los nombres

    test_<sistema>[_<detalle>][_golden|_dibujo].py

El sistema va primero para que `ls pruebas/*/test_menu*` junte todo lo del
menú. El sufijo dice **contra qué se compara la pantalla**, que es lo que
cambia qué hacer cuando se pone rojo:

* **`_golden`**: contra las capturas congeladas de `pruebas/golden/` —`tanda.golden`,
  o `Recorrido.foto` en las que juegan—. La captura en rojo queda en
  `pruebas/snapshots/tanda/` o `snapshots/playthrough/<tramo>/`, con el mismo
  nombre que su golden: se miran lado a lado. Si el render cambió a
  propósito, **cambiar la golden es un acto deliberado**: va a git, se mira, y
  el commit dice por qué. Si no, es una regresión. Ver `golden/tanda/LEEME.md`.
* **`_dibujo`**: contra lo que dibuja `tools/port/` —`titulo.render_*`,
  `pantallas.*`, `escena.*`—, casi siempre por `arnes/dibujo.py`. La captura y
  la esperada quedan en `pruebas/snapshots/pantallas/`, y el que está mal
  puede ser cualquiera de los dos: la ROM o el dibujo de Python.
* **sin sufijo**: miran estado —WRAM, VRAM, SRAM, ARAM, registros—, o
  pixeles sin nada guardado contra qué compararlos —dos corridas, dos cores,
  una propiedad de la imagen—, o no corren ROM. Lo que falló lo dice el
  mensaje de la aserción.

Un archivo con casos de más de un tipo lleva el sufijo de lo que compara la
pantalla: `test_menu_dibujo` también mira la RAM, y `test_caminar_golden`
también exige que el héroe haya caminado las celdas del plan.

## Qué prueba cubre qué

Todo archivo `test_*.py` de `pruebas/` tiene que estar nombrado en esta
lista, y todo lo nombrado tiene que existir: lo cobra
`herramientas/test_indice.py`.

**Caminar, rutas y la cámara**

* `rpgmaker/test_caminar_golden.py`: el héroe en cada mapa y dirección,
  puertas, plantados, una página automática
* `rpgmaker/test_rutas_golden.py`: rutas forzadas —`MoveEvent`, NPCs,
  gráficos, anclados—
* `rpgmaker/test_velocidad.py`: la velocidad del héroe
* `rpgmaker/test_saltos.py`: teletransportes encadenados
* `rpgmaker/test_salto_atraviesa.py`, `rpgmaker/test_salto_colgado.py`: saltos
  con atravesar, y al final de una ruta forzada
* `rpgmaker/test_salto_velocidad.py`: lo que dura el salto del héroe según
  su velocidad
* `rpgmaker/test_puerta_misma.py`: una puerta al mismo mapa
* `rpgmaker/test_carga_descomprimida.py`: la VRAM, la grilla y los dibujos
  de la animación después de cargar cada mapa y de volver de una pelea,
  contra lo que el conversor dejó sin comprimir
* `rpgmaker/test_camara.py`: la ventana del tilemap contra la cámara
* `rpgmaker/test_accion_propia.py`: la tecla de acción sobre la celda del héroe
* `rpgmaker/test_terreno.py`: `StoreTerrainID`
* `rpgmaker/test_cores.py`: snes9x contra bsnes, para la memoria sin
  inicializar —ver `AGENTS.md`, "La regla que sostiene todo"—
* `rpgmaker/test_pila.py`: la hondura de la pila contra `bancos.PILA`, en
  los caminos más hondos que se conocen

**Eventos y comandos**

* `rpgmaker/test_comandos_golden.py`: los comandos sueltos de página —texto,
  tecla, variables, destello, tinte, timer, pan, sacudir, animación, ventana,
  espera y las ramas de ítem y de actor—
* `rpgmaker/test_animacion_cuadros.py`: cada cuadro de cada animación de
  batalla llega entero a la caja de la VRAM, aunque el cartucho lo guarde sin
  sus tiles vacíos
* `rpgmaker/test_hablar_golden.py`: hablarle a algo: condiciones, giro, cola
* `rpgmaker/test_condicional.py`: `ConditionalBranch`
* `rpgmaker/test_rama_grupo.py`: `ConditionalBranch` "¿está en el grupo?"
* `rpgmaker/test_elegir.py`: `ShowChoice`
* `rpgmaker/test_tecla.py`: `KeyInputProc`
* `rpgmaker/test_autofire.py`: X sostenido es el autofire de A, que RM2k no
  tiene
* `rpgmaker/test_variables.py`: variables
* `rpgmaker/test_oro.py`: `ChangeGold` y su rama
* `rpgmaker/test_items.py`: el inventario desde un evento
* `rpgmaker/test_curar.py`: `FullHeal` y sumar HP desde un evento
* `rpgmaker/test_equipo_y_habilidades.py`: `ChangeEquipment` y `ChangeSkills`
* `rpgmaker/test_sprite_actor.py`: `ChangeSpriteAssociation`
* `rpgmaker/test_sustitucion.py`: `TileSubstitution`
* `rpgmaker/test_posada.py`: `ShowInn`
* `rpgmaker/test_paralelos.py`: la lista de eventos paralelos
* `rpgmaker/test_refresco_con_automatica.py`: el refresco de páginas con una
  automática corriendo
* `rpgmaker/test_compositor.py`: el compositor de texto

**El menú de pausa**

* `rpgmaker/test_menu_golden.py`: el menú, los ítems y el equipo, abiertos y
  de vuelta al mapa
* `rpgmaker/test_menu_dibujo.py`: abrir, el cursor, los HP, el permiso de
  escapar
* `rpgmaker/test_menu_items_dibujo.py`: la pantalla de ítems
* `rpgmaker/test_menu_equipo_dibujo.py`: la pantalla de equipo
* `rpgmaker/test_menu_curar_dibujo.py`: usar una medicina
* `rpgmaker/test_menu_hp_de_la_pelea_dibujo.py`: los HP que deja la pelea
* `rpgmaker/test_tienda_dibujo.py`: la tienda

**La pelea**

* `rpgmaker/test_batalla.py`: HP, daño, turnos, el fin y lo que vuelve a la
  partida
* `rpgmaker/test_batalla_golden.py`: la pantalla, pelear hasta el final, el
  encuentro al azar
* `rpgmaker/test_batalla_escena_dibujo.py`: el fondo y los battlers compuestos
* `rpgmaker/test_fundido_de_pelea.py`: la transición de entrada y de salida
  tapa la carga del paquete de audio
* `abl/test_msu_datos.py`: el fondo leído del `.msu` por el MSU-1, y el
  respaldo del cartucho cuando el `.msu` no es el suyo
* `rpgmaker/test_tropa.py`: las páginas de tropa
* `rpgmaker/test_experiencia_dibujo.py`: la experiencia y el nivel, en la RAM
  y en el menú
* `rpgmaker/test_victoria.py`: lo que la victoria cuenta —la experiencia y
  una página por cada actor que subió—, leído del tilemap
* `rpgmaker/test_game_over.py`: perder una pelea sin manejador

**El título y guardar**

* `rpgmaker/test_titulo_golden.py`: la pantalla de título y la de ranuras
* `rpgmaker/test_titulo_dibujo.py`: sus dos opciones, y las ranuras contra el
  dibujo
* `rpgmaker/test_guardar.py`: guardar y cargar, en la SRAM
* `rpgmaker/test_guardar_golden.py`: la pantalla de ranuras y la vuelta al mapa
* `abl/test_guardar_save_point.py`: guardar caminando hasta el save point

**La música**

* `rpgmaker/test_musica_paquete.py`: las muestras del tema, en la ARAM
* `rpgmaker/test_tema_del_mapa.py`: el tema de cada mapa
* `rpgmaker/test_bateria_suena.py`: lo que la música les escribe a las voces
  de la batería
* `herramientas/test_musica_stream.py`: el stream que arma el conversor: a
  qué voz va cada nota y cuándo se suelta
* `rpgmaker/test_musica_reparto.py`: las ocho voces repartidas nota a nota,
  sobre `escape_newyork` —el acorde entero y los canales que antes no
  sonaban— y sobre el de batalla, cuya melodía no pierde notas
* `rpgmaker/test_musica_escrituras.py`: que el decodificador del stream le
  escriba al DSP lo que el stream dice, cuadro por cuadro
* `rpgmaker/test_musica_techos.py`: que ningún tema recorte con su techo de
  volumen, y que la tabla de techos sea la de la mezcla de hoy
* `abl/test_msu.py`: las pistas de MSU-1

**Lo propio de ABL**

* `abl/test_recorrido_golden.py`: el recorrido largo, jugado desde el título
* `abl/test_recorrido_vipers_golden.py`: el tramo de los Neon Vipers
* `abl/test_escenas_golden.py`: las escenas y cinemáticas
* `abl/test_recuerdo.py`: el recuerdo de CORE y MANTA
* `abl/test_un_ano_antes.py`: el cartel de "1 year earlier"
* `abl/test_piedras.py`, `abl/test_luces.py`: los minijuegos del mapa 11
* `abl/test_puerta_del_10.py`: las puertas del mapa 10 y el switch 231
* `abl/test_hover_tram.py`: el Hover Tram horneado

**El conversor y los generados**, sin ROM

* `herramientas/test_lz2.py`: cada bloque que la ROM descomprime al cargar un
  mapa, ida y vuelta por el compresor y por la referencia
* `herramientas/test_reservas_de_la_wram.py`: que nadie más caiga en la mitad
  alta de la WRAM, que es de la grilla y de la pelea
* `herramientas/test_bancos.py`: el acomodo de bancos
* `herramientas/test_ensamblar.py`: `ensamblar.py`
* `herramientas/test_protocolo.py`: el bytecode: las declaraciones y los
  generados
* `herramientas/test_paginas.py`: las tablas de páginas del lado de Python
* `herramientas/test_parches.py`: los parches versionados contra el
  conversor, sobre `release` armado
* `herramientas/test_fork_mapas.py`: el fork de `parches/manual/`
* `herramientas/test_horneados.py`: los eventos horneados en el mapa
* `herramientas/test_repartos.py`: los repartos de VRAM, su orden y el del 38
* `herramientas/test_sustituciones.py`: el tope de `TileSubstitution`
* `herramientas/test_textos.py`, `herramientas/test_escapes.py`: los cuadros
  de texto rearmados y los escapes `\|` y `\^`
* `herramientas/test_encuentros.py`: los encuentros al azar
* `herramientas/test_lideres.py`: quién puede ser líder
* `herramientas/test_destello_paleta.py`: la paleta de sprite de los líderes
* `herramientas/test_timer_paleta.py`: el cronómetro y sus paletas
* `herramientas/test_indice.py`: que esta lista esté al día

## Casos

**Cómo se agrega un caso**: un archivo en `pruebas/casos/`, y la prueba lo
pide por el nombre. Entra solo en `release`, **apagado**: la partida de
verdad corre la página 0, que es el caso `nada`, y el arnés elige los demás
—ver `PRIMERO` en `tools/ensamblado/cartuchos.py`—. Empieza con un `Teleport`
a su mapa y a su celda: el mapa de arranque es el 4, cuya cinemática corre
sola. Para el grupo de la tanda en un mapa sin nada más están los
`grupo-11-en-<mapa>`, y para el del juego los `en-<mapa>`, con la celda donde
el héroe caía cuando ese mapa era el de arranque de su cartucho.

## ROMs

Son dos, y las pruebas corren sobre los dos. Los arma `just cartuchos`,
que `just pruebas` corre antes; `just build <cual>` arma uno solo:

* `release`, la ROM que se juega, con título y cronómetro, que lleva además
  los mapas de prueba y todos los casos de `pruebas/casos/`: las pruebas que
  juegan —el recorrido, el título, las escenas de la apertura— y las normales.
  El arnés pasa el título solo, por "Begin the Story". Hasta el 2026-09-25
  las normales corrían en otro, `test-main`, sin título ni cronómetro.
* `test-special`, lo que no entra en `release` o cuida una disposición del
  cartucho

Qué lleva cada uno, y por qué, en `tools/ensamblado/cartuchos.py`.

`ChangeEncounterSteps` no está implementado, así que los encuentros de
prueba siguen siendo un flag de `test-special`.

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

## Cosas sin pruebas

Ver `UNTESTED.md`.
