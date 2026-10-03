---
name: "La tabla de páginas de prueba se llenó"
description: "El número de página de prueba era un byte y release ya tenía 256: un caso más no ensamblaba. Ahora entran 2048 páginas por mapa, contando las del mapa"
type: bug
assignee: taro
---

Lo encontró Tacuarita el 2026-10-01 (`testing/mundo-5-tangle-forest.md`):
la tabla de páginas de prueba de `release` está llena, porque el número de
página es un byte y ya hay 256. Un caso más rompe el ensamblado con `Range
error`. Mientras tanto, ningún mapa nuevo puede sumar casos propios.

## Qué era

Lo único que no entraba era el `+2` del registro de página, "its page
number", que `rm2k-snes-mapdata` (`record.rs`, `page_table`) escribía entero
con `.byte`. **La consola no lo lee**: `read_page` salta de `+0` a `+3`, y
ninguna otra lectura de `[page_ptr], y` cae en `+2` —buscado en todo
`tools/runtime/`—. Todo lo demás ya era de 16 bits:

* el valor contra el que la página k compara la variable del caso es el
  `.word` de `+26`, con signo: hasta 32767;
* `M_PAGE_COUNT` es un escalar de 16 bits del registro del mapa, y
  `pages_left` es de 2 bytes;
* el arnés escribe la variable del caso en dos bytes (`_elegir_el_caso`);
* el recorrido usa `page_ofs` de 16 bits, y `pick_by_ev` guarda ese offset
  por evento, con `$FFFD`–`$FFFF` como centinelas.

## Qué se hizo

Lo más barato: `+2` lleva **sólo el byte bajo** del número, con el porqué
al lado. Ensancharlo costaba un byte por página —el registro ya ocupa los 32—
para un número que nadie lee, y cambiar el runtime. Las ROMs salen **byte
por byte iguales** (ninguna página de hoy pasa de 255), y la tabla no crece.

**El límite nuevo es `MAX_PAGES`**, en `record.rs`: 2048 páginas en la tabla
de un mapa —65536 / 32, por el `page_ofs` de 16 bits—, y es el de las
páginas de prueba, que van todas en un evento del mapa que las lleva, sumadas
a las de ese mapa. `check_counts` se niega con un mensaje si un mapa lo pasa,
en vez de dejar que el offset dé la vuelta callado. El comentario de
`CASE_VARIABLE` en `tools/port/events.py` apunta ahí.

## Lo medido

* **El rojo, de punta a punta**: con dos casos de más en `pruebas/casos/`
  (copias de `contador`), `just build release` con el `mapdata` viejo da
  `Range error (256 not in [0..255])` y `(257 …)` en `mapdata.inc`. Con el
  nuevo arma, y una prueba descartable corrió los dos casos —páginas 255 y
  256— contra las goldens `contador-110` y `contador-190`: iguales. Los
  casos y la prueba se borraron después.
* **La prueba que queda**: `more_than_256_test_pages_fit_in_the_page_table`,
  en `record.rs`: arma la tabla de un evento de prueba con 300 páginas y
  mira que cada literal de cada `.byte` y `.word` entre en su directiva, que
  es lo que mira `ca65`. Sin el arreglo da rojo con `256 does not fit in:
  .byte 256  ; +2  its page number`. Y
  `a_map_with_more_pages_than_the_console_walks_is_refused`, que 2048 entran
  y 2049 no. Corren con `cargo test -p rm2k-snes-mapdata`, **no con `just
  pruebas`**; de punta a punta lo va a cubrir `release` en cuanto pase de 256
  casos, que es lo próximo que suma Zorro o Puma.
* `NO_CACHE=1 just cartuchos` antes y después: los 1287 archivos de
  `rom/build/` iguales, `abl.sfc` en `6809f47d59671284…`. Las goldens no se
  movieron, y el espacio tampoco.

## Al mergear

Instalar `mapdata` en el global: `just -f tools/justfile install mapdata`.
Nada de Python renombrado.
