#include "graphics.h"

#include "graphics/renderer.h"
#include "graphics/screen.h"

static void set_translation(int x, int y)
{
    if (x != 0 || y != 0) {
        graphics_renderer()->set_viewport(x, y, screen_width() - x, screen_height() - y);
    } else {
        graphics_renderer()->reset_viewport();
    }
}

void graphics_in_dialog(void)
{
    graphics_in_dialog_with_size(640, 480);
}

void graphics_in_dialog_with_size(int width, int height)
{
    set_translation((screen_width() - width) / 2, (screen_height() - height) / 2);
    screen_set_dialog_offset(width, height);
}

void graphics_reset_dialog(void)
{
    graphics_renderer()->reset_viewport();
}

/* An optional outer clip (a scrolling panel): inner clips are intersected with it and a reset
 * returns to it, so widgets that clip themselves (labels, panels) cannot draw outside. */
static struct { int active, x, y, width, height; } outer_clip;

void graphics_set_clip_rectangle(int x, int y, int width, int height)
{
    if (outer_clip.active) {
        int x2 = x + width, y2 = y + height;
        int ox2 = outer_clip.x + outer_clip.width, oy2 = outer_clip.y + outer_clip.height;
        if (x < outer_clip.x) x = outer_clip.x;
        if (y < outer_clip.y) y = outer_clip.y;
        if (x2 > ox2) x2 = ox2;
        if (y2 > oy2) y2 = oy2;
        width = x2 > x ? x2 - x : 0;
        height = y2 > y ? y2 - y : 0;
        if (!width || !height) { x = -10; y = -10; width = 1; height = 1; } /* nothing visible */
    }
    graphics_renderer()->set_clip_rectangle(x, y, width, height);
}

void graphics_reset_clip_rectangle(void)
{
    if (outer_clip.active) {
        graphics_renderer()->set_clip_rectangle(outer_clip.x, outer_clip.y, outer_clip.width, outer_clip.height);
    } else {
        graphics_renderer()->reset_clip_rectangle();
    }
}

void graphics_push_outer_clip(int x, int y, int width, int height)
{
    outer_clip.active = 0;
    graphics_set_clip_rectangle(x, y, width, height);
    outer_clip.x = x; outer_clip.y = y; outer_clip.width = width; outer_clip.height = height; outer_clip.active = 1;
}

void graphics_pop_outer_clip(void)
{
    outer_clip.active = 0;
    graphics_renderer()->reset_clip_rectangle();
}

void graphics_clear_screen(void)
{
    graphics_renderer()->clear_screen();
}

void graphics_draw_line(int x_start, int x_end, int y_start, int y_end, color_t color)
{
    graphics_renderer()->draw_line(x_start, x_end, y_start, y_end, color);
}

void graphics_draw_rect(int x, int y, int width, int height, color_t color)
{
    graphics_renderer()->draw_rect(x, width, y, height, color);
}

void graphics_draw_inset_rect(int x, int y, int width, int height, color_t color_dark, color_t color_light)
{
    int x_end = x + width - 1;
    int y_end = y + height - 1;
    graphics_renderer()->draw_line(x, x_end, y, y, color_dark);
    graphics_renderer()->draw_line(x_end, x_end, y, y_end, color_light);
    graphics_renderer()->draw_line(x, x_end, y_end, y_end, color_light);
    graphics_renderer()->draw_line(x, x, y, y_end, color_dark);
}

void graphics_fill_rect(int x, int y, int width, int height, color_t color)
{
    graphics_renderer()->fill_rect(x, width, y, height, color);
}

void graphics_shade_rect(int x, int y, int width, int height, int darkness)
{
    color_t alpha = (0x11 * darkness) << COLOR_BITSHIFT_ALPHA;
    graphics_renderer()->fill_rect(x, width, y, height, alpha);
}

void graphics_light_up_rect(int x, int y, int width, int height, int lightness)
{
    color_t color = ((0x11 * lightness) << COLOR_BITSHIFT_ALPHA) | 0xFFFFFF;
    graphics_renderer()->fill_rect(x, width, y, height, color);
}

void graphics_tint_rect(int x, int y, int width, int height, color_t rgb, int alpha_level)
{
    color_t tinted = (alpha_level << COLOR_BITSHIFT_ALPHA) | (rgb & 0xFFFFFF);
    graphics_renderer()->fill_rect(x, width, y, height, tinted);
}

int graphics_save_to_image(int image_id, int x, int y, int width, int height)
{
    return graphics_renderer()->save_image_from_screen(image_id, x, y, width, height);
}

void graphics_draw_from_image(int image_id, int x, int y)
{
    graphics_renderer()->draw_image_to_screen(image_id, x, y);
}
