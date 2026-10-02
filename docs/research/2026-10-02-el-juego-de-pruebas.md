# El juego de pruebas: ABL afuera, y un juego propio para el motor

> **Medido el 2026-10-02 sobre `3c83b5d8`**, por Leñatero. Es una foto: los
> números son de ese día y este archivo no se actualiza. Lo que dice cuántas
> pruebas hay **hoy** es `just pruebas`; cómo rehacer cada cuenta está al
> final, en "Cómo se midió".

El pedido es de taro, el 2026-10-02: *"empezar el proyecto de tener un
juego de rpg maker 2000 para pruebas"*. Hoy las pruebas de lo que hace RM2k
viven con A Blurred Line sólo porque necesitan un juego, y el runtime ya
vive en `tools/runtime/`. El horizonte es el de
`decisiones/rm2k-plus.md`: un "RPG Maker 2000 PLUS" que porte otros juegos.

Ese mismo día taro fijó la dirección, y este estudio la tiene adentro:

1. **Primero, todo lo de ABL en un solo lugar y fuera de este repo**, en un
   repo propio.
2. **Después, pruebas 100% originales en este repo**, sin una referencia a
   ABL ni un asset con derechos.
3. Los assets: **el reemplazo del RTP de EasyRPG**, otros assets libres que
   él tiene guardados, **assets fabricados** por ahora, **efectos** que él
   puede hacer, y **música** de obras del dominio público con secuencias de
   licencia declarada.


## Resumen

* **El inventario.** Son 999 casos en 138 archivos. Por lo que prueban y no
  por la carpeta: **80 archivos y 605 casos son del motor** y se pueden
  escribir contra un juego sintético —44 que sólo usan a ABL de escenario y
  36 que necesitan contenido que hay que fabricar: peleas, música, imágenes,
  menú—; **20 archivos y 208 casos miran una propiedad sobre todo el
  contenido de un juego** —cada mapa, cada animación, el cartucho armado— y
  corren en los dos; y **38 archivos y 186 casos son de ABL** y se quedan.
* **El juego se escribe como texto, y ya arma un cartucho.** Un juego de
  dos mapas escrito como volcado exacto de Ditto —JSON con sólo lo que no es
  default, los enums por nombre— armó un cartucho que arranca y camina, **en
  0,4 s**, con el RTP de EasyRPG y el SoundFont FluidR3. No hace falta el
  editor, ni siquiera `.lmu`: el conversor lee el volcado. `ditto pack` lo
  vuelve binario para abrirlo en el editor o correrlo en el RPG_RT.
  Para llegar hubo que esquivar **siete supuestos de ABL en las
  herramientas**, que son la primera tarea de la fase 2.
* **Los assets alcanzan casi todos.** El reemplazo del RTP de EasyRPG es
  CC0 o CC-BY 4.0 archivo por archivo y trae ChipSets, CharSets, caras,
  System, título, Game Over, 30 MIDIs y 96 efectos. Le faltan los fondos de
  pelea y casi todos los enemigos, que se fabrican. La fuente ya es libre
  (ttyp0 y Shinonome, las de easyrpg-player), y FluidR3 es MIT. El RTP de
  Don Miguel no sirve: la licencia de Enterbrain lo ata al editor.
* **Separar ABL es factible**, y la historia se conserva con `git
  filter-repo` sobre las rutas que ABL tuvo en cada época. Lo que ABL toma
  hoy de `tools/` fuera del PATH son dos paquetes de Python (`common` y
  `emulator`) y el runtime, que ya se encuentra por la instalación.
* **ABL gana poco en reloj y mucho en mantenimiento.** Sin las del motor,
  su tanda baja de 999 a 394 casos, de 643 a 351 CPU-s (**−45%**), pero de
  86,5 a 73 s de reloj (**−16%**): el reloj lo mandan las pocas pruebas
  largas, y ésas se quedan. Deja de mantener unos 206 casos, unas 360
  goldens y dos cartuchos de prueba: arma sólo `release`.
* **La recomendación son cinco fases**, la primera la separación. El riesgo
  más grande no es técnico: entre la fase 1 y la 2 el motor no tiene
  pruebas de ROM propias, y un cambio en `tools/` se verifica corriendo las
  de ABL desde el otro repo.


## 1. El inventario

### Por carpeta

    carpeta        archivos  casos  CPU-s   la más larga
    rpgmaker             85    662    351   14 s
    abl                  32    251    179   13 s
    herramientas         21     86    112   25 s
    total               138    999    643

Los casos son los que junta pytest —un archivo parametrizado cuenta cada
parámetro—, y el CPU es la suma de lo que tardó cada uno en la corrida, con
16 procesos: la tanda tardó **86,5 s de reloj** con los cartuchos ya
armados.

### Por lo que prueban

La carpeta no alcanza para decidir: `abl/` tiene pruebas del motor (las del
MSU-1, la de los líderes sin gráfico) y `rpgmaker/` tiene pruebas de
sistemas de ABL (AG7, la portable console). Se clasificó cada archivo por
**qué tendría que tener un juego para que la prueba siga diciendo lo
mismo**:

* **M1, motor con ABL de escenario**: un mapa donde pararse y una página de
  prueba. El juego de pruebas alcanza con mapas y eventos.
* **M2, motor con contenido que fabricar**: la regla es del motor, pero
  necesita peleas con sus tropas y battlers, temas con batería o acordes,
  imágenes, un menú con ítems, equipo y caras, un título.
* **M3, motor sobre todo el contenido**: la propiedad vale para cualquier
  juego, pero la cobertura sale de que el juego sea grande —cada mapa del
  cartucho, cada animación, los caminos más hondos de la pila, el cartucho
  armado—. **Corre en los dos juegos**, y en ABL es la que más encuentra.
* **J, del juego**: el recorrido, las escenas, los sistemas de ABL, sus
  parches, sus forks, su índice.

        clase  archivos  casos  CPU-s  líneas
        M1           44    327    113    5186
        M2           36    278    155    8755
        M3           20    208    184    3292
        J            38    186    191    5863

Lo que se muda es M1 y M2: **80 archivos, 605 casos, 268 CPU-s y unas
13.900 líneas**.

### Qué usan de ABL

