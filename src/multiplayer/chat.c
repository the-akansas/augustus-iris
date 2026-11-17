#include "chat.h"
#include "clock.h"
#include "core/encoding.h"
#include "core/mp_i18n.h"
#include "core/time.h"
#include "core/file.h"
#include "platform/windows_paths.h"
#ifdef _WIN32
#include <windows.h>
#endif
#include "city/message.h"
#include "scenario/custom_messages.h"
#include "graphics/window.h"
#include "graphics/graphics.h"
#include "route_post.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static long chat_offset;
static int *records, record_count, record_capacity, generation, inbox_id, debug_mode;
static char toast[3][4096];static unsigned int toast_until[3];static int toast_color[3]={-1,-1,-1};
/* Personal presentation only; never part of host rules or a city save. */
static int duration=8, preferences_loaded;   /* default 8 s (user 2026-11-15); a saved choice still wins */
static const int durations[]={3,5,8,15,30,60};
void mp_chat_preferences_reload(void){
 duration=8;preferences_loaded=1;
 const char *path=dir_get_file_at_location("multiplayer-chat.ini",PATH_LOCATION_CONFIG);
 FILE *f=path?file_open(path,"rb"):0;if(!f)return;
 int value;if(fscanf(f,"toast_seconds=%d",&value)==1)
  for(int i=0;i<6;i++)if(value==durations[i])duration=value;
 file_close(f);
}
int mp_chat_duration(void){if(!preferences_loaded)mp_chat_preferences_reload();return duration;}
int mp_chat_duration_cycle(void){
 int old=mp_chat_duration(),next=3;for(int i=0;i<6;i++)if(old==durations[i])next=durations[(i+1)%6];
 char path[FILE_PATH_MAX],tmp[FILE_PATH_MAX];
 snprintf(path,sizeof(path),"%s",dir_append_location("multiplayer-chat.ini",PATH_LOCATION_CONFIG));
 if(snprintf(tmp,sizeof(tmp),"%s.tmp",path)>=(int)sizeof(tmp))return 0;
 FILE *f=file_open(tmp,"wb");if(!f)return 0;
 int ok=fprintf(f,"toast_seconds=%d\n",next)>0;if(!file_close(f))ok=0;
 if(!ok){remove(tmp);return 0;}
#ifdef _WIN32
 if(!augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING)){remove(tmp);return 0;}
#else
 if(rename(tmp,path)){remove(tmp);return 0;}
#endif
 duration=next;return 1;
}
int mp_chat_generation(void){return generation;}
int mp_chat_count(void){return record_count;}
int mp_chat_record(int index){return index>=0 && index<record_count?records[index]:0;}
int mp_chat_is_inbox(int id){
 custom_message_t *m=custom_messages_get(id);
 return m && m->linked_uid && !strcmp((const char*)m->linked_uid->text,"mpchat-inbox");
}
int mp_debug_visible(void){return debug_mode==1;}
int mp_debug_hint_visible(void){return debug_mode==0;}
void mp_debug_toggle(void){if(mp_clock_active())debug_mode=(debug_mode+1)%3;}
const char *mp_chat_toast(int i){return i>=0 && i<3 && (int)(toast_until[i]-time_get_millis())>0?toast[i]:0;}
int mp_chat_toast_color(int i){return i>=0 && i<3?toast_color[i]:-1;}
/* The sender's player colour at sending rides on the archived key ("mpchat:<session>:<id>:c<0-7>", written by the
 * bridge from the server chat record). No suffix (system, no city yet, old record): -1, no mark. */
static int uid_color(const char *uid){
 if(!uid || strncmp(uid,"mpchat:",7))return -1;
 const char *last=strrchr(uid,':');
 if(!last || last-uid<8 || last[1]!='c' || last[2]<'0' || last[2]>'7' || last[3])return -1;
 int colons=0;for(const char *p=uid;p<last;p++)colons+=*p==':';
 return colons==2?last[2]-'0':-1;
}
/* A colour suffix is presentation metadata, not message identity. A restored save
 * and a regenerated bridge journal can carry different suffixes for the same message. */
static int chat_existing_uid(const char *uid){
 int id=custom_messages_get_id_by_uid((const uint8_t*)uid);if(id)return id;
 if(strncmp(uid,"mpchat:",7))return 0;
 size_t n=strlen(uid);if(uid_color(uid)>=0)n-=3;
 char key[4096];if(n+4>sizeof(key))return 0;
 memcpy(key,uid,n);key[n]=0;
 int colons=0;for(size_t i=0;i<n;i++)colons+=key[i]==':';if(colons!=2)return 0;
 id=custom_messages_get_id_by_uid((const uint8_t*)key);if(id)return id;
 for(int color=0;color<8;color++){
  snprintf(key+n,sizeof(key)-n,":c%d",color);
  id=custom_messages_get_id_by_uid((const uint8_t*)key);if(id)return id;
 }
 return 0;
}
int mp_chat_color(int id){
 custom_message_t *m=custom_messages_get(id);
 return m && m->linked_uid?uid_color((const char*)m->linked_uid->text):-1;
}
/* A small player-colour mark next to a sender's name. The dark edge keeps a white or pale colour apart from a
 * light background; on the dark chat panels the colour itself stands out. */
