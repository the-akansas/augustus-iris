#include "set_salary.h"

#include "city/emperor.h"
#include "city/finance.h"
#include "city/ratings.h"
#include "city/victory.h"
#include "core/encoding.h"
#include "game/difficulty.h"
#include "game/settings.h"
#include "core/lang.h"
#include "graphics/color.h"
#include "graphics/font.h"
#include "core/string.h"
#include "core/locale.h"
#include "game/resource.h"
#include "graphics/button.h"
#include "graphics/generic_button.h"
#include "graphics/graphics.h"
#include "graphics/image.h"
#include "graphics/lang_text.h"
#include "graphics/panel.h"
#include "graphics/text.h"
#include "graphics/window.h"
#include "input/input.h"
#include "window/advisors.h"

#include <stdio.h>

#define MIN_DIALOG_WIDTH 384

/* What each salary does to the emperor's favor at the end of the year (city/ratings.c, yearly update; user 2026-11-13):
 * paid above the governor's own rank: -(ranks above + difficulty penalty); at the rank: no change; below it: +1
 * (not at the lowest rank). Measured on the salary actually paid over the year, so a change mid-year counts in part.
 * The governor's own rank is fixed by the scenario; the salary is only what one pays oneself. */
static int rank_label(uint8_t *out,int size){   /* "  (내 계급: 시민)", the game's own rank name, trailing spaces trimmed */
    uint8_t open[48],close[8];encoding_from_utf8("  (내 계급: ",open,sizeof(open));encoding_from_utf8(")",close,sizeof(close));
    const uint8_t *name=lang_get_string(32,city_emperor_rank());int n=0;
    for(int i=0;open[i] && n<size-1;i++)out[n++]=open[i];
    int start=n;for(int i=0;name && name[i] && n<size-1;i++)out[n++]=name[i];
    while(n>start && out[n-1]==' ')n--;
    for(int i=0;close[i] && n<size-1;i++)out[n++]=close[i];
    out[n]=0;return n;
}
static int rank_label_width(void){uint8_t t[128];rank_label(t,sizeof(t));return text_get_width(t,FONT_NORMAL_BLACK);}
/* One salary row in one font: "사무관의 봉급: 2 Dn (연말 지지도 -2)". The salary chosen now has a gold frame. */
static const uint8_t *money_unit(void){return locale_translate_money_dn()?lang_get_string(6,0):string_from_ascii("Dn");}
static int salary_text_width(unsigned int rank){   /* "사무관의 봉급: 2 Dn" in the row font */
    uint8_t number[32];int n=string_from_int(number,city_emperor_salary_for_rank(rank),0);(void)n;
    return lang_text_get_width(52,rank+4,FONT_NORMAL_WHITE)+text_get_width(number,FONT_NORMAL_WHITE)+text_get_width(money_unit(),FONT_NORMAL_WHITE);
}
/* "(연말 지지도 -N)" starts at one x for every row, after the widest salary text (user 2026-11-13: not ragged). */
static int effect_column(void){int widest=0;for(unsigned int r=0;r<11;r++){int w=salary_text_width(r);if(w>widest)widest=w;}return 176+widest+18;}
static void draw_salary_row(unsigned int rank,int y,font_t font,color_t color,int column){
    int x=176;
    x+=lang_text_draw_colored(52,rank+4,x,y,font,color);
    x+=text_draw_number(city_emperor_salary_for_rank(rank),'@',0,x,y,font,color);
    text_draw(money_unit(),x,y,font,color);
    int own=city_emperor_rank();
    if(city_victory_has_won())return;
    /* above the rank: -N; the rank itself: no change; below it: +1. All in the row's own font and colour
       (user 2026-11-13: colours stay as they are). */
    char label[64];uint8_t text[96];
    if((int)rank>own)snprintf(label,sizeof(label),"(연말 지지도 -%d)",(int)rank-own+difficulty_high_salary_punishment());
    else if((int)rank==own)snprintf(label,sizeof(label),"(연말 지지도 변화 없음)");
    else if(own!=0)snprintf(label,sizeof(label),"(연말 지지도 +1)");
    else return;
    encoding_from_utf8(label,text,sizeof(text));text_draw(text,column,y,font,color);
}

static void button_cancel(const generic_button *button);
static void button_set_salary(const generic_button *button);

