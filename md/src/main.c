/* ---------------------------------------------------------------------------
 * Renderiza un mapa de A Blurred Line en el VDP de la Mega Drive y deja mover
 * la cámara con la cruceta.
 *
 * El personaje se mueve como en RM2k: la posición "real" es el tile destino,
 * que se fija apenas arranca el paso, y un contador de 256 unidades por tile
 * dice cuánto falta para llegar. El sprite se dibuja interpolado entre el tile
 * anterior y el destino. La cámara lo sigue, centrada y con clamp.
 *
 * Sin colisión: se puede caminar sobre cualquier cosa, sólo se frena en el
 * borde del mapa.
 *
 * El plano A mide 64x64 celdas de 8x8 y se repite cada 512 píxeles, así que un
 * mapa más grande no entra de una. Lo que se hace es tenerlo poblado sólo
 * alrededor de la cámara —41 columnas por 31 filas, una más que lo visible en
 * cada eje por el scroll sub-celda— y redibujar la columna o la fila que va
 * entrando a medida que la cámara se mueve. El plano se comporta como un
 * anillo: la celda del mapa (x, y) siempre cae en la posición (x mod 64,
 * y mod 64), y el registro de scroll se encarga del resto.
 *
 * El modo de video se elige según la consola: V30 (240 renglones) sólo funciona
 * a 50 Hz, así que en NTSC se usan los 224 de siempre y se ve un poco menos.
 * --------------------------------------------------------------------------- */
#include "mapdata.h"

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef signed short   s16;

#define VDP_DATA_W   (*(volatile u16 *)0xC00000)
#define VDP_DATA_L   (*(volatile u32 *)0xC00000)
#define VDP_CTRL_W   (*(volatile u16 *)0xC00004)
#define VDP_CTRL_L   (*(volatile u32 *)0xC00004)

/* Bit 6 del registro de versión: 1 = consola PAL de 50 Hz. */
#define VERSION_REG  (*(volatile u8 *)0xA10001)
#define PAD1_DATA    (*(volatile u8 *)0xA10003)
#define PAD1_CTRL    (*(volatile u8 *)0xA10009)

/* --- mapa de la VRAM ------------------------------------------------------
 * Con los planos de 64x64 celdas cada uno ocupa 8 KB. Los tiles van abajo de
 * todo: hay lugar para 1024, que a 32 bytes son los primeros 32 KB.
 */
#define TILESET_ADDR 0x0020     /* el tile 0 se deja en blanco */
#define PLANE_A      0x8000
#define PLANE_B      0xA000
#define PLANE_W      0xD000
#define SPRITE_TAB   0xF000
#define HSCROLL_TAB  0xFC00

#define PLANE_CELLS_W 64
#define PLANE_CELLS_H 64

/* Una columna y una fila más de lo que se ve, porque la cámara se mueve de a
 * píxeles y casi siempre hay media celda asomando de cada lado. En NTSC se ven
 * dos filas menos y sobran, que no molesta. */
#define VIEW_W       41
#define VIEW_H       31

#define SCREEN_W     320
#define WORLD_W      (MAP_CELLS_W * 8)
#define WORLD_H      (MAP_CELLS_H * 8)

/* --- el personaje, con el modelo de RM2k ----------------------------------
 * remaining_step va de 256 a 0 y baja 1 << (1 + velocidad) por cuadro. A la
 * velocidad 4, la normal, son 32 por cuadro: ocho cuadros por tile, o sea 2 px
 * por cuadro. La animación avanza cada 6 cuadros, que es lo que EasyRPG saca
 * de las tablas de RPG_RT para esa velocidad.
 */
#define TILE_UNITS   256
#define MOVE_SPEED   4
#define MOVE_STEP    (1 << (1 + MOVE_SPEED))
#define ANIM_PERIOD  6

/* El sprite mide 24x32 y se para en una celda de 16x16: va centrado a lo ancho
 * y apoyado por los pies. */
#define SPRITE_OFFSET_X (-((SPRITE_CELLS_W * 8 - 16) / 2))
#define SPRITE_OFFSET_Y (-(SPRITE_CELLS_H * 8 - 16))

/* Los tiles del personaje van en la VRAM justo después de los del mapa. */
#define SPRITE_TILE_BASE (1 + MAP_TILE_COUNT)

/* Las filas del CharSet de RM2k, en ese orden. */
#define FACE_UP    0
#define FACE_RIGHT 1
#define FACE_DOWN  2
#define FACE_LEFT  3

