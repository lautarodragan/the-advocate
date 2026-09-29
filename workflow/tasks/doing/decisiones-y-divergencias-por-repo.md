---
name: "Decisiones y divergencias, por repo"
description: "Clasificar cada archivo de workflow/decisiones/ y workflow/divergencias/ según vaya al repo de las herramientas o al de ABL, para el corte"
type: docs
assignee: Guayabo
---

Pregunta 8 del research de las herramientas, que taro dejó abierta el
2026-09-28 ("algunas son de ABL y otras no: revisarlas una por una"), y que
Hornero decide con la autorización de taro del 2026-09-29.

El criterio: va con las herramientas lo que valdría para cualquier juego de
RM2k portado con ellas; va con ABL lo que es de este juego, sus mapas, sus
eventos o sus decisiones artísticas. Si una mezcla las dos cosas, se dice
cuál parte es cuál.

## Cómo se aplicó

Se clasifica **la regla, no los ejemplos**. Casi todas se tomaron mirando ABL
y citan sus mapas, sus eventos y sus números; eso no las hace de ABL si la
regla vale para cualquier juego. Muchas de las de herramientas están
**justificadas** por cómo es ABL —"ninguna ruta del juego lo ejercita",
"las 26 rutas con diagonales"—: son límites del motor medidos sobre ABL, que
según `decisiones/las-herramientas-se-separan-de-abl.md` se quedan fijos en
el motor. En la tabla dicen "medido sobre ABL", porque son lo primero que
hay que volver a mirar con otro juego.

Las divergencias salen **todas** de las herramientas, y no es casualidad:
una divergencia es la ROM haciendo otra cosa que RM2k, y la ROM es el
runtime y el conversor. Las que "valen porque ABL es como es" —las de
"Cuándo deja de alcanzar"— son justamente las que el repo de las
herramientas tiene que llevarse, porque son las que le avisan al próximo
juego.

