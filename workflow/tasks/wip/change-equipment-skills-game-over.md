**Implementar `ChangeEquipment` (10450), `ChangeSkills` (10440) y `GameOver` (12420).**

Hoy ninguno compila, así que la página entera que los usa no corre:

- el `Craftsman` de `Sector 27 Workshop` (mapa 30, evento 1): `ChangeEquipment [0, 0, 1, 0, 0]`;
- la cinemática del techo de `Sector 27 Warehouse` (mapa 32, evento `EV0005`, y los
  eventos 23 y 25): `ChangeSkills [1, 14, 0, 0, 133]`, `ChangeEquipment [1, 25, 1, 4, 0]`
  y `GameOver`.

Hecho es: esas páginas compilan y corren, con casos en `pruebas/casos/`.