void mp_chat_draw_chip(int x,int y,int w,int h,int color){
 if(color<0 || color>7 || w<3 || h<3)return;
 graphics_fill_rect(x,y,w,h,mp_player_color(color));
 graphics_draw_rect(x,y,w,h,0xff000000);
}
static void add_record(int id){
 if(record_count==record_capacity){int cap=record_capacity?record_capacity*2:256;int *p=realloc(records,cap*sizeof(int));if(!p)return;records=p;record_capacity=cap;}
 records[record_count++]=id;
}
void mp_chat_reload(void){
 chat_offset=0;record_count=0;inbox_id=0;generation++;
 memset(toast_until,0,sizeof(toast_until));
 for(int i=1;i<=custom_messages_count();i++){
  custom_message_t *m=custom_messages_get(i);
  if(m && m->linked_uid && !strncmp((const char*)m->linked_uid->text,"mpchat:",7))add_record(i);
 }
}
int mp_client_role(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
 char path[2048];snprintf(path,sizeof(path),"%s/role.txt",dir);
 FILE *f=fopen(path,"rb");if(!f)return 0;int c=fgetc(f);fclose(f);return c=='1'?1:c=='2'?2:0;
}

/* One command mailbox: publish outcome before removal, and never unlock on a
 * timeout. Losing a reply must not permit a duplicate economic operation. */
static int request_waiting,request_outcome;
static unsigned request_started,request_visible_until;
static char request_label[256],request_status[768];
static const char *request_description(const char *verb,const char *text){
 if(!strncmp(verb,"speed",5))return "속도 변경 요청 중";
 if(strcmp(verb,"trade"))return 0;
 if(!strncmp(text,"accept ",7)||!strncmp(text,"contract_accept ",16))return "거래 수락 처리 중";
 if(!strncmp(text,"route_",6))return "도시 교역 계약 처리 중";
 if(!strncmp(text,"offer ",6)||!strncmp(text,"contract_offer ",15))return "거래 제안 전송 중";
 if(!strncmp(text,"reject ",7)||!strncmp(text,"contract_stop ",14))return "거래 취소 처리 중";
 if(!strncmp(text,"contract_counter ",17))return "수량 수정 제안 처리 중";
 if(!strncmp(text,"contract_resume ",16))return "계약 재개 요청 중";
 return 0;
}
int mp_client_request_pending(void){
 if(!request_waiting)return 0;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 1;
 char path[2048];snprintf(path,sizeof(path),"%s/network-entry.txt",dir);
 FILE*f=fopen(path,"rb");int disconnected=f?fgetc(f)=='1':0;if(f)fclose(f);
 if(disconnected){request_outcome=-1;request_waiting=0;request_visible_until=time_get_millis()+6000;snprintf(request_status,sizeof(request_status),"연결이 종료되었습니다. 재접속 후 요청 결과를 확인하세요.");return 0;}
 snprintf(path,sizeof(path),"%s/command.txt",dir);
 f=fopen(path,"rb");if(f){fclose(f);return 1;}
 snprintf(path,sizeof(path),"%s/command-result.txt",dir);f=fopen(path,"rb");
 if(!f)return 1;
 size_t n=fread(request_status,1,sizeof(request_status)-1,f);fclose(f);request_status[n]=0;
 if(!n)return 1;
 snprintf(path,sizeof(path),"%s/command-outcome.txt",dir);f=fopen(path,"rb");if(!f)return 1;
 int result=0;int valid=fscanf(f,"%d",&result)==1 && (result==1 || result==-1);fclose(f);if(!valid)return 1;
 request_outcome=result;request_waiting=0;request_visible_until=time_get_millis()+6000;return 0;
}
int mp_client_request_outcome(void){return mp_client_request_pending()?0:request_outcome;}
const char *mp_client_request_status(void){
 if(mp_client_request_pending()){
  unsigned seconds=(unsigned)(time_get_millis()-request_started)/1000;
  snprintf(request_status,sizeof(request_status),seconds>=5?"%s · %u초 · 응답 대기, 다시 누르지 않아도 됩니다":"%s · %u초",request_label,seconds);
  return request_status;
 }
 return time_get_millis()<request_visible_until?request_status:0;
}