#define BTN_UP    0x01
#define BTN_DOWN  0x02
#define BTN_LEFT  0x04
#define BTN_RIGHT 0x08

#define VRAM_WRITE  0x40000000u
#define CRAM_WRITE  0xC0000000u
#define VSRAM_WRITE 0x40000010u

static void vdp_reg(u8 reg, u8 value)
{
    VDP_CTRL_W = (u16)(0x8000 | (reg << 8) | value);
}

/* El VDP direcciona con un patrón de bits repartido en dos palabras. */
static void vdp_addr(u32 kind, u16 addr)
{
    VDP_CTRL_L = kind | ((u32)(addr & 0x3FFF) << 16) | ((addr >> 14) & 3);
}

static void vdp_init(void)
{
    vdp_reg(0,  0x04);   /* modo 1: MODE5, sin interrupción de línea        */
    vdp_reg(1,  0x04);   /* modo 2: display OFF hasta terminar de cargar    */
    vdp_reg(2,  PLANE_A >> 10);
    vdp_reg(3,  PLANE_W >> 10);
    vdp_reg(4,  PLANE_B >> 13);
    vdp_reg(5,  SPRITE_TAB >> 9);
    vdp_reg(6,  0x00);
    vdp_reg(7,  0x00);   /* color de fondo: paleta 0, índice 0              */
    vdp_reg(10, 0xFF);   /* contador de HINT, sin uso                       */
    vdp_reg(11, 0x00);   /* scroll de pantalla completa, sin trucos         */
    vdp_reg(12, 0x81);   /* modo 4: H40 (320 px), sin entrelazado           */
    vdp_reg(13, HSCROLL_TAB >> 10);
    vdp_reg(15, 0x02);   /* autoincremento de 2 bytes por escritura         */
    vdp_reg(16, 0x11);   /* tamaño de los planos: 64x64 celdas              */
    vdp_reg(17, 0x00);
    vdp_reg(18, 0x00);
}

static void vram_clear(void)
{
    u16 i;
    vdp_addr(VRAM_WRITE, 0x0000);
    for (i = 0; i < 0x8000; i++)
        VDP_DATA_W = 0x0000;
}

/* El índice 0 de cada paleta es transparente y ningún tile lo usa: el conversor
 * pone magenta ahí, que es el color de fondo y a la vez un canario. Si se ve
 * magenta dentro de la pantalla, algún tile está usando el índice 0. */
static void load_palette(void)
{
    u16 i;
    vdp_addr(CRAM_WRITE, 0x0000);
    for (i = 0; i < 64; i++)
        VDP_DATA_W = md_palette[i];
}

static void load_tiles(void)
{
    u16 i;
    vdp_addr(VRAM_WRITE, TILESET_ADDR);
    for (i = 0; i < MAP_TILE_COUNT * 8; i++)
        VDP_DATA_L = md_tiles[i];

    /* Las 12 poses del personaje, una atrás de la otra. */
    vdp_addr(VRAM_WRITE, (u16)(TILESET_ADDR + MAP_TILE_COUNT * 32));
    for (i = 0; i < SPRITE_POSES * SPRITE_POSE_TILES * 8; i++)
        VDP_DATA_L = md_sprite_tiles[i];
}

/* Una sola entrada en la tabla de sprites: 3x4 celdas, sin enlace a otra.
 * El VDP suma 128 a las coordenadas, así que un sprite en 0,0 va en 128,128. */
static void set_sprite(s16 x, s16 y, u16 tile)
{
    vdp_addr(VRAM_WRITE, SPRITE_TAB);
    VDP_DATA_W = (u16)(y + 128);
    VDP_DATA_W = (u16)(((SPRITE_CELLS_W - 1) << 10) | ((SPRITE_CELLS_H - 1) << 8));
    VDP_DATA_W = (u16)((SPRITE_PALETTE << 13) | tile);
    VDP_DATA_W = (u16)(x + 128);
}

/* --- el plano como ventana móvil sobre el mapa -----------------------------
 * top_x, top_y son las coordenadas, en celdas del mapa, de la esquina de
 * arriba a la izquierda de lo que está poblado en el plano.
 */
static s16 top_x;
static s16 top_y;

static u16 cell_at(s16 x, s16 y)
{
    if (x < 0 || y < 0 || x >= MAP_CELLS_W || y >= MAP_CELLS_H)
        return 0;               /* fuera del mapa: celda en blanco */
    return md_tilemap[(u32)y * MAP_CELLS_W + (u32)x];
}

