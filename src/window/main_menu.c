#include "main_menu.h"
#include "multiplayer_lobby.h"
#include "core/encoding.h"
#include "multiplayer/chat.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>
#endif

#include "assets/assets.h"
#include "core/calc.h"
#include "core/config.h"
#include "core/string.h"
#include "editor/editor.h"
#include "game/campaign.h"
#include "game/game.h"
#include "game/system.h"
#include "graphics/generic_button.h"
#include "graphics/graphics.h"
#include "graphics/image.h"
#include "graphics/image_button.h"
#include "graphics/lang_text.h"
#include "graphics/panel.h"
#include "graphics/text.h"
#include "graphics/screen.h"
#include "graphics/weather.h"
#include "graphics/window.h"
#include "sound/music.h"
#include "window/cck_selection.h"
#include "window/config.h"
#include "window/editor/map.h"
#include "window/file_dialog.h"
#include "window/language_select.h"
#include "core/mp_language.h"
#include "window/plain_message_dialog.h"
#include "window/popup_dialog.h"
#include "window/select_campaign.h"
#include "window/video.h"

#define MAX_BUTTONS 8
static char menu_notice[256];

static void button_click(const generic_button *button);

static struct {
    unsigned int focus_button_id;
    int logo_image_id;
} data;

static generic_button buttons[] = {
    {192, 130, 256, 25, button_click, 0, 1},
    {192, 164, 256, 25, button_click, 0, 2},
    {192, 198, 256, 25, button_click, 0, 3},
    {192, 232, 256, 25, button_click, 0, 4},
    {192, 266, 256, 25, button_click, 0, 7},
    {192, 300, 256, 25, button_click, 0, 8},
    {192, 334, 256, 25, button_click, 0, 5},
    {192, 368, 256, 25, button_click, 0, 6},
};

/* Fixed sibling executables only; no shell or user-supplied command. */
static int launch_menu_companion(int creator)
{
#ifdef _WIN32
    wchar_t path[4096], command[8192];
    DWORD length = GetModuleFileNameW(NULL, path, 4096);
    if (!length || length >= 4000) return 0;
    wchar_t *end = wcsrchr(path, L'\\');
    if (!end) return 0;
    wcscpy(end + 1, creator ? L"Augustus-Scenario-Creator.exe" : L"Augustus.exe");
    swprintf(command, 8192, creator ? L"\"%ls\"" : L"\"%ls\" --multiplayer", path);
    STARTUPINFOW startup = {0}; PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    if (!CreateProcessW(path, command, NULL, NULL, FALSE, 0, NULL, NULL, &startup, &process)) return 0;
    CloseHandle(process.hThread); CloseHandle(process.hProcess); return 1;
#else
    return 0;
#endif
}


static void draw_version_string(void)
{
    uint8_t version_string[100] = "Augustus v";
    int version_prefix_length = string_length(version_string);
    int text_y = screen_height() - 54;

    string_copy(string_from_ascii(system_version()), version_string + version_prefix_length, 99);

    int text_width = text_get_width(version_string, FONT_NORMAL_GREEN);
    int width = calc_value_in_step(text_width + 20, 16);

    inner_panel_draw(20, text_y, width / 16, 2);
    text_draw_centered(version_string, 20, text_y + 11, width, FONT_NORMAL_GREEN, 0);
}

static void draw_background(void)
{
    graphics_reset_dialog();
    graphics_reset_clip_rectangle();
    image_draw_fullscreen_background(image_group(GROUP_INTERMEZZO_BACKGROUND));

    if (!window_is(WINDOW_FILE_DIALOG)) {
        graphics_in_dialog();
        outer_panel_draw(162, 32, 20, 25);
        if (!data.logo_image_id) {
            data.logo_image_id = assets_get_image_id("UI", "Main Menu Banner");
        }
        image_draw(data.logo_image_id, 176, 50, COLOR_MASK_NONE, SCALE_NONE);
        graphics_reset_dialog();
        draw_version_string();
    }
}

