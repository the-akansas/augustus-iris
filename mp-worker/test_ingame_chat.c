#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "SDL.h"
#include "multiplayer/chat.h"
#include "multiplayer/clock.h"
#include "city/message.h"
#include "scenario/custom_messages.h"
#include "game/file.h"
#include "graphics/window.h"
#include "core/encoding.h"
static void show(window_id id){window_type w={0};w.id=id;window_show(&w);}
void test_ingame_chat(const char *dir){
 char path[2048];_putenv_s("AUGUSTUS_MP_BRIDGE",dir);
 snprintf(path,sizeof(path),"%s/chat-events.txt",dir);FILE *f=fopen(path,"wb");assert(f);
 for(int i=1;i<=3000;i++)fprintf(f,"mpchat:test:%d\tAurelia\t함렡 쀍 @P @G123 ABC 123 .,! #%d\n",i,i);
 fclose(f);mp_chat_reload();int before=city_message_count();
 show(WINDOW_MESSAGE_DIALOG);mp_chat_poll();assert(city_message_count()==before);
 show(WINDOW_CITY);for(int i=0;i<100;i++)mp_chat_poll();
 assert(mp_chat_count()==3000);assert(city_message_count()==before+1);assert(window_is(WINDOW_CITY));
 int id=custom_messages_get_id_by_uid((uint8_t*)"mpchat:test:1");assert(id);
 char utf8[2048];encoding_to_utf8(custom_messages_get_text(custom_messages_get(id)),utf8,sizeof(utf8),0);
 assert(strstr(utf8,"@P @G123 ABC 123 .,! #1"));assert(strstr(utf8,"함렡"));
 int hub=custom_messages_get_id_by_uid((uint8_t*)"mpchat-inbox");assert(mp_chat_is_inbox(hub));
 assert(strstr(mp_chat_toast(2),"Aurelia : "));
 mp_chat_reload();for(int i=0;i<100;i++)mp_chat_poll();assert(city_message_count()==before+1);assert(mp_chat_count()==3000);
 snprintf(path,sizeof(path),"%s/chat-inbox.sav",dir);assert(game_file_write_saved_game(path));
 assert(game_file_load_saved_game(path)==FILE_LOAD_SUCCESS);
 show(WINDOW_CITY);mp_chat_reload();for(int i=0;i<100;i++)mp_chat_poll();assert(city_message_count()==before+1);assert(mp_chat_count()==3000);
 id=custom_messages_get_id_by_uid((uint8_t*)"mpchat:test:3000");assert(id);
 encoding_to_utf8(custom_messages_get_text(custom_messages_get(id)),utf8,sizeof(utf8),0);assert(strstr(utf8,"#3000"));
 /* Upgrade old per-message inbox entries without destroying archive or other events. */
 city_message_post(-1,MESSAGE_CUSTOM_MESSAGE,id,0);assert(city_message_count()==before+2);
 city_message_pin_chat(hub,1);assert(city_message_count()==before+1);assert(mp_chat_count()==3000);
 snprintf(path,sizeof(path),"%s/command.txt",dir);remove(path);
 snprintf(path,sizeof(path),"%s/role.txt",dir);f=fopen(path,"wb");fputs("2",f);fclose(f);assert(!mp_client_speed(60));
 f=fopen(path,"wb");fputs("1",f);fclose(f);assert(mp_client_speed(200));assert(!mp_client_speed(60));
 snprintf(path,sizeof(path),"%s/command.txt",dir);f=fopen(path,"rb");assert(f);char cmd[64]={0};fread(cmd,1,63,f);fclose(f);assert(!strcmp(cmd,"speed100\n"));remove(path);
 _putenv_s("AUGUSTUS_MP_BRIDGE","");
 puts("PASS native archive: 3000 chats in one inbox entry, Unicode, literal @, sender toast, dedup, SAV round-trip, legacy consolidation, host-only speed");
}