static u16 plane_addr(u16 col, u16 row)
{
    return (u16)(PLANE_A + row * (PLANE_CELLS_W * 2) + col * 2);
}

/* Las dos escriben una tira de celdas y la parten en dos cuando se pasa del
 * borde del plano, que es donde el anillo da la vuelta. */

static void draw_column(s16 map_x, s16 map_y)
{
    u16 col = (u16)map_x & (PLANE_CELLS_W - 1);
    u16 row = (u16)map_y & (PLANE_CELLS_H - 1);
    s16 left = VIEW_H;
    s16 y = map_y;
    s16 run, i;

    /* Con el autoincremento en una fila entera del plano, una columna se
     * escribe de corrido en vez de reposicionar el VDP en cada celda. */
    vdp_reg(15, PLANE_CELLS_W * 2);
    while (left > 0) {
        run = (s16)(PLANE_CELLS_H - row);
        if (run > left)
            run = left;
        vdp_addr(VRAM_WRITE, plane_addr(col, row));
        for (i = 0; i < run; i++)
            VDP_DATA_W = cell_at(map_x, (s16)(y + i));
        left -= run;
        y += run;
        row = 0;
    }
    vdp_reg(15, 2);
}

static void draw_row(s16 map_y, s16 map_x)
{
    u16 col = (u16)map_x & (PLANE_CELLS_W - 1);
    u16 row = (u16)map_y & (PLANE_CELLS_H - 1);
    s16 left = VIEW_W;
    s16 x = map_x;
    s16 run, i;

    while (left > 0) {
        run = (s16)(PLANE_CELLS_W - col);
        if (run > left)
            run = left;
        vdp_addr(VRAM_WRITE, plane_addr(col, row));
        for (i = 0; i < run; i++)
            VDP_DATA_W = cell_at((s16)(x + i), map_y);
        left -= run;
        x += run;
        col = 0;
    }
}

static void fill_plane(s16 x, s16 y)
{
    s16 i;
    top_x = x;
    top_y = y;
    for (i = 0; i < VIEW_W; i++)
        draw_column((s16)(x + i), y);
}

/* Mueve la ventana hasta donde la quiere la cámara, redibujando sólo lo que
 * entra. Normalmente es una columna, una fila, o ninguna. */
static void stream_to(s16 want_x, s16 want_y)
{
    while (top_x < want_x) {
        draw_column((s16)(top_x + VIEW_W), top_y);
        top_x++;
    }
    while (top_x > want_x) {
        top_x--;
        draw_column(top_x, top_y);
    }
    while (top_y < want_y) {
        draw_row((s16)(top_y + VIEW_H), top_x);
        top_y++;
    }
    while (top_y > want_y) {
        top_y--;
        draw_row(top_y, top_x);
    }
}

static u8 read_pad(void)
{
    u8 value;

    /* Con TH en alto el puerto devuelve C, B, derecha, izquierda, abajo y
     * arriba, activos en bajo. Los nops le dan tiempo al pad a responder. */
    PAD1_DATA = 0x40;
    __asm__ volatile ("nop\n\tnop\n\tnop\n\tnop");
    value = PAD1_DATA;
    return (u8)(~value & 0x3F);
}

static void wait_vblank(void)
{
    while (VDP_CTRL_W & 0x0008)     /* si ya estamos adentro, salir primero */
        ;
    while (!(VDP_CTRL_W & 0x0008))  /* y ahora esperar el siguiente         */
        ;
}

static s16 clamp(s16 value, s16 high)
{
    if (value < 0)
        return 0;
    if (value > high)
        return high;
    return value;
}

static void set_scroll(s16 x, s16 y)
{
    /* El scroll horizontal va al revés que la cámara: correr la ventana a la
     * derecha es correr el plano a la izquierda. El vertical no. */
    vdp_addr(VRAM_WRITE, HSCROLL_TAB);
    VDP_DATA_W = (u16)(-x);
    VDP_DATA_W = (u16)(-x);
    vdp_addr(VSRAM_WRITE, 0x0000);
    VDP_DATA_W = (u16)y;
    VDP_DATA_W = (u16)y;
}

/* Los deltas de cada dirección, en el orden de las filas del CharSet. */
static const s16 dir_dx[4] = {  0, 1, 0, -1 };
static const s16 dir_dy[4] = { -1, 0, 1,  0 };

