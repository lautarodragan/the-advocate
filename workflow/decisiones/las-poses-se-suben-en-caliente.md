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
la OAM que ya cuenta con ella. Cómo, en `vram_encolar`
(`tools/runtime/load_graphics.s`) y su cola en `tools/runtime/low_ram.s`.