**Casi todo es un mapa y un caso.** De los 289 casos de `pruebas/casos/`,
**206 los usan sólo pruebas del motor**, 34 sólo pruebas de ABL o M3, 28 los
dos, y 21 no aparecen escritos en ninguna prueba porque se piden armando el
nombre (`grupo-11-en-<mapa>`, `en-<mapa>`). Los mapas que más se repiten son
el 5 y el 6, que están elegidos por ser grandes, abiertos y mudos: eso es
fácil de dibujar a propósito.

Las goldens, contadas por el caso que las nombra: de las 649 de
`golden/tanda/`, **unas 360 son de pruebas del motor** (287 de casos del
motor y 74 de `test_caminar_golden`), 108 de ABL, 81 compartidas y 99 que
el nombre no deja atribuir. Es una cuenta aproximada: el nombre de una
golden no siempre es el de su caso.

### Por archivo

La columna de mapas son los que la prueba nombra —por un `Teleport` de sus
casos o por `ir_al_mapa`—; la última dice qué tendría que tener el juego de
pruebas, o por qué se queda.

| archivo | casos | CPU-s | clase | mapas de ABL | qué hace falta, o por qué se queda |
|---|--:|--:|:-:|---|---|
| `rpgmaker/test_accion_con_ruta.py` | 3 | 1.1 | M1 | — | un mapa y una página |
| `rpgmaker/test_accion_propia.py` | 2 | 0.6 | M1 | — | un mapa y una página |
| `rpgmaker/test_autofire.py` | 6 | 3.8 | M1 | 5 | feature del PLUS |
| `rpgmaker/test_borrar_evento.py` | 1 | 0.5 | M1 | — | `EraseEvent` tras un `Teleport`; hoy el 311 |
| `rpgmaker/test_camara.py` | 3 | 0.8 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_caminar_golden.py` | 75 | 17.6 | M1 | 1, 4, 6, 19, 30, 74, 121 y `grupo-11-en-*` | doce mapas de ChipSets distintos, puertas, prioridades |
| `rpgmaker/test_comandos_golden.py` | 58 | 26.4 | M1 | 1, 2, 5, 6, 7, 73, 95, 133, 255, 269, 348 y `grupo-11-en-*` | 49 casos; una imagen, una animación de batalla, un cofre con llave |
| `rpgmaker/test_compositor.py` | 2 | 0.5 | M1 | — | un mapa y una página |
| `rpgmaker/test_condicional.py` | 4 | 0.7 | M1 | 5 y `en-*` | un mapa y una página |
| `rpgmaker/test_cronometro_condiciones.py` | 2 | 0.6 | M1 | — | una rama y una condición de página por cronómetro |
| `rpgmaker/test_direccion_trabada.py` | 4 | 0.8 | M1 | 6, 9 | un mapa y una página |
| `rpgmaker/test_elegir.py` | 6 | 1.8 | M1 | 348 | una elección; hoy el Insta-Shave del 7 |
| `rpgmaker/test_encuentro_cada_paso.py` | 1 | 0.3 | M1 | 21 | un mapa con encuentros, en su propio cartucho |
| `rpgmaker/test_etiquetas.py` | 1 | 0.9 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_guardar.py` | 7 | 1.8 | M1 | 5, 6 | un save point |
| `rpgmaker/test_hablar_golden.py` | 15 | 9.3 | M1 | 7, 8, 9, 10, 13 | NPCs con condiciones de página |
| `rpgmaker/test_items.py` | 3 | 0.4 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_llamada_compartida.py` | 2 | 0.5 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_lugar_recordado.py` | 5 | 2.1 | M1 | 3, 6, 60, 61 | un mapa y una página |
| `rpgmaker/test_numero.py` | 3 | 1.6 | M1 | — | un `InputNumber`; hoy la puerta de Drust Camp |
| `rpgmaker/test_oro.py` | 4 | 3.0 | M1 | 7, 8 | `ChangeGold` y su rama; hoy dos escenas del juego |
| `rpgmaker/test_paralelos.py` | 2 | 0.5 | M1 | 11 | un mapa con muchas paralelas (hoy el 11) |
| `rpgmaker/test_pasos_de_encuentro.py` | 4 | 0.8 | M1 | 5, 66 | mapas con encuentros |
| `rpgmaker/test_posada.py` | 5 | 2.0 | M1 | 20 | un `ShowInn` |
| `rpgmaker/test_puerta_misma.py` | 2 | 1.2 | M1 | — | un mapa y una página |
| `rpgmaker/test_rama_grupo.py` | 2 | 0.3 | M1 | 6 | un mapa y una página |
| `rpgmaker/test_refresco_con_automatica.py` | 1 | 0.1 | M1 | 4 | un mapa y una página |
| `rpgmaker/test_repeticion.py` | 5 | 1.1 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_rutas_golden.py` | 41 | 19.6 | M1 | 6, 10, 20, 70 | un mapa grande, abierto y mudo (hoy el 6) |
| `rpgmaker/test_salto_atraviesa.py` | 1 | 0.6 | M1 | — | un mapa y una página |
| `rpgmaker/test_salto_bloqueado.py` | 4 | 0.7 | M1 | 6 | un mapa y una página |
| `rpgmaker/test_salto_colgado.py` | 4 | 0.6 | M1 | 5, 6 | un mapa y una página |
| `rpgmaker/test_salto_velocidad.py` | 3 | 0.4 | M1 | 6 | un mapa y una página |
| `rpgmaker/test_saltos.py` | 3 | 1.1 | M1 | 4 | un mapa y una página |
| `rpgmaker/test_sonido_en_ruta.py` | 3 | 0.6 | M1 | 10 | efectos de sonido |
| `rpgmaker/test_sprite_actor.py` | 4 | 0.7 | M1 | 5, 6 | un mapa y una página |
| `rpgmaker/test_sustitucion.py` | 2 | 0.9 | M1 | 1, 6 | un mapa y una página |
| `rpgmaker/test_tecla.py` | 7 | 1.7 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_teletransporte_contra_rm2k.py` | 4 | 0.5 | M1 | 5 | volver a medir en el RPG_RT: el juego empacado con `ditto pack` |
| `rpgmaker/test_terreno.py` | 7 | 0.5 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_variable_en_texto.py` | 1 | 0.4 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_variables.py` | 5 | 0.9 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_velocidad.py` | 3 | 1.2 | M1 | 5 | un mapa y una página |
| `rpgmaker/test_velocidad_con_l_y_r.py` | 7 | 1.9 | M1 | 1, 5, 6 | feature del PLUS |
| `abl/test_msu.py` | 12 | 4.7 | M2 | 3, 5 | pistas de MSU-1 de los temas |
| `abl/test_msu_datos.py` | 7 | 17.0 | M2 | 5 | un fondo de pelea en el `.msu` |
| `abl/test_msu_efectos.py` | 5 | 2.3 | M2 | 3, 6, 10 | efectos de calidad en el `.msu` |
| `rpgmaker/test_batalla.py` | 27 | 15.2 | M2 | 2, 5 | tropa, enemigos, habilidades, ítems; el modelo de `rm2k-snes-battle` |
| `rpgmaker/test_batalla_escena_dibujo.py` | 6 | 3.8 | M2 | 7, 60 | fondo y battlers |
| `rpgmaker/test_batalla_golden.py` | 13 | 2.8 | M2 | 6, 21 | fondo, battlers y animaciones de pelea |
| `rpgmaker/test_bateria_suena.py` | 1 | 0.2 | M2 | — | un MIDI con batería |
| `rpgmaker/test_curar.py` | 9 | 2.5 | M2 | 5, 20, 23 | una pelea perdida con manejador; `FullHeal` |
| `rpgmaker/test_equipo_y_habilidades.py` | 7 | 2.9 | M2 | 5, 6 | armas, armaduras y habilidades |
| `rpgmaker/test_eventos_de_tropa.py` | 7 | 6.0 | M2 | 60 | páginas de tropa por turno y HP, enemigos ocultos |
| `rpgmaker/test_experiencia_dibujo.py` | 12 | 5.7 | M2 | 5, 20 | curvas de experiencia y caras |
| `rpgmaker/test_fin_del_juego.py` | 4 | 1.0 | M2 | 21 | el menú y el título |
| `rpgmaker/test_fundido_de_pelea.py` | 3 | 6.0 | M2 | — | una pelea con su paquete de audio |
| `rpgmaker/test_fundido_del_tema.py` | 1 | 0.3 | M2 | 3 | un tema y efectos |
| `rpgmaker/test_game_over.py` | 13 | 3.9 | M2 | 5 | una pelea sin manejador y la imagen de Game Over |
| `rpgmaker/test_guardar_golden.py` | 6 | 1.3 | M2 | 73 | un save point y caras |
| `rpgmaker/test_imagenes_golden.py` | 9 | 5.0 | M2 | 12, 81, 95, 311 | imágenes chicas; hoy también escenas del juego |
| `rpgmaker/test_imagenes_grandes_golden.py` | 9 | 5.3 | M2 | 12, 49, 69 | imágenes de pantalla entera |
| `rpgmaker/test_menu_curar_dibujo.py` | 11 | 2.4 | M2 | 5 | medicinas y caras |
| `rpgmaker/test_menu_dibujo.py` | 10 | 2.0 | M2 | 5 | grupo con caras |
| `rpgmaker/test_menu_equipo_dibujo.py` | 6 | 1.9 | M2 | 5, 73 | equipo inicial y equipable |
| `rpgmaker/test_menu_golden.py` | 20 | 4.1 | M2 | 73 y `grupo-11-en-*` | ítems, equipo y caras |
| `rpgmaker/test_menu_hp_de_la_pelea_dibujo.py` | 3 | 1.1 | M2 | 5 | una pelea y el menú |
| `rpgmaker/test_menu_items_dibujo.py` | 7 | 3.1 | M2 | 5, 73 | dieciséis ítems de varias clases |
| `rpgmaker/test_musica_escrituras.py` | 7 | 30.3 | M2 | — | temas cualesquiera |
| `rpgmaker/test_musica_paquete.py` | 11 | 4.6 | M2 | 2, 3, 10, 38 | temas por mapa |
| `rpgmaker/test_musica_reparto.py` | 3 | 0.3 | M2 | — | un tema con acordes de tres notas; hoy `escape_newyork` |
| `rpgmaker/test_sistemas_de_tropa.py` | 12 | 4.8 | M2 | 60 | páginas de tropa que cambian el grupo y los HP; hoy los sistemas de ABL |
| `rpgmaker/test_tema_del_mapa.py` | 3 | 0.8 | M2 | 21 | mapas con tema propio, heredado y ninguno |
| `rpgmaker/test_tema_que_ya_suena.py` | 1 | 0.3 | M2 | 3 | dos `PlayBGM` del mismo tema |
| `rpgmaker/test_tienda_dibujo.py` | 3 | 2.3 | M2 | 10 | tres tiendas |
| `rpgmaker/test_titulo_dibujo.py` | 15 | 5.9 | M2 | — | una imagen de título |
| `rpgmaker/test_titulo_golden.py` | 4 | 0.6 | M2 | — | una imagen de título |
| `rpgmaker/test_tropa.py` | 2 | 1.4 | M2 | 6 | una habilidad de switch y su página de tropa |
| `rpgmaker/test_victoria.py` | 6 | 2.1 | M2 | 60 | enemigos que sueltan oro e ítems |
| `rpgmaker/test_volumen_y_tempo.py` | 3 | 0.8 | M2 | 3 | un tema a otro volumen y tempo |
| `abl/test_lider_sin_grafico.py` | 104 | 14.1 | M3 | — | cada mapa del juego |
| `herramientas/test_bancos.py` | 1 | 0.0 | M3 | — | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_cartuchos.py` | 6 | 0.3 | M3 | — | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_destello_paleta.py` | 3 | 3.2 | M3 | — | las paletas de los líderes |
| `herramientas/test_encuentros.py` | 10 | 0.9 | M3 | — | los encuentros del juego |
| `herramientas/test_espacio.py` | 6 | 2.5 | M3 | — | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_horneados.py` | 3 | 73.7 | M3 | — | los horneados de cada mapa |
| `herramientas/test_lideres.py` | 2 | 2.3 | M3 | — | los líderes del juego |
| `herramientas/test_linter.py` | 3 | 1.5 | M3 | — | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_lz2.py` | 4 | 0.6 | M3 | — | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_paginas.py` | 10 | 12.2 | M3 | — | Cotorra la lleva a `rm2k-snes-events` |
| `herramientas/test_protocolo_contra_el_juego.py` | 5 | 0.8 | M3 | — | todas las páginas; cambia con los bytecodes en Rust |
| `herramientas/test_reservas_de_la_wram.py` | 4 | 0.0 | M3 | — | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_saltos_entre_bancos.py` | 4 | 6.0 | M3 | 6 | sobre el cartucho armado: corre con cualquier juego |
| `herramientas/test_textos_del_juego.py` | 2 | 1.6 | M3 | — | los textos de `data/` |
| `herramientas/test_timer_paleta.py` | 2 | 2.0 | M3 | — | el cronómetro y sus paletas |
| `rpgmaker/test_animacion_cuadros.py` | 3 | 8.1 | M3 | 6 | cada animación del cartucho |
| `rpgmaker/test_carga_descomprimida.py` | 6 | 20.1 | M3 | 52 | cada mapa del cartucho |
| `rpgmaker/test_cores.py` | 21 | 31.5 | M3 | 2, 4, 5, 6, 7, 12, 28, 60, 61, 68, 69, 73, 108, 312 y `grupo-11-en-*` | diecisiete casos en dos cores |
| `rpgmaker/test_pila.py` | 9 | 2.2 | M3 | 6, 10, 11, 73 y `grupo-11-en-*` | los caminos más hondos que se conocen, que son de ABL |
| `abl/test_capitulo.py` | 5 | 1.4 | J | 5 | del juego |
| `abl/test_escenas_golden.py` | 29 | 42.3 | J | 2, 3, 5, 7, 8, 9, 10, 17 | del juego |
| `abl/test_guardar_save_point.py` | 3 | 4.0 | J | 4 | del juego |
| `abl/test_hover_tram.py` | 2 | 0.5 | J | 32 | del juego |
| `abl/test_luces.py` | 2 | 0.6 | J | 11 | del juego |
| `abl/test_mapa_de_debug.py` | 21 | 9.6 | J | — | del juego |
| `abl/test_mundo.py` | 2 | 0.7 | J | 5 | del juego |
| `abl/test_paradise.py` | 6 | 2.0 | J | 5 | del juego |
| `abl/test_piedras.py` | 6 | 2.7 | J | 11 | del juego |
| `abl/test_puerta_del_10.py` | 2 | 0.5 | J | — | del juego |
| `abl/test_recorrido_capitulo_golden.py` | 1 | 13.1 | J | — | del juego |
| `abl/test_recorrido_carrera_golden.py` | 2 | 5.8 | J | — | del juego |
| `abl/test_recorrido_golden.py` | 2 | 4.4 | J | 3 | del juego |
| `abl/test_recorrido_lashe_cierre_golden.py` | 3 | 9.6 | J | — | del juego |
| `abl/test_recorrido_lashe_golden.py` | 6 | 6.8 | J | 37, 38, 47 | del juego |
| `abl/test_recorrido_lashe_planta_golden.py` | 3 | 4.6 | J | 48 | del juego |
| `abl/test_recorrido_lashe_wick_golden.py` | 2 | 7.8 | J | 37 | del juego |
| `abl/test_recorrido_paradise_golden.py` | 1 | 2.3 | J | — | del juego |
| `abl/test_recorrido_sorbe_golden.py` | 1 | 5.0 | J | — | del juego |
| `abl/test_recorrido_tangle_golden.py` | 1 | 4.3 | J | — | del juego |
| `abl/test_recorrido_vipers_golden.py` | 1 | 1.4 | J | — | del juego |
| `abl/test_recorrido_vipers_otras_ramas_golden.py` | 3 | 3.6 | J | 8 | del juego |
| `abl/test_recuerdo.py` | 2 | 2.1 | J | — | del juego |
| `abl/test_sorbe.py` | 4 | 1.0 | J | 5, 69 | del juego |
| `abl/test_tangle.py` | 2 | 0.5 | J | 5 | del juego |
| `abl/test_un_ano_antes.py` | 2 | 1.5 | J | — | del juego |
| `abl/test_video.py` | 4 | 1.8 | J | — | del juego |
| `abl/test_yun_y_drust.py` | 5 | 1.5 | J | 5 | del juego |
| `herramientas/test_fork_mapas.py` | 9 | 2.6 | J | — | los forks de ABL |
| `herramientas/test_goldens_del_recorrido.py` | 2 | 0.3 | J | — | las goldens del recorrido |
| `herramientas/test_indice.py` | 3 | 0.0 | J | — | el índice de las pruebas de ABL |
| `herramientas/test_lado_de_abl.py` | 4 | 1.5 | J | — | la frontera de ABL |
| `herramientas/test_parches.py` | 2 | 0.0 | J | 6 | los parches de ABL |
| `herramientas/test_perillas_repetidas.py` | 1 | 0.0 | J | — | el `rm2k-snes.toml` de ABL |
| `rpgmaker/test_ag7_y_la_planta.py` | 8 | 3.1 | J | 60 | AG7-17 y sus piezas; la IA de enemigos, a M2 aparte |
| `rpgmaker/test_consola_portatil.py` | 4 | 1.0 | J | 5 | el sistema del ítem 81; lo genérico ya lo cubren otras |
| `rpgmaker/test_musica_techos.py` | 26 | 40.5 | J | — | la tabla de techos de ABL |
| `rpgmaker/test_rutas_auditorio.py` | 4 | 0.4 | J | 18 y `grupo-11-en-*` | una escena del 18 |

### Lo que cambia con Cotorra

Cuando termine `las-pruebas-sin-opcodes.md`, ninguna prueba de Python usa el
bytecode: `herramientas/test_paginas.py` pasa a las pruebas de
`rm2k-snes-events`, `herramientas/test_protocolo_contra_el_juego.py` cambia
con los bytecodes en Rust, y `arnes/events.py` (1.391 líneas) y
`arnes/event_opcodes.py` (230) se achican o se van. **Este plan cuenta con
eso**: ningún paso de acá mueve código del arnés que hable el bytecode, y
lo que Cotorra deje como caso de `pruebas/casos/` se clasifica igual que
cualquier otro.


## 2. Fase 1: ABL afuera

### Qué es de ABL hoy

**Todo `rom/`**: 2.024 archivos versionados.

    rom/data/         31 MB    el volcado del juego
    rom/parches/      1,9 MB   lo que se decidió sobre el juego
    rom/pruebas/      16 MB    las pruebas, sus casos y sus goldens
    rom/justfile, rom/rm2k-snes.toml, rom/pytest.ini

**Fuera de `rom/`**:

* `justfile` de la raíz: sólo importa el de `rom/`, y dice él mismo que se
  borra al partir el repo.
* `tools/assembly/entregar.py` (`abl-entregar`): es de ABL, como dice
  `tools/README.md`. Usa `common`.
* `docs/` y `workflow/`: la clasificación ya existe, en
  `workflow/tasks/testing/decisiones-y-divergencias-por-repo.md`. De
  `decisiones/` y `divergencias/`, 59 van con las herramientas, 1 con ABL y
  6 son mixtas; de `docs/`, son de ABL `inspeccion-integral-del-repo.md` y
  mitades de `rtp.md` y `pipeline.md`. `workflow/tasks/` y `ESTADO.md` son
  casi todos de ABL.
* `README.md` y `AGENTS.md`: mezcla; cada repo necesita el suyo. `DITTO.md`
  habla de `data/` como fuente de verdad, que es de ABL.
* **Los comentarios**: 65 archivos de `tools/` nombran a ABL, casi todos en
  el runtime y en las etapas del conversor. La decisión de las herramientas
  dice que se quedan por ahora, y no son pruebas: el punto 2 de taro no los
  toca.

### La historia

La historia de este repo son 2.224 commits. Por lo que tocan:

    sólo docs, workflow o la raíz       580
    las dos cosas                       529
    merges sin cambios propios          394
    sólo herramientas o runtime         530
    sólo ABL                            191

**`git subtree split --prefix=rom` no sirve**: `rom/` es ABL recién desde
la mudanza del 2026-09-29 (`3b3f8db6`). Antes, ABL estuvo en `data/`,
`parches/`, `pruebas/` y `pytest.ini` en la raíz; al principio, en `Maps/`,
`Chipset/` y `Charset/` —los `.lmu` y los PNG del juego, commiteados el
primer día—; y en `juego/`, `tiles/`, `poc/assets/` y `poc/screenshots/`.
Y `rom/src/` era el runtime. Un split por prefijo perdería todo lo de antes
del 29.

**`git filter-repo` sí**, sobre un clon y con la lista de rutas históricas:
deja los 720 commits que tocan ABL (191 + 529) y, en los que tocaban las
dos cosas, sólo la mitad de ABL con el mensaje entero. Los mensajes van a
nombrar cambios de herramientas que ya no están en ese repo: es aceptable,
porque el `git log` es el registro. `filter-repo` reescribe los hashes, y
reescribe también los hashes abreviados que aparecen en los mensajes; los
que aparecen en archivos —`c64e4d9` en `AGENTS.md`, los de los
research— no.

**En este repo, `git rm` y no reescribir.** Reescribir esta historia
rompería cada worktree, cada rama y cada hash citado, y no hace falta
mientras el repo sea privado. Si alguna vez se publica, ahí sí hay que
purgarla: además de las rutas de ABL, `poc/build/rm2k.sfc` es una ROM
armada con ABL, y es el único binario de arte o de audio fuera de esas
rutas en toda la historia. Los siete PNG de `tools/` son de las pruebas de
los crates, fabricados por fórmula.

`git filter-repo` no está instalado; en Arch es el paquete
`git-filter-repo`.

### Cómo encuentra ABL a las herramientas

**Los ejecutables ya están en el PATH**, y `test_lado_de_abl.py` cobra que
el lado de ABL no nombre `tools/`. Lo que queda:

* **El runtime** lo encuentra `rm2k-snes-cartridges` por la ruta del
  checkout desde el que se instaló (`suite.rs` en `rm2k-snes/project/`):
  sigue andando con ABL en otro repo mientras el checkout de las
  herramientas exista. Embeberlo en el binario, como dice la decisión de
  las herramientas, es lo que lo deja instalar sin el checkout, y no hace
  falta para la fase 1.
* **Dos paquetes de Python**: las pruebas de ABL importan `common` (16
  veces) y `emulator` (4), con `../tools` en el `pythonpath` de
  `rom/pytest.ini`. Es lo único que ABL toma de `tools/` como fuente. La
  propuesta es que `install` los deje en un directorio de la instalación y
  que un ejecutable lo diga —por ejemplo `rm2k-snes-python-path`—, y que el
  `justfile` de ABL lo exporte en `PYTHONPATH`. ABL sigue conociendo sólo el
  PATH.
* **`install-local`**: la receta de `rom/justfile` que frena a un worktree
  sin su `bin/` arma la ruta de `tools/justfile` con `git rev-parse`.
  Pasa a una variable que diga dónde está el checkout de las herramientas.
* **La versión**: la decisión de las herramientas pide que el juego
  declare con qué versión de la suite se arma. Con dos repos deja de ser un
  detalle: es lo que ata las goldens de ABL a un motor.

**El arnés se va entero con ABL en la fase 1.** Hasta que exista el juego
de pruebas, las 999 pruebas siguen siendo de ABL —es la opción b) que taro
eligió en la decisión de las herramientas—, así que no hay por qué partir
el arnés todavía. Se parte en la fase 2, cuando haya otro juego que lo
use.

### Qué queda en este repo

`tools/` entero —la suite, el runtime, sus pruebas—, `docs/` y `workflow/`
de las herramientas, y, desde la fase 2, el juego de pruebas.

### Riesgos

* **El motor sin pruebas de ROM.** Entre la fase 1 y la 2, un cambio en
  `tools/` sólo se verifica corriendo `just pruebas` en el checkout de ABL
  con las herramientas del cambio. Hoy eso lo hace la misma receta; mañana
  es un paso que hay que acordarse de dar, y los sub-agentes trabajan en
  worktrees de un solo repo. **Es el argumento para no demorar la fase 2.**
* **Dos repos en el mismo ambiente.** `install-local`, los worktrees y la
  entrega de builds hoy suponen un repo. Con dos, un agente que toca las
  herramientas y quiere ver ABL necesita las dos copias y saber cuál usa.
* **Una ruta histórica que se olvide** deja material de ABL en el repo
  equivocado o le saca historia a ABL. Se comprueba después: en el repo de
  ABL, `git log --all --format= --name-only | sort -u` no puede tener nada
  de `tools/`; y si este repo se purga algún día, al revés.
* **Mergear lo que esté en vuelo.** Las ramas de los agentes que tocan
  `rom/` tienen que entrar antes del corte: después no hay merge posible
  entre los dos repos.


## 3. El juego de pruebas

### Los assets

**El RTP de Don Miguel no se puede usar.** Es la traducción al inglés, de
2000, del RTP japonés de ASCII/Enterbrain. Su `Readme.txt` no tiene
licencia: tiene una dirección web y "Do not change any of standard RTP
files EVER!!!". Lo que rige es la licencia de Enterbrain, que —según la
cita que circula en los foros del editor— prohíbe "distribute, assign,
lease, sublicense […] the RTP SOFTWARE and/or its data" sin permiso
escrito, y lo ata a juegos hechos con el editor. El README del reemplazo de
EasyRPG dice lo mismo con otras palabras: "original RPG Maker RTP can't be
distributed freely". No encontré el texto original de la licencia, sólo esas
dos fuentes.

**El reemplazo de EasyRPG** (`github.com/EasyRPG/RTP`, clonado en el commit
`993d88c` del 2025-04-05) es lo que taro proponía, y sirve:

* **La licencia** es por archivo, en su `AUTHORS.md`: cada uno es **CC0 o
  CC-BY 4.0** (unos pocos dicen también OGA-BY), con su autor. CC-BY pide
  atribución: el juego de pruebas lleva un `AUTHORS` con la de cada archivo
  que use.
* **Lo que trae**, en el formato de RM2k (PNG indexados, ChipSets de
  480x256): 8 ChipSets (CC0, de Jason Perry), 17 CharSets, 5 FaceSets
  (CC0), 5 System (CC-BY), 4 títulos (CC0), un Game Over, 13 panoramas,
  3 animaciones de pelea, **30 MIDIs** y **96 efectos**.
* **Lo que no trae**: fondos de pelea (ninguno) y enemigos (uno, `Hornet`).
  Ésos se fabrican.
* **Los nombres no son los del RTP** (`Actor1` en vez de `Chara1`): por eso
  `docs/rpgmaker/rtp.md` dice que a ABL no le sirve. A un juego hecho para
  él, sí.
* **El System no entra como viene.** La ventana de mensajes de la consola
  tiene 15 colores, y el del texto tiene que caer antes de la entrada 9; los
  cinco System del reemplazo tienen 32 colores en la ventana. Hay que
  dibujarle uno al juego, o reducirlo con cuidado: es un límite de la
  consola, no de ABL.

**La fuente ya es libre.** El port no usa la de RM2k: usa las dos de
easyrpg-player (`rm2k-snes/text/src/glyphs.rs`), ttyp0 —licencia ttyp0, que
deja redistribuir y modificar renombrando— y la `rmg2000` de Shinonome, de
dominio público. El bloqueo de la wishlist sobre la fuente del sistema no
aplica.

**El SoundFont**: ABL usa el Microsoft GS Wavetable Synth, que no es libre.
**FluidR3_GM es MIT**, según el paquete del sistema que lo instala
(`soundfont-fluid`, "custom:MIT"). Es una entrada de la máquina —un flag—,
no algo que vaya al repo, pero sus muestras terminan en el cartucho: para
que el cartucho del juego de pruebas se pueda distribuir, tiene que salir
de uno libre.

**La música, además de los 30 MIDIs del reemplazo**: Mutopia publica
partituras de obras del dominio público con su MIDI, y cada pieza declara
su licencia en su página —"Public Domain", CC-BY o CC-BY-SA—. La de la
pieza 1, mirada: "Public Domain", con LilyPond, MIDI y PDF. La página de
licencias no dice explícitamente que la licencia cubra el MIDI, así que lo
más limpio es **elegir piezas de dominio público y generar el MIDI desde su
LilyPond**, que es un derivado mecánico de una fuente con licencia
declarada. Así se cubre lo que taro marcaba: que la obra sea libre no hace
libre la secuencia de otro.

**Los efectos**, los 96 del reemplazo (casi todos CC0), más los que haga
taro.

**Lo fabricado**, por ahora: fondos de pelea, enemigos, imágenes de
`ShowPicture`, el System. Hay precedente en el repo: el juego chico de
`rm2k-snes/screens/tests/game/` tiene un System y una FaceSet "hechos por
fórmula", y el de `rm2k-snes/images/` PNG con degradés y ruido.

### Cómo se escribe

**Como volcado exacto de Ditto, a mano o generado, y sin el editor.** Se
probó escribiendo un juego desde cero —un generador descartable de unas 120
líneas—:

* **El conversor lee el volcado exacto**, no sólo el resuelto: Ditto lee las
  dos vistas a los mismos tipos (`Dump::open`), y `rm2k-snes-convert` acepta
  como juego un directorio que es un volcado (`dump_dir` en `game.rs`). **No
  hace falta ningún `.lmu`.** `ditto pack` lo vuelve binario —en el
  experimento, 2.622 bytes en tres archivos— para abrirlo en el editor o
  correrlo en el RPG_RT; `pack` sólo acepta la vista exacta.
* **Lo que se escribe es poco.** El exacto omite todo lo que vale su
  default y escribe los enums por nombre: un NPC con dos renglones de
  mensaje y un `ControlSwitches` son 12 líneas. Los casos de
  `pruebas/casos/` ya tienen esa forma —una lista de `event_commands`—, así
  que lo que hay escrito se reusa tal cual.
* **Los tiles no se escriben a mano.** `.tiles` es una fila de ids por
  línea, y los ids de RM2k (5000 + n para los fijos de abajo, 10000 + n
  arriba, autotiles en 4000-4999) no se leen. Lo práctico es dibujar el
  mapa en ASCII con una leyenda y generar el `.tiles`; en el experimento,
  un mapa de 20x15 son 15 renglones de ASCII y 3 entradas de leyenda.
* **El cartucho armó en 0,4 s**, y arranca: el héroe aparece, camina, y
  el NPC y el cofre se dibujan con los CharSets del reemplazo. Un mapa de
  20x15 da 13 tiles únicos y 3 paletas de sprites.

**El editor de RM2k, si se quiere**, encaja como herramienta de dibujo y no
como fuente: se abre lo que da `ditto pack`, se dibuja el mapa, y `ditto
unpack` lo vuelve al volcado exacto que se versiona. La vuelta es exacta
byte por byte, que es lo que hace a Ditto confiable para esto. No lo probé
con el editor.

**Los siete supuestos de ABL que aparecieron** —cada uno, una tarea chica
en Rust—:

1. `rm2k-snes-cartridges` exige **exactamente un mapa nuevo**, el de debug,
   en `patches/manual/nuevos/`, aunque `[debug] debug_map` sea `false`
   (`cartridges.rs`, en `load`).
2. Exige **un cartucho que se llame `release`** con `cases = "all"`: el
   nombre del cartucho de ABL es parte de la interfaz.
3. **Un juego de un solo mapa no arma**: el de arranque va aparte y
   `--maps` sale vacío.
4. El conversor **lee las quince secciones de la base** y corta si falta
   una; Ditto no las pide.
5. **System y FaceSet se buscan sólo en el juego**, no en el RTP: en el
   experimento hubo que copiarlos al juego.
6. **`fallback_backdrop` tiene que ser un fondo que el juego use**, también
   en un juego sin peleas.
7. **La ventana**: el límite de 15 colores de arriba. Para seguir, el
   experimento usó un System de ABL en el scratch, que no se versionó.

Y uno que no es supuesto: falta el estado 1, el de muerte, que el editor
crea siempre. Un juego escrito a mano tiene que partir de una base mínima
como la de un proyecto nuevo del editor.

Lo que **no** se miró: la estadística de colisión del conversor dio 100%
de celdas abiertas aunque el mapa tenía paredes. Puede ser la elección de
ids del experimento; no lo seguí.

### Cómo convive con lo que hay

* **Los juegos chicos de los crates** (`tests/game/` de `events`,
  `screens`, `battle`, `images` y `patches`) se quedan como están: prueban
  una etapa sola, sin ROM, en milisegundos, y la mitad compara contra los
  hashes de lo que daba el Python. El juego de pruebas es la capa de
  arriba: el cartucho entero en un emulador.
* **Los casos** se quedan como mecanismo: el cartucho mete las páginas de
  prueba y el arnés elige una. El juego de pruebas tiene su propio
  directorio de casos; los de ABL se quedan con ABL y se achican a los que
  usan sus pruebas.
* **Las goldens nacen de nuevo**, y ésa es la parte cara: una golden nueva
  defiende lo que la ROM dibujaba el día que se sacó, bien o mal. Cada
  prueba que se muda tiene que mirarse una vez.


## 4. Dónde vive

    tools/test-game/
      rm2k-snes.toml    sus cartuchos: uno general y los que pidan flags
                        propios, como hoy `test-special`
      data/             el volcado exacto
      maps/             los mapas en ASCII y su leyenda, si se generan
      ChipSet/, CharSet/, System/, Music/, Sound/, …
                        los assets, copiados con su AUTHORS
      cases/            los casos
      tests/            las pruebas, en pytest
      golden/           sus goldens
      build/            no se versiona

En inglés, como todo lo de `tools/`, y sin nombrar a ABL, que es lo que
taro pidió para las pruebas. **Con sus assets adentro** y no detrás de un
flag: son pocos —los que se usen del reemplazo más lo fabricado—, y así el
juego es reproducible sin nada de la máquina salvo el SoundFont, que llega
por flag como hoy a las pruebas de audio (`SOUNDFONT`).

**El arnés**: en la fase 2 se parte, y lo genérico va a `tools/` como un
paquete de Python. Medido sobre las 9.411 líneas de `rom/pruebas/arnes/`:

* **de ABL, unas 1.960**: `recorrido`, los `tramo_*`, `piedras`, `video`,
  `msu` y `lugares`;
* **del bytecode, 1.621**: `events` y `event_opcodes`, que son de Cotorra;
* **genérico, unas 5.830**: `consola` —salvo la firma `ABLS`, que sale del
  archivo de proyecto, y las opciones del título—, `tanda`, `cartuchos`,
  `dibujo`, `menu`, `pantallas`, `batalla` —salvo el droide y el grupo de la
  intro—, los modelos (`modelo`, `experience`, `scene`, `animation`,
  `rm2k`, `lcf`, `render_map`), los clientes de las etapas y `lz2`. Buena
  parte ya está en inglés.

Sigue en Python: moverlo es barato y reescribirlo en Rust no, y
`tools/emulator/` —el core de libretro desde Python— ya está en `tools/`.
ABL lo importa desde la instalación, como `common` y `emulator` en la
fase 1.

**En `tools/justfile`**: una receta propia —`test-game`, que arma sus
cartuchos y corre sus pruebas—, y **no adentro de `test`**. `test` hoy son
las pruebas de Python de `tools/tests/`, que no corren ninguna ROM; las del
juego necesitan un core de libretro y el SoundFont, como las de audio, que
también van aparte.


## 5. Cuánto cuesta, por fase

**Fase 1, ABL afuera.** Es mecánica y se verifica: en el repo nuevo, `just
cartuchos` da las ROMs byte por byte iguales y `just pruebas` los 999 en
verde.

* el repo de ABL con `filter-repo` y las rutas históricas, y `git rm` de
  lo mismo acá;
* `common` y `emulator` instalables, y el `PYTHONPATH` de ABL desde un
  ejecutable;
* `abl-entregar` a ABL;
* `docs/` y `workflow/` según la tabla que ya existe;
* un `AGENTS.md` para cada repo.

**Fase 2, el juego mínimo.** Los siete supuestos de la sección 3 —cada uno
un cambio chico en `cartridge`, `convert` o `screens`, con su prueba—, un
juego de tres o cuatro mapas, el arnés partido, y **diez archivos de M1**
mudados para probar el camino: `test_variables`, `test_condicional`,
`test_etiquetas`, `test_saltos`, `test_puerta_misma`, `test_velocidad`,
`test_tecla`, `test_terreno`, `test_accion_propia` y `test_camara`, que usan
el 4, el 5 o ningún mapa en particular. Mientras tanto la versión de ABL sigue corriendo: se
borra cuando taro haya mirado las goldens nuevas.

**Fase 3, el resto de M1.** 34 archivos, unos 290 casos; casi todo es
escribir casos contra los mapas del juego de pruebas. Lo que pide más que
un mapa —un mapa con muchas paralelas, encuentros, un `InputNumber`, una
posada, efectos en una ruta— se agrega al juego a medida. La medición
contra el RPG_RT (`test_teletransporte_contra_rm2k`) se puede volver a
hacer sobre el juego empacado con `ditto pack`.

**Fase 4, M2.** 36 archivos, 278 casos, y es la que pide assets: peleas
—enemigos y fondos fabricados, las tres animaciones del reemplazo—,
música —los MIDIs del reemplazo; uno con batería y uno con acordes—,
imágenes chicas y de pantalla entera, un título, el menú con ítems y
equipo, y las pistas de MSU-1, que salen del MIDI con el SoundFont.

**Fase 5, M3 en los dos.** Los 20 archivos de M3 se escriben para correr
también contra el juego de pruebas; en ABL siguen, porque sobre un juego
grande son los que encuentran algo.

**Lo que gana ABL**, medido sacando de la tanda los 80 archivos de M1 y M2:

    casos     999 → 394
    CPU-s     643 → 351   (−45%)
    reloj    86,5 → 73 s  (−16%)

El reloj casi no baja porque lo mandan las pruebas largas, que se quedan:
`test_horneados` tiene un caso de 25 s, `test_carga_descomprimida` uno de
14 y `test_recorrido_capitulo_golden` uno de 13. Lo que sí baja es lo que
hay que mantener: **unos 206 casos, unas 360 goldens**, y **dos de sus tres
cartuchos**: `test-special` y `test-encounter-every-step` llevan sólo casos
de pruebas del motor, así que ABL arma sólo `release`. Cuánto tarda menos
`just cartuchos` sin ellos no lo medí.


## 6. La recomendación

**Factible, en este orden:**

1. **Fase 1, ya**, apenas termine Cotorra: con las pruebas sin opcodes, el
   arnés que se lleva ABL no tiene bytecode adentro.
2. **Fase 2 enseguida**, porque el riesgo de la fase 1 es el motor sin
   pruebas propias, y la fase 2 lo corta. Su primera tarea son los siete
   supuestos: sin ellos no arma ningún juego que no sea ABL, y eso es el
   PLUS.
3. **Fases 3 a 5 por familias**, mudando y no duplicando, y con la versión
   de ABL viva hasta que taro mire las goldens nuevas.

**Las tareas que salen**, a `workflow/tasks/todo/`:

* *ABL a su repo*: la fase 1 entera, con la lista de rutas históricas y la
  comprobación de arriba.
* *Lo que ABL toma de tools como Python*: `common` y `emulator`
  instalables, y el `PYTHONPATH` desde un ejecutable.
* *Las herramientas sin supuestos de ABL*: los siete de la sección 3.
* *El juego de pruebas*: el directorio, el generador de mapas desde ASCII,
  la base mínima, los assets del reemplazo con su `AUTHORS`, el System
  dibujado y la receta `test-game`.
* *El arnés en tools*: partirlo, sin el bytecode.
* *Las pruebas del motor al juego de pruebas*, una por fase (2 a 5).
* *Música libre*: piezas de dominio público de Mutopia, con el MIDI generado
  desde su LilyPond; y pedirle a taro los sitios de assets que tiene
  guardados y los efectos que pueda hacer.


## Cómo se midió

Todo con scripts descartables, que no quedan en el repo; lo que hacen está
acá para poder rehacerlo.

* **La tanda y sus tiempos**: `just pruebas --junitxml=<archivo>`. Cada
  `<testcase>` trae su `classname` —`pruebas.rpgmaker.test_x`— y su
  `time`; sumados por archivo y por carpeta dan las tablas. 999 en 86,5 s.
* **Lo que queda en ABL**: la misma receta con un `--ignore=` por cada
  archivo de M1 y M2. 394 en 73 s.
* **Qué usa cada prueba**: los literales de cada archivo que son nombres de
  caso de `pruebas/casos/`, los `Teleport`, `ChangePartyMembers`,
  `EnemyEncounter` y `PlayBGM` de esos casos, y los `ir_al_mapa(N`. La
  clase de cada archivo es criterio, leyendo su docstring.
* **Las goldens**: cada PNG de `golden/tanda/` atribuido al caso más largo
  que sea prefijo de su nombre.
* **La historia**: `git log --format=@%H --name-only --no-renames`, y cada
  commit clasificado por si toca rutas que fueron de ABL —las de la sección
  2—, rutas de las herramientas, o sólo `docs/`, `workflow/` y la raíz.
* **Los archivos de `tools/` que nombran a ABL**: `grep -rlI -i -E
  "talan|lashe|a blurred line|\bABL\b" tools --exclude-dir=target`.
* **El juego sintético**: un generador que escribe el volcado exacto —
  `ditto.json` con `"view": "exact"`, `maps.json`, las quince secciones de
  `db/`, dos mapas y sus `.tiles` desde ASCII— y un `rm2k-snes.toml` mínimo;
  `ditto pack` sobre el volcado, y `rm2k-snes-cartridges --project <juego>
  --game-dir <juego>/data --rtp-dir <el reemplazo de EasyRPG> --soundfont
  <FluidR3_GM.sf2> --without-tracks release`. La captura, con
  `tools/emulator/retro.py`.
* **Las licencias**: `AUTHORS.md` y `COPYING` del reemplazo de EasyRPG;
  `Readme.txt` del RTP de Don Miguel; `pacman -Qi soundfont-fluid`;
  `resources/ttyp0/LICENSE` y el README de easyrpg-player; la página de
  licencias de Mutopia y la de su pieza 1.