int main(void)
{
    /* En PAL entran 240 renglones; en NTSC, 224. */
    u8 pal = (VERSION_REG & 0x40) != 0;
    s16 screen_h = pal ? 240 : 224;
    s16 max_cam_x = WORLD_W - SCREEN_W;
    s16 max_cam_y = (s16)(WORLD_H - screen_h);

    /* El tile destino: se fija apenas arranca el paso, como en RM2k. */
    s16 hero_tx = MAP_TILES_W / 2;
    s16 hero_ty = MAP_TILES_H / 2;
    s16 hero_step = 0;              /* lo que falta para llegar, 256 a 0 */
    u8 facing = FACE_DOWN;
    u8 anim_frame = 1;              /* la del medio es la pose parada */
    u8 anim_count = 0;
    u8 walking = 0;

    s16 hero_x, hero_y, cam_x, cam_y;
    u8 pad, column;

    vdp_init();
    vram_clear();
    load_palette();
    load_tiles();
    PAD1_CTRL = 0x40;    /* TH como salida, el resto entradas */

    hero_x = (s16)(hero_tx * 16);
    hero_y = (s16)(hero_ty * 16);
    cam_x = clamp((s16)(hero_x + 8 - SCREEN_W / 2), max_cam_x);
    cam_y = clamp((s16)(hero_y + 8 - screen_h / 2), max_cam_y);
    fill_plane((s16)(cam_x >> 3), (s16)(cam_y >> 3));
    set_scroll(cam_x, cam_y);

    /* Recién ahora se prende el display, así no se ve la VRAM sin inicializar
     * mientras se carga. 0x4C = V30 (240 renglones), 0x44 = V28 (224). */
    vdp_reg(1, pal ? 0x4C : 0x44);

    for (;;) {
        /* --- dónde está el personaje ----------------------------------- */
        hero_x = (s16)(hero_tx * 16 - dir_dx[facing] * (hero_step >> 4));
        hero_y = (s16)(hero_ty * 16 - dir_dy[facing] * (hero_step >> 4));

        cam_x = clamp((s16)(hero_x + 8 - SCREEN_W / 2), max_cam_x);
        cam_y = clamp((s16)(hero_y + 8 - screen_h / 2), max_cam_y);

        /* La caminata son cuatro fases sobre tres columnas: 0, 1, 2, 1. */
        column = (u8)(anim_frame == 3 ? 1 : anim_frame);

        wait_vblank();
        /* Primero se pone al día el plano y después se mueve el scroll, así no
         * llega a verse una columna que todavía no se dibujó. */
        stream_to((s16)(cam_x >> 3), (s16)(cam_y >> 3));
        set_scroll(cam_x, cam_y);
        set_sprite((s16)(hero_x + SPRITE_OFFSET_X - cam_x),
                   (s16)(hero_y + SPRITE_OFFSET_Y - cam_y),
                   (u16)(SPRITE_TILE_BASE
                         + (facing * 3 + column) * SPRITE_POSE_TILES));

        /* --- y para dónde va ------------------------------------------- */
        if (hero_step <= 0) {
            s16 dx = 0, dy = 0;

            /* Como en RM2k, una dirección por vez: nada de diagonales. */
            pad = read_pad();
            if (pad & BTN_LEFT) {
                facing = FACE_LEFT;  dx = -1;
            } else if (pad & BTN_RIGHT) {
                facing = FACE_RIGHT; dx = 1;
            } else if (pad & BTN_UP) {
                facing = FACE_UP;    dy = -1;
            } else if (pad & BTN_DOWN) {
                facing = FACE_DOWN;  dy = 1;
            }

            walking = (u8)(dx || dy);
            if (walking) {
                s16 nx = (s16)(hero_tx + dx);
                s16 ny = (s16)(hero_ty + dy);
                /* Sin colisión: lo único que frena es el borde del mapa. */
                if (nx >= 0 && ny >= 0 && nx < MAP_TILES_W && ny < MAP_TILES_H) {
                    hero_tx = nx;
                    hero_ty = ny;
                    hero_step = TILE_UNITS;
                }
            } else {
                anim_frame = 1;     /* quieto: la pose del medio */
                anim_count = 0;
            }
        }

        if (hero_step > 0) {
            hero_step -= MOVE_STEP;
            if (hero_step < 0)
                hero_step = 0;
        }

        /* La animación depende de si se está caminando, no de si se avanza:
         * contra un borde el personaje sigue moviendo las piernas, como en
         * RM2k. */
        if (walking && ++anim_count >= ANIM_PERIOD) {
            anim_count = 0;
            anim_frame = (u8)((anim_frame + 1) & 3);
        }
    }
}
