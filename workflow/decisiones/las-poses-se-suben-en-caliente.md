# Qué

**En VRAM vive una pose por personaje.** Las doce poses de cada personaje que
cambia de pose viven en el cartucho, y la que toca se sube por DMA en el
vblank, como hace FF5. Los quietos siguen compartiendo ranura por (CharSet,
índice, pose), porque no cambian.

# Por qué

Las poses de RM2k son de 24x32 y el objeto más chico que las cubre es de 32x32:
un personaje son 192 tiles de objeto, y la PPU direcciona 512 —los dos bancos
de nombres, un tope del hardware y no un reparto—. Con todas las poses
residentes entran dos personajes y medio, y la escena de apertura —Core, Manta,
el droide y Kersh caminando en el mismo mapa— pedía 768.

La otra salida era armar cada personaje con doce objetos de 8x8 para compartir
tiles, y eso revienta los 128 lugares de OAM en cualquier mapa con gente. taro
eligió la subida en caliente.

Lo que cuesta: un DMA por pose que cambia, con un tope por vblank —lo que sobra
espera al siguiente—, y la cola tiene que subir la pose en el mismo vblank que
la OAM que ya cuenta con ella. Cómo, en `vram_queue`
(`tools/runtime/load_graphics.s`) y su cola en `tools/runtime/low_ram.s`.

# Y los quietos lejanos se turnan una ranura

De taro, el 2026-10-01, para que entre Distant Paradise (108): en un mapa que
no entra en ningún reparto de VRAM, y sólo ahí, los quietos que ninguna
cámara muestra juntos comparten una ranura aunque muestren poses distintas, y
la pose se sube cuando el que la necesita entra en pantalla, por la misma cola.
Sólo los que nadie mueve y muestran un solo gráfico. Era la opción A de Puma
en `workflow/tasks/*/mundo-7-camino-a-paradise.md`; la B —todos los quietos
de un personaje mirando para el mismo lado— cambiaba lo que se ve. Cómo, en
`tools/runtime/shared_poses.s` y en `workflow/tasks/*/el-108-con-poses-compartidas.md`.

# Y si ni así entra, nadie tiene ranura

De taro, el 2026-10-03, para la granja de ABL (127), que no entra ni con los
turnos —"vamos con la 1", la opción D de Puma—: en un mapa así, y sólo ahí,
las ranuras son una caché. El que entra en pantalla pide una, camine o no; la
pose sube por la misma cola; y la ranura que nadie dibujó en dos cuadros la
toma el siguiente. Los quietos que muestran la misma pose comparten la suya.
Si la caché se llena, el que pide **espera sin dibujarse** hasta que alguien
salga de la pantalla: no se cuelga, y el que espera es el último que
`build_oam` alcanza. Cómo, en `tools/runtime/cache_slots.s`; lo medido y lo
que se descartó —los espejos, el margen en celdas—, en
`workflow/tasks/*/la-cache-de-ranuras.md`.
