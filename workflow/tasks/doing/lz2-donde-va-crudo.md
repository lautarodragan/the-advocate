---
name: "LZ2 donde va crudo"
description: "Comprimir con LZ2 lo que hoy va crudo y se sube al cargar: la tabla de bloques, el bytecode, los battlers, las animaciones de las cinemáticas, la fuente y los fondos de batalla livianos; unos 470 KB en el juego entero, sin perder nada"
type: feature
assignee: Quirquincho
---

Fase 1 del plan de `docs/research/2026-10-01-el-juego-entero-sin-msu-1.md`
(Tucu-tucu), medido por Lechuza en
`docs/research/2026-10-01-los-mapas-por-el-msu-1.md`, sección 5. De taro,
el 2026-10-01, después de pasar a 8 MB
(`decisiones/el-cartucho-pasa-a-8-mb.md`). Las poses y las secuencias de
música no se pueden: se leen mientras se usan, y por qué está en el estudio.

## Cómo va (Quirquincho, 2026-10-01)

Base: `cd3dce0d`, `abl.sfc` en `ccdf1191…`. Cada paso, con `NO_CACHE=1 just
cartuchos`, `just pruebas` y `just -f tools/justfile test`; el tiempo de
carga con el método de `_cargar` en `test_carga_descomprimida.py` —los
cuadros de hardware de la vuelta del lazo que cargó— sobre los 97 mapas de
`release`, y la pelea con `SCN_FRAMES` en el caso `pelea-en-52`.

### 1. La tabla de bloques y su pasabilidad: hecho

Se pueden: la CPU las lee sólo por `blocks_ptr`, `blocks8_ptr` y `pass_ptr`,
punteros de 24 bits que `enter_map` arma desde el registro. Viven ahora en
la WRAM **detrás de la grilla**, en un tercer flujo de LZ2 pegado a los dos
de la grilla (`map_ram` en `materials.rs`): `lz2_grid` lo descomprime donde
terminó el segundo, y por eso vuelven solas con `back_from_battle`. El
registro trae las direcciones de la WRAM, que calcula el conversor; la ROM
no las calcula, y `test_carga_descomprimida.py` mira que coincidan y que el
contenido sea el de `crudos/N.map_ram.bin`, al cargar cada mapa y a la vuelta
de la pelea del 52.

* En `release`: 119,2 KB crudos, 61,7 KB en LZ2 (el reporte del conversor).
  `just espacio`: de 62 bancos de datos a 61, y los huecos de 7.406 B a 0.
* Carga: +39 cuadros sobre los 97 mapas, +0,4 de media, mediana 0, máximo
  +2. La pelea no cambia.
* Ninguna golden se movió; las dos tandas en verde.
* Los hashes de `tests/python.rs` de `rm2k-snes-mapdata` cambiaron a
  propósito: son los bytes del cartucho.
