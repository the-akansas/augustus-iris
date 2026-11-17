#ifndef WINDOW_MULTIPLAYER_LOBBY_H
#define WINDOW_MULTIPLAYER_LOBBY_H
#include "input/mouse.h"
#include "input/hotkey.h"
void window_multiplayer_lobby_show(void);
void window_city_visit_set_spectator(int on);   /* window/city_visit.inc: the spectator screen opened the visit */
/* A spectator of the game hall (Korean edition; 0 and no-ops elsewhere): the empire map is its screen. */
int window_multiplayer_spectating(void);
int window_multiplayer_spectate_tick(void);      /* the empire map, every frame: 1 when spectating ended and the hall took over */
void window_multiplayer_spectate_banner(int x,int y,int width);
void window_multiplayer_spectate_leave_map(void); /* from the empire map to the spectator screen */
void window_multiplayer_save_options_show(void);
void window_multiplayer_room_poll(void);
int window_multiplayer_enter_city(void);
void window_multiplayer_chat_draw(void);
void window_multiplayer_chat_begin(void);
int window_multiplayer_chat_input_top(void);
int window_multiplayer_trade_alert_top(void);
int window_multiplayer_chat_input(const mouse *m,const hotkeys *h);
/* The throne box, card, dialog or scoreboard is under (x,y) (or a dialog is open): the city shows no tooltip.
 * A hook, not a call: the engine worker builds window/city.c without the multiplayer screens (set by them when drawn). */
extern int (*window_multiplayer_overlay_hook)(int x,int y);
void window_multiplayer_history_show(void);
void window_multiplayer_reset(void);
void window_multiplayer_leave_to_menu(void);
void window_multiplayer_trade_show(void);
void window_multiplayer_trade_show_for_post(unsigned id);
void window_multiplayer_trade_show_for_city(int name_id);
void window_multiplayer_cash_show(int name_id);
void window_multiplayer_army_show(int name_id);
/* Trade status panel over the empire map (the city shows it as a side tab). */
int window_multiplayer_side_trade_open(void);
void window_multiplayer_side_trade_toggle(void);
void window_multiplayer_side_trade_draw(int x,int y,int max_height);
int window_multiplayer_side_trade_input(const mouse *m,int x,int y,int max_height);

#endif

void window_multiplayer_transport_show(void);