int mp_client_command(const char *verb,const char *text){
 if(mp_client_request_pending())return 0;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
 char path[2048],tmp[2048];snprintf(path,sizeof(path),"%s/command.txt",dir);snprintf(tmp,sizeof(tmp),"%s/command.tmp",dir);
 FILE *f=fopen(path,"rb");if(f){fclose(f);return 0;}
 const char *description=request_description(verb,text?text:"");
 if(description){char result[2048];snprintf(result,sizeof(result),"%s/command-result.txt",dir);remove(result);snprintf(result,sizeof(result),"%s/command-outcome.txt",dir);remove(result);}
 f=fopen(tmp,"wb");if(!f)return 0;fprintf(f,"%s\n%s",verb,text?text:"");
 if(fclose(f))return 0;if(rename(tmp,path)!=0)return 0;
 if(description){request_outcome=0;request_waiting=1;request_started=time_get_millis();snprintf(request_label,sizeof(request_label),"%s",description);}
 return 1;
}
int mp_client_speed(int speed){
 if(mp_client_role()!=1)return 0;
 if(speed<0)speed=0;if(speed>100)speed=100;
 char verb[32];snprintf(verb,sizeof(verb),"speed%d",speed);return mp_client_command(verb,"");
}
void mp_chat_poll(void){
 /* Native chat viewer retains IDs, never pointers into movable scenario storage. */
 if(!window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY) && !window_is(WINDOW_TOP_MENU) && !window_is(WINDOW_MESSAGE_LIST) && !window_is(WINDOW_MULTIPLAYER_CHAT))return;
 if(!inbox_id){
  inbox_id=custom_messages_get_id_by_uid((uint8_t*)"mpchat-inbox");
  if(!inbox_id){
   custom_message_t *m=custom_messages_create((uint8_t*)"mpchat-inbox");if(!m)return;inbox_id=m->id;
   m->title=message_media_text_blob_add_encoded("멀티플레이 채팅");
   m->subtitle=message_media_text_blob_add_encoded("전체 플레이어 대화 기록");
   m->display_text=message_media_text_blob_add_encoded("채팅 기록을 엽니다.");
  }
  city_message_pin_chat(inbox_id,0);
 }
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],line[4096];snprintf(path,sizeof(path),"%s/chat-events.txt",dir);
 FILE *f=fopen(path,"rb");if(!f)return;fseek(f,chat_offset,SEEK_SET);int added=0;
 for(int count=0;count<32 && fgets(line,sizeof(line),f);count++){
  if(!strchr(line,'\n'))break;
  char *sender=strchr(line,'\t');if(!sender)break;*sender++=0;
  char *body=strchr(sender,'\t');if(!body)break;*body++=0;body[strcspn(body,"\r\n")]=0;
  /* Optional presentation flag: keep countdown history, never replay its toast in a city. */
  char *presentation=strchr(body,'\t');if(presentation)*presentation++=0;
  int show_toast=!presentation || strcmp(presentation,"history-only");
  if(!chat_existing_uid(line)){
   custom_message_t *msg=custom_messages_create((uint8_t*)line);if(!msg)break;
   int id=msg->id;
   /* multilingual: room notices (sender 시스템) are shown in the reader's language, what players type never changes;
    * a player's name is theirs too (a name that happens to be a catalog word stays as it is, 2026-11-14) */
   int player_line=strcmp(sender,"시스템")!=0;if(player_line)mp_i18n_suspend(1);
   msg->title=message_media_text_blob_add_encoded(sender);
   msg->subtitle=message_media_text_blob_add_encoded(sender);
   msg->display_text=message_media_text_blob_add_encoded(body);
   if(player_line)mp_i18n_suspend(0);
   add_record(id);added=1;
   if(show_toast){
   memmove(toast[0],toast[1],sizeof(toast[0])*2);memmove(toast_until,toast_until+1,sizeof(toast_until[0])*2);memmove(toast_color,toast_color+1,sizeof(toast_color[0])*2);
   toast_color[2]=uid_color(line);
   /* The toast is final text (window/multiplayer_chat.c draws it without the catalog): a notice is put in the
    * reader's language here, part by part; a player's line stays as typed (2026-11-14). */
   if(player_line)snprintf(toast[2],sizeof(toast[2]),"%s : %s",sender,body);
   else{char who[256];snprintf(who,sizeof(who),"%s",mp_i18n_translate(sender));snprintf(toast[2],sizeof(toast[2]),"%s : %s",who,mp_i18n_translate(body));}
   toast_until[2]=time_get_millis()+1000*mp_chat_duration();
   }
  }
  chat_offset=ftell(f);
 }
 fclose(f);
 if(added)city_message_pin_chat(inbox_id,!window_is(WINDOW_MULTIPLAYER_CHAT));
}
