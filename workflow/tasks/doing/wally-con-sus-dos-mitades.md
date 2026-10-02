---
name: "Wally con sus dos mitades adentro"
description: "map-background y map-sprites dejan de ser crates: pasan a ser módulos de Wally, con una prueba que cuide que el fondo no use los sprites ni al revés; mapdata pasa a usar la biblioteca de Wally"
type: refactor
assignee: Chiflón
---

De taro, el 2026-10-02: "map-background podría pasar a ser parte de wally y
ya, no?" y, para las dos, "dale". Mara los separó en tres crates para que
Cargo cuidara que el fondo no sabe de los objetos y al revés
(`testing/rust-el-dominio-de-los-mapas.md`, "Un crate o varios"); esa
frontera pasa a cuidarla una prueba.
