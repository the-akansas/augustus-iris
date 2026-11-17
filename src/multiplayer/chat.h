#ifndef MP_CHAT_H
#define MP_CHAT_H
int mp_client_role(void);
int mp_client_command(const char *verb, const char *text);
int mp_client_speed(int speed);
int mp_client_request_pending(void);
int mp_client_request_outcome(void);
const char *mp_client_request_status(void);
void mp_chat_poll(void);
void mp_chat_reload(void);
int mp_chat_generation(void);
int mp_chat_count(void);
int mp_chat_record(int index);
int mp_chat_is_inbox(int id);
void mp_debug_toggle(void);
int mp_debug_visible(void);
int mp_debug_hint_visible(void);
const char *mp_chat_toast(int index);
int mp_chat_toast_color(int index);
int mp_chat_color(int id);
void mp_chat_draw_chip(int x, int y, int w, int h, int color);
int mp_chat_duration(void);
int mp_chat_duration_cycle(void);
void mp_chat_preferences_reload(void);
#endif
