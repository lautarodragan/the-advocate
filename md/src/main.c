/* ---------------------------------------------------------------------------
 * Renderiza un mapa de A Blurred Line en el VDP de la Mega Drive y deja mover
 * la cámara con la cruceta.
 *
 * Sólo los tiles: sin sprites y sin personaje. La "cámara" es un par x,y en
 * píxeles que los botones suben y bajan, y que se traduce directo a los
 * registros de scroll del VDP.
 *
 * El mapa entero entra en el plano A, que mide 64x64 celdas de 8x8 (512x512
 * píxeles). Un mapa más grande que eso necesita ir redibujando filas y
 * columnas del plano a medida que se scrollea; el conversor avisa si no entra.
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

#define SCREEN_W     320
#define WORLD_W      (MAP_CELLS_W * 8)
#define WORLD_H      (MAP_CELLS_H * 8)

#define CAMERA_SPEED 2          /* píxeles por cuadro */

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
}

static void load_tilemap(void)
{
    u16 x, y;
    for (y = 0; y < MAP_CELLS_H; y++) {
        vdp_addr(VRAM_WRITE, (u16)(PLANE_A + y * PLANE_CELLS_W * 2));
        for (x = 0; x < MAP_CELLS_W; x++)
            VDP_DATA_W = md_tilemap[y * MAP_CELLS_W + x];
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

int main(void)
{
    /* En PAL entran 240 renglones; en NTSC, 224. */
    u8 pal = (VERSION_REG & 0x40) != 0;
    s16 screen_h = pal ? 240 : 224;
    s16 max_x = WORLD_W - SCREEN_W;
    s16 max_y = (s16)(WORLD_H - screen_h);
    s16 cam_x = 0;
    s16 cam_y = 0;
    u8 pad;

    vdp_init();
    vram_clear();
    load_palette();
    load_tiles();
    load_tilemap();
    set_scroll(cam_x, cam_y);

    PAD1_CTRL = 0x40;    /* TH como salida, el resto entradas */

    /* Recién ahora se prende el display, así no se ve la VRAM sin inicializar
     * mientras se carga. 0x4C = V30 (240 renglones), 0x44 = V28 (224). */
    vdp_reg(1, pal ? 0x4C : 0x44);

    for (;;) {
        wait_vblank();
        set_scroll(cam_x, cam_y);

        pad = read_pad();
        if (pad & BTN_LEFT)
            cam_x -= CAMERA_SPEED;
        if (pad & BTN_RIGHT)
            cam_x += CAMERA_SPEED;
        if (pad & BTN_UP)
            cam_y -= CAMERA_SPEED;
        if (pad & BTN_DOWN)
            cam_y += CAMERA_SPEED;

        cam_x = clamp(cam_x, max_x);
        cam_y = clamp(cam_y, max_y);
    }
}
