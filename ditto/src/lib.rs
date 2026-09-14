//! Ditto: lee los archivos de RPG Maker 2000 y los vuelca a JSON, y al revés.
//!
//! El criterio que hace útil a esto es que la vuelta sea **byte por byte**:
//! sólo así se puede abrir el juego con el RPG Maker de verdad, guardarlo, y
//! seguir teniendo el mismo repositorio. Ver `README.md`.

pub mod archivo;
pub mod crudos;
pub mod esquema;
pub mod lcf;