La clasificación vive **sólo acá**, sin tocar los archivos: los de
`decisiones/` y `divergencias/` no tienen frontmatter, y agregárselo a
sesenta y cuatro archivos para un dato que se usa una vez ensucia más que
una tabla. Las tablas se leen con un script: cada fila de archivo empieza
con `` | `decisiones/`` o `` | `divergencias/`` o `` | `docs/``, y la
segunda columna es exactamente `herramientas`, `abl` o `mixto`:

    grep -E '^\| `(decisiones|divergencias)/' workflow/tasks/*/decisiones-y-divergencias-por-repo.md \
      | awk -F'|' '{gsub(/[ `]/, "", $2); gsub(/ /, "", $3); print $3, $2}'

Las rutas de las dos primeras tablas son relativas a `workflow/`; las de la
tercera, a la raíz.

## Decisiones

| archivo | repo | porqué |
|---|---|---|
| `decisiones/README.md` | mixto | Cada repo necesita el suyo: se copia a los dos. |
| `decisiones/agotar-el-presupuesto-de-teletransportes-es-un-error.md` | herramientas | Regla del runtime (`entrar_en_panico`), vale para cualquier juego. |
| `decisiones/atravesar-paredes-vale-para-el-salto.md` | herramientas | Semántica de RM2k en el runtime. |
| `decisiones/call-event-se-compila-en-linea.md` | herramientas | Cómo compila el conversor `CallEvent`; "ninguna llamada es recursiva" y `LLAMADA_MAX` están medidos sobre ABL. |
| `decisiones/conditional-branch-cinco-de-doce-clases.md` | herramientas | Qué compila el conversor y cómo; qué clases entran está medido sobre ABL. |
| `decisiones/data-es-la-vista-resuelta.md` | herramientas | Es la convención de Ditto y del lector para cualquier juego: qué emite `ditto unpack` y qué versiona un proyecto. |
| `decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md` | herramientas | `BOOT_CUADROS` es del runtime y el corte es del conversor; el número está medido sobre el mapa de arranque de ABL. |
| `decisiones/el-cartucho-se-queda-en-4-mb.md` | mixto | "LoROM topa en 4 MB y pasar es ExHiROM" es del runtime; que ABL se quede en 4 MB, sus 2,52 MB y "se revisa al 85-90%" son de ABL. Se parte así. |
| `decisiones/el-color-math-no-se-usa.md` | herramientas | Cómo dibuja el runtime los translúcidos; lo de snes9x redondeando vale para cualquier golden. |
| `decisiones/el-cronometro-no-tiene-paleta-propia.md` | herramientas | Reparto de paletas del conversor y `subir_timer_pal` del runtime. |
| `decisiones/el-refresco-corre-en-tres-momentos.md` | herramientas | Estructura del cuadro del runtime, copiada de `Game_Map::Update`. |
| `decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md` | herramientas | Política del presupuesto de audio del conversor y del runtime (`temas_heredados`, `tema_asegurar`). |
| `decisiones/el-trueno-va-entero-y-paga-la-lluvia.md` | mixto | "Los efectos tienen dos voces" y el mecanismo de alias por mapa y de enteros que paga la música son de las herramientas; el trueno del mapa 1 a 8.800 Hz y la lluvia entera son de ABL, y ya viven en `[sound_effects]` de `rom/rm2k-snes.toml`. Se parte así. |
| `decisiones/la-camara-corrida-de-la-reja-es-del-juego.md` | abl | Un evento concreto del juego (el Bum del mapa 8) que el original también hace; no dice nada del motor que no diga ya `camara.s`. |
| `decisiones/la-grilla-vive-en-la-wram.md` | herramientas | Dónde vive la grilla en el runtime; "si Lashe City anda, anda el resto" está medido sobre ABL. |
| `decisiones/la-orden-34-sobre-el-heroe.md` | herramientas | Qué órdenes de ruta hace el runtime; lo ganado está medido sobre ABL. |
| `decisiones/la-pagina-activa-se-congela-hasta-el-refresco.md` | herramientas | Semántica de RM2k en el runtime. |
| `decisiones/la-pagina-de-prueba-se-apaga-sola.md` | herramientas | La página de prueba la inyecta el conversor (`SWITCH_DE_PRUEBA` en `tools/port/eventos.py`) en cualquier juego. |
| `decisiones/la-tecla-de-accion-mira-las-dos-celdas.md` | herramientas | Semántica de RM2k en el runtime. |
| `decisiones/las-diagonales-van-sobre-eventos.md` | herramientas | Límite del conversor y del runtime, medido sobre ABL (ninguna ruta del héroe con diagonales). |
| `decisiones/las-herramientas-se-separan-de-abl.md` | mixto | Cómo se parte el repo: le importa a los dos. Lo del runtime, la versión de la suite, el inglés y "instalar" es de las herramientas; "ABL sólo conoce ejecutables del PATH", declarar la versión y "verificar" son de ABL. Se copia a los dos, o se parte así. |
| `decisiones/las-poses-se-suben-en-caliente.md` | herramientas | Arquitectura del runtime (el tope de 512 tiles de objeto es del hardware). |
| `decisiones/los-eventos-disparan-con-dos-bits.md` | herramientas | Estructura del runtime, copiada de `waiting_execution`. |
| `decisiones/los-lideres-comparten-una-ranura-de-cgram.md` | herramientas | Reparto de CGRAM del conversor. |
| `decisiones/los-lideres-posibles-son-una-aproximacion.md` | herramientas | Cómo simula el conversor `ChangePartyMembers`. |
| `decisiones/los-translucidos-van-horneados.md` | herramientas | Cómo convierte el conversor el "Trans"; vale mientras los translúcidos del juego sean estáticos, que está medido sobre ABL. La excepción del save point es de ABL y ya está en `[graphics] opaque` de `rom/rm2k-snes.toml`. |
| `decisiones/orden-9-de-ruta-hacia-el-heroe.md` | herramientas | Qué órdenes de ruta hace el runtime; las nueve que faltan, medidas sobre ABL. |
| `decisiones/ordenes-de-ruta-26-y-27-sobre-el-heroe.md` | herramientas | Qué órdenes tira el conversor; "el juego se puede jugar sin ellas" está medido sobre ABL. |
| `decisiones/se-dibujan-todos-los-eventos.md` | herramientas | Principio del conversor (el préstamo de paleta en `cabe`), de taro. |
| `decisiones/un-caso-largo-en-cero-no-prueba-nada.md` | mixto | La regla vale para la tanda de cualquier juego; pero las pruebas de ROM se quedan en ABL hasta que exista el juego golden. Se copia a los dos. |
| `decisiones/un-grafico-que-no-entra-no-se-dibuja.md` | herramientas | Reparto de paletas del conversor. **Ya no vale entera**: ver abajo. |
| `decisiones/un-solo-banco-de-muestras.md` | herramientas | Arquitectura de audio del conversor y del runtime. |
| `decisiones/una-puerta-al-mismo-mapa-no-recarga-el-mapa.md` | herramientas | Semántica de RM2k en el runtime. |
| `decisiones/una-puerta-es-una-pagina-de-contacto.md` | herramientas | Cómo compila el conversor un `Teleport`. |

Sin contar el README: **28 de herramientas, 1 de ABL y 4 mixtas.**

## Divergencias

| archivo | repo | porqué |
|---|---|---|
| `divergencias/README.md` | mixto | Cada repo necesita el suyo; el párrafo "salvo las que valen porque ABL es como es" es de las herramientas. |
| `divergencias/atravesar-paredes-vale-mientras-dura-la-ruta.md` | herramientas | Runtime; justificada por ABL (las cuatro páginas que la dejan prendida son descuidos del original). |
| `divergencias/autofire-de-a-con-x.md` | herramientas | Runtime (`read_pad`), en todas las pantallas. |
| `divergencias/cronometro-llegando-a-cero.md` | herramientas | Runtime. **Dudosa**: ver abajo. |
| `divergencias/destello-sobre-la-paleta-de-otro.md` | herramientas | Runtime y reparto de paletas. |
| `divergencias/el-chipset-se-saltea-un-dibujo-cada-18-minutos.md` | herramientas | Runtime. |
| `divergencias/el-cronometro-y-su-vecino-comparten-colores.md` | herramientas | Runtime y reparto de paletas; los mapas son ejemplos. |
| `divergencias/el-mapa-lleva-a-vram-solo-lo-que-dibuja.md` | herramientas | Conversor; "cuándo deja de alcanzar" es para el próximo juego. |
| `divergencias/fase-de-los-tiles-animados.md` | herramientas | Runtime. **Dudosa**: ver abajo. |
| `divergencias/la-animacion-de-batalla-achicada.md` | herramientas | Conversor. |
| `divergencias/la-fase-de-los-quietos-que-animan.md` | herramientas | Runtime. |
| `divergencias/la-partida-no-guarda-los-eventos.md` | herramientas | Runtime. |
| `divergencias/la-ventana-de-mensaje-se-lleva-10-kb-de-vram.md` | herramientas | Runtime; las 39 columnas valen para cualquier juego de RM2k. |
| `divergencias/las-transiciones-del-teletransporte.md` | herramientas | Conversor y runtime; los mapas son ejemplos. |
| `divergencias/llamada-salteada.md` | herramientas | Conversor; el `AfterBattleMint` es un ejemplo. |
| `divergencias/lo-que-el-giro-hacia-el-heroe-no-modela.md` | herramientas | Runtime. |
| `divergencias/lo-que-la-colision-con-los-eventos-no-modela.md` | herramientas | Runtime. |
| `divergencias/lo-que-la-ia-de-los-enemigos-no-modela.md` | herramientas | Conversor y runtime; las tropas son ejemplos. |
| `divergencias/lo-que-la-pantalla-de-end-game-no-modela.md` | herramientas | Runtime. |
| `divergencias/lo-que-la-pantalla-de-game-over-no-modela.md` | herramientas | Runtime; qué imagen nombra el `System` de ABL es un ejemplo. |
| `divergencias/lo-que-las-paginas-de-tropa-no-modelan.md` | herramientas | Runtime. Qué efectos de tropa entran lo decide el juego, y ya está en `[sound_effects] troop_effects_in_package` de `rom/rm2k-snes.toml`. |
| `divergencias/los-comunes-del-equipo-corren-al-cerrar-el-menu.md` | herramientas | La regla (`eventos.COMUNES_DEL_EQUIPO`) vale para cualquier común paralelo de esa forma; en ABL hay uno. |
| `divergencias/los-ocho-cuadros-del-cierre-de-un-mensaje.md` | herramientas | Runtime. |
| `divergencias/los-translucidos-quedan-opacos.md` | herramientas | Conversor; justificada por ABL (ningún translúcido camina). |
| `divergencias/mas-de-cuatro-quietos-que-animan.md` | herramientas | Conversor (`ANIMA_QUIETO_MAX`), medido sobre ABL. |
| `divergencias/move-event-tras-teleport-interno.md` | herramientas | Runtime. **Dudosa**: ver abajo. |
| `divergencias/paso-bloqueado-de-una-ruta-forzada.md` | herramientas | Runtime. |
| `divergencias/siete-paletas-en-un-mapa-con-animaciones.md` | herramientas | Conversor. |
| `divergencias/ticks-de-pantalla-despues-del-interprete.md` | herramientas | Runtime. |
| `divergencias/un-evento-que-camina-no-cambia-de-grafico.md` | herramientas | Runtime y conversor. |
| `divergencias/un-solo-contador-para-las-cuatro-flechas.md` | herramientas | Runtime. |
| `divergencias/una-celda-con-las-dos-animaciones-del-chipset.md` | herramientas | Voodoo; justificada por ABL (cero celdas así). |

Sin contar el README: **31 de herramientas, 0 de ABL y 0 mixtas.**

## docs/

| archivo | repo | porqué |
|---|---|---|
| `docs/README.md` | mixto | Cada repo necesita el suyo, con las carpetas que le toquen. |
| `docs/jetbrains.md` | herramientas | Es para que el annotate atraviese el corte de `main.s`, que está en `tools/runtime/`. |
| `docs/port/` | herramientas | Cómo funcionan el conversor y el runtime; los mapas de ABL son ejemplos. Salvo `pipeline.md`, abajo. |
| `docs/port/pipeline.md` | mixto | El diagrama es de las herramientas; las rutas `rom/…`, `$ABL_GAME_DIR` y las dos recetas de `just` son de ABL. |
| `docs/rpgmaker/chipsets.md` | herramientas | El formato de RM2k. |
| `docs/rpgmaker/rtp.md` | mixto | Qué es el RTP de Don Miguel, por qué no sirve el de EasyRPG y cómo se extrae son de las herramientas; los 5 ChipSets y 17 CharSets que usa ABL son de ABL. |
| `docs/snes/` | herramientas | La consola y los emuladores. |
| `docs/research/graficos-de-rm2k-a-snes.md` | herramientas | Estudio de cómo convertir los gráficos de RM2k, medido sobre ABL; lo citan decisiones y divergencias de las herramientas. |
| `docs/research/el-mapa-de-las-herramientas-de-python.md` | herramientas | El mapa de `tools/` y el plan del corte. |
| `docs/research/inspeccion-integral-del-repo.md` | abl | Foto del repo entero antes del corte, y más de la mitad es sobre las pruebas de ROM y su arnés, que se quedan en ABL. No se parte: es una foto. |

## Las que ya no valen, para taro

No se tocaron: el que decide es taro.

* **`decisiones/un-grafico-que-no-entra-no-se-dibuja.md`** la reemplazó
  `decisiones/se-dibujan-todos-los-eventos.md`. El título y la primera
  frase son del 2026-09-06 (`3bf9a780`, la orden 34); el préstamo de paleta
  es del 2026-09-08 (`ac8f356b`), y desde ese día `cabe`, en
  `tools/port/snes_convert.py`, le presta una paleta ajena también a los
  tiles del chipset y a los gráficos de la orden 34, que entran por la misma
  función: un gráfico sólo se queda sin dibujar si todas las paletas son de
  líder. `la-orden-34-sobre-el-heroe.md` ya lo dice ("un evento dibujado con
  un tile del chipset pasa a colgarse de una paleta ajena"). Lo que sigue
  valiendo es la mitad del medio: a esos gráficos **no se les abre una paleta
  nueva** —forzarlos rompía el 108, el 114 y el 207—. Los comentarios de
  `snes_convert.py` que dicen "el que no entra no se dibuja" —el de los
  gráficos de la orden 34 y el del cronómetro, los dos en
  `npcs_dibujables`— tienen la misma frase vieja.
* **Tres divergencias se midieron contra la referencia en Python, no contra
  RM2k**, y la referencia se borró el 2026-09-16. Nada dice cuál de los dos
  lados se equivocaba, así que no se sabe si la ROM difiere de RM2k:
  * `divergencias/fase-de-los-tiles-animados.md`: lo dice ella misma ("dejó
    de poder investigarse así").
  * `divergencias/cronometro-llegando-a-cero.md`: los 252 pixeles del cuadro
    60 salieron el 2026-09-13 comparando contra la referencia (`27c828de`),
    aunque el archivo no lo aclara.
  * `divergencias/move-event-tras-teleport-interno.md`: "contra la
    referencia en Python, mientras existió"; el título dice "que RM2k".

  Según el README de `divergencias/`, que pide "dónde la ROM no hace lo que
  RM2k hace", ninguna de las tres entra hoy. O se verifican contra el RPG_RT
  con Wine, o se borran.

### Lo que no deja de valer pero está viejo

* **Las rutas de la mudanza.** Varios citan `rom/src/`, que desde la
  mudanza es `tools/runtime/` —cuáles, `grep -l 'rom/src/'
  workflow/decisiones/*.md workflow/divergencias/*.md`—, y los `pruebas/…` de adentro ahora son
  `rom/pruebas/…`. Es un reemplazo mecánico que conviene hacer antes del
  corte, en su propio commit.
* **Nombres que pasaron al archivo de proyecto**: `SIN_TRAMA`
  (`los-translucidos-van-horneados.md`) es `[graphics] opaque`;
  `SE_DEL_MAPA` y `SE_ENTEROS_PAGADOS` (`el-trueno-va-entero-y-paga-la-lluvia.md`)
  son `[sound_effects] per_map` y `paid_by_music`; `SE_DE_TROPA_AL_PAQUETE`
  (`lo-que-las-paginas-de-tropa-no-modelan.md`) es
  `troop_effects_in_package`. Todos en `rom/rm2k-snes.toml`.
* `decisiones/un-caso-largo-en-cero-no-prueba-nada.md` dice "los dos lados
  no hacían nada", de cuando había referencia; la regla vale igual contra
  una golden.