static void draw_foreground(void)
{
    graphics_in_dialog();

    for (unsigned int i = 0; i < MAX_BUTTONS; i++) {
        large_label_draw_custom_size(buttons[i].x, buttons[i].y, buttons[i].width, buttons[i].height);
        if (data.focus_button_id == i + 1) {
            graphics_shade_rect(buttons[i].x, buttons[i].y, buttons[i].width, buttons[i].height, 2);
            // if buttons are replaced with complex_button structures, the shading should be drawn there
        }
    }

    for (int i = 0; i < MAX_BUTTONS; ++i) {
        const generic_button *b = &buttons[i];
        int type = b->parameter1;
        if (type == 1) lang_text_draw_centered(CUSTOM_TRANSLATION, TR_MAIN_MENU_SELECT_CAMPAIGN, b->x, b->y+7, b->width, FONT_NORMAL_GREEN);
        else if (type == 2 || type == 3 || type == 5 || type == 6) {
            int group = type == 5 ? 2 : 30;
            int text = type == 2 ? 2 : type == 3 ? 3 : type == 5 ? 0 : 5;
            lang_text_draw_centered(group, text, b->x, b->y+7, b->width, FONT_NORMAL_GREEN);
        } else {
            uint8_t label[128];
            encoding_from_utf8(type == 4 ? "지도 편집기" : type == 7 ? "멀티플레이" : "멀티 시나리오 제작기", label, sizeof(label));
            text_draw_centered(label,b->x,b->y+7,b->width,FONT_NORMAL_GREEN,0);
        }
    }
    char status[512] = {0}; const char *bridge = getenv("AUGUSTUS_MP_BRIDGE");
    if (bridge) {
        char path[2048]; snprintf(path,sizeof(path),"%s/menu-status.txt",bridge);
        FILE *f=fopen(path,"rb"); if(f){fread(status,1,sizeof(status)-1,f);fclose(f);}
    }
    if (menu_notice[0] || status[0]) {
        uint8_t text[1024]; encoding_from_utf8(menu_notice[0]?menu_notice:status,text,sizeof(text));
        text_draw_ellipsized(text,176,406,288,FONT_SMALL_PLAIN,0);
    }

    graphics_reset_dialog();
}

static void handle_input(const mouse *m, const hotkeys *h)
{
    const mouse *m_dialog = mouse_in_dialog(m);
    if (generic_buttons_handle_mouse(m_dialog, 0, 0, buttons, MAX_BUTTONS, &data.focus_button_id)) {
        return;
    }
    if (h->close_pressed) {
        hotkey_handle_escape();
    }
    if (h->load_file) {
        window_file_dialog_show(FILE_TYPE_SAVED_GAME, FILE_DIALOG_LOAD);
    }
}

static void confirm_exit(int accepted, int checked)
{
    if (accepted) {
        system_exit();
    }
}

static void button_click(const generic_button *button)
{
    int type = button->parameter1;

    if (type == 1) {
        window_select_campaign_show();
    } else if (type == 2) {
        window_file_dialog_show(FILE_TYPE_SAVED_GAME, FILE_DIALOG_LOAD);
    } else if (type == 3) {
        window_cck_selection_show();
    } else if (type == 4) {
        if (!editor_is_present() || !game_init_editor()) {
            window_plain_message_dialog_show(
                TR_NO_EDITOR_TITLE, TR_NO_EDITOR_MESSAGE, 1);
        } else {
            if (config_get(CONFIG_UI_SHOW_INTRO_VIDEO)) window_video_show("map_intro.smk", window_editor_map_show);
            sound_music_play_editor();
        }
    } else if (type == 5) {
        window_config_show(CONFIG_FIRST_PAGE, 0, 1);
    } else if (type == 6) {
        window_popup_dialog_show(POPUP_DIALOG_QUIT, confirm_exit, 1);
    } else if (type == 7) {
        if (getenv("AUGUSTUS_MP_BRIDGE")) window_multiplayer_lobby_show();
        else if (launch_menu_companion(0)) system_exit();
        else strcpy(menu_notice,"Augustus.exe 실행 파일을 확인해 주세요.");
    } else if (type == 8) {
        int opened = getenv("AUGUSTUS_MP_BRIDGE") ? mp_client_command("open-creator", "") : launch_menu_companion(1);
        strcpy(menu_notice,opened?"":"제작기를 열지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }
}

static void open_startup_lobby(void)
{
    if (getenv("AUGUSTUS_MP_OPEN_LOBBY") && getenv("AUGUSTUS_MP_BRIDGE")) window_multiplayer_lobby_show();
}

static void language_chosen(void)
{
    window_main_menu_show(0);
    open_startup_lobby();
}

void window_main_menu_show(int restart_music)
{
    window_multiplayer_leave_to_menu();
    window_multiplayer_reset();
    menu_notice[0] = 0;
    if (restart_music) {
        sound_music_play_intro();
    }
    weather_reset();
    game_campaign_clear();
    window_type window = {
        WINDOW_MAIN_MENU,
        draw_background,
        draw_foreground,
        handle_input
    };
    window_show(&window);
    static int startup_done;
    if (!startup_done) {
        startup_done = 1;
        /* Multilingual build: the first start asks for the display language once (saved in augustus.ini). */
        if (encoding_get() == ENCODING_KOREAN && mp_language_chosen() < 0 && mp_language_available_count() > 1) {
            window_language_select_show(language_chosen);
            return;
        }
        open_startup_lobby();
    }
}