static generic_button buttons[] = {
    {240, 395, 160, 20, button_cancel},
    {144, 85, 352, 20, button_set_salary, 0, 0},
    {144, 105, 352, 20, button_set_salary, 0, 1},
    {144, 125, 352, 20, button_set_salary, 0, 2},
    {144, 145, 352, 20, button_set_salary, 0, 3},
    {144, 165, 352, 20, button_set_salary, 0, 4},
    {144, 185, 352, 20, button_set_salary, 0, 5},
    {144, 205, 352, 20, button_set_salary, 0, 6},
    {144, 225, 352, 20, button_set_salary, 0, 7},
    {144, 245, 352, 20, button_set_salary, 0, 8},
    {144, 265, 352, 20, button_set_salary, 0, 9},
    {144, 285, 352, 20, button_set_salary, 0, 10},
};

static unsigned int focus_button_id;

static int get_dialog_width(void)
{
    int dialog_width = 16 + lang_text_get_width(52, 15, FONT_LARGE_BLACK) + rank_label_width();
    if (dialog_width < MIN_DIALOG_WIDTH) {
        dialog_width = MIN_DIALOG_WIDTH;
    }
    if (dialog_width % BLOCK_SIZE != 0) {
        // make sure the width is a multiple of 16
        dialog_width += BLOCK_SIZE - dialog_width % BLOCK_SIZE;
    }
    return dialog_width;
}

static void draw_foreground(void)
{
    graphics_in_dialog();

    int dialog_width = get_dialog_width();
    int dialog_x = 128 - (dialog_width - MIN_DIALOG_WIDTH) / 2;
    outer_panel_draw(dialog_x, 32, dialog_width / BLOCK_SIZE, 25);
    image_draw(resource_get_data(RESOURCE_DENARII)->image.icon, dialog_x + 10, 42, COLOR_MASK_NONE, SCALE_NONE);
    int title_width = lang_text_get_width(52, 15, FONT_LARGE_BLACK);
    int title_x = dialog_x + 25 + (dialog_width - 64 - title_width - rank_label_width()) / 2;
    lang_text_draw(52, 15, title_x, 48, FONT_LARGE_BLACK);
    {   /* the governor's own rank beside the title, centered on the title's line */
        uint8_t label[128];rank_label(label,sizeof(label));
        int y = 56;   /* middle of the large title line (checked on screen; the font tables' line heights put it too high) */
        text_draw(label, title_x + title_width, y, FONT_NORMAL_BLACK, 0);
    }

    inner_panel_draw(144, 80, 22, 15);

    int column = effect_column();
    for (unsigned int rank = 0; rank < 11; rank++) {
        int focused = focus_button_id == rank + 2, chosen = (int) rank == city_emperor_salary_rank();
        if (focused) {
            draw_salary_row(rank, 90 + 20 * rank, FONT_NORMAL_RED, 0, column);
        } else if (chosen) {   /* gold frame, same font as the other rows */
            graphics_fill_rect(150, 87 + 20 * rank, 340, 18, 0x50e7c45a);
            graphics_draw_rect(150, 87 + 20 * rank, 340, 18, COLOR_FONT_YELLOW);
            draw_salary_row(rank, 90 + 20 * rank, FONT_NORMAL_WHITE, 0, column);
        } else {
            draw_salary_row(rank, 90 + 20 * rank, FONT_NORMAL_WHITE, 0, column);
        }
    }

    if (!city_victory_has_won()) {
        if (city_emperor_salary_rank() <= city_emperor_rank()) {
            lang_text_draw_multiline(52, 76, 152, 336, 336, FONT_NORMAL_BLACK);
        } else {
            lang_text_draw_multiline(52, 71, 152, 336, 336, FONT_NORMAL_BLACK);
        }
    } else {
        lang_text_draw_multiline(52, 77, 150, 336, 340, FONT_NORMAL_BLACK);
    }
    button_border_draw(240, 395, 160, 20, focus_button_id == 1);
    lang_text_draw_centered(13, 4, 176, 400, 288, FONT_NORMAL_BLACK);

    graphics_reset_dialog();
}

static void handle_input(const mouse *m, const hotkeys *h)
{
    if (generic_buttons_handle_mouse(mouse_in_dialog(m), 0, 0, buttons, 12, &focus_button_id)) {
        return;
    }
    if (input_go_back_requested(m, h)) {
        window_advisors_show();
    }
}

static void button_cancel(const generic_button *button)
{
    window_advisors_show();
}

static void button_set_salary(const generic_button *button)
{
    int rank = button->parameter1;

    if (!city_victory_has_won()) {
        city_emperor_set_salary_rank(rank);
        city_finance_update_salary();
        city_ratings_update_favor_explanation();
        window_advisors_show();
    }
}

void window_set_salary_show(void)
{
    window_type window = {
        WINDOW_SET_SALARY,
        window_advisors_draw_dialog_background,
        draw_foreground,
        handle_input
    };
    window_show(&window);
}
