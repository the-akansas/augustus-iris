#include "multiplayer_victory.h"
#include "window/video.h"
#include "window/city.h"
#include "multiplayer/clock.h"
#include "core/encoding.h"
#include "graphics/graphics.h"
#include "graphics/window.h"
#include "graphics/video.h"
#include "graphics/panel.h"
#include "graphics/text.h"
#include "graphics/font.h"
#include "graphics/scrollbar.h"
#include "input/input.h"
#include "sound/music.h"
#include "city/message.h"
#include "scenario/custom_messages.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif
static char current[65];
static int showing, waiting;
/* A separate saved inbox item; the live chat archive remains a single entry. */
static void record_completion(const char *dir){
 char path[2048],run[40],uid[64],body[32768];snprintf(path,sizeof(path),"%s/objective-completed.txt",dir);FILE *f=fopen(path,"rb");if(!f)return;
 if(!fgets(run,sizeof(run),f)){fclose(f);return;}run[strcspn(run,"\r\n")]=0;
 if(strlen(run)!=32||strspn(run,"0123456789abcdef")!=32){fclose(f);return;}
 size_t count=fread(body,1,sizeof(body)-1,f);fclose(f);body[count]=0;
 snprintf(uid,sizeof(uid),"mpgoal:%s",run);if(custom_messages_get_id_by_uid((uint8_t*)uid))return;
 custom_message_t *m=custom_messages_create((uint8_t*)uid);if(!m)return;
 /* a 기한 경쟁 result (Augustus/objectives.py race_lines) is a ranking, not a shared success */
 int race=!strncmp(body,"기한 경쟁",strlen("기한 경쟁"));
 m->title=message_media_text_blob_add_encoded(race?"기한 경쟁 결과":"공동 목표 달성");m->subtitle=message_media_text_blob_add_encoded(race?"마감 때의 순위":"모든 도시가 함께 달성한 결과");m->display_text=message_media_text_blob_add_encoded(body);
 city_message_post(-1,MESSAGE_CUSTOM_MESSAGE,m->id,0);
}
static void scrolled(void){window_invalidate();}
static scrollbar_type scroll={548,108,196,468,196,scrolled,0,0,0,0,0,20};
static void draw_background(void){window_draw_underlying_window();}
static void draw_text(const char *s,int y){uint8_t text[2048];encoding_from_utf8(s,text,sizeof(text));text_draw_multiline(text,80,y,480,0,FONT_NORMAL_BLACK,0);}
static void draw_foreground(void){
 graphics_in_dialog();outer_panel_draw(56,48,33,24);
 draw_text("공동 목표를 달성했습니다!",72);
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],line[1024];int y=108;
 if(dir){snprintf(path,sizeof(path),"%s/objective-status.txt",dir);FILE *f=fopen(path,"rb");
  static uint8_t lines[256][2048];int count=0,height=0;
  while(f&&count<256&&fgets(line,sizeof(line),f)){line[strcspn(line,"\r\n")]=0;encoding_from_utf8(line,lines[count],sizeof(lines[count]));height+=text_measure_multiline(lines[count],456,FONT_NORMAL_BLACK,0)*(font_definition_for(FONT_NORMAL_BLACK)->line_height+5)+8;count++;}if(f)fclose(f);
  scrollbar_update_total_elements(&scroll,height);graphics_set_clip_rectangle(80,108,462,196);y=108-(int)scroll.scroll_position;
  for(int i=0;i<count;i++)y+=text_draw_multiline(lines[i],80,y,456,0,FONT_NORMAL_BLACK,0)+8;
  graphics_reset_clip_rectangle();scrollbar_draw(&scroll);
  snprintf(path,sizeof(path),"%s/victory-wait.txt",dir);f=fopen(path,"rb");y=330;
  while(f&&y<400&&fgets(line,sizeof(line),f)){line[strcspn(line,"\r\n")]=0;draw_text(line,y);y+=32;}if(f)fclose(f);
 }
 graphics_reset_dialog();
}
static void handle_input(const mouse *m,const hotkeys *h){scrollbar_handle_mouse(&scroll,mouse_in_dialog(m),1);}
static void finished(void){
 sound_music_resume();
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char tmp[2048],path[2048];
 if(dir){snprintf(tmp,sizeof(tmp),"%s/victory-done.tmp",dir);snprintf(path,sizeof(path),"%s/victory-done.txt",dir);FILE *f=fopen(tmp,"wb");if(f){fprintf(f,"%s\n",current);if(!fclose(f)){
#ifdef _WIN32
 MoveFileExA(tmp,path,MOVEFILE_REPLACE_EXISTING);
#else
 rename(tmp,path);
#endif
 }}}
 waiting=1;scrollbar_init(&scroll,0,0);window_city_show();window_type w={WINDOW_PLAIN_MESSAGE_DIALOG,draw_background,draw_foreground,handle_input};window_show(&w);
}
void window_multiplayer_victory_poll(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],request[65]={0};
 if(mp_clock_active()&&dir){record_completion(dir);snprintf(path,sizeof(path),"%s/victory-request.txt",dir);FILE *f=fopen(path,"rb");if(f){if(fscanf(f,"%64s",request)!=1)request[0]=0;fclose(f);}}
 if(strlen(request)!=64||strspn(request,"0123456789abcdef")!=64)request[0]=0;
 if(!request[0]){if(showing){if(!waiting)video_stop();sound_music_resume();showing=waiting=0;if(mp_clock_active())window_city_show();}return;}
 if(!strcmp(request,current))return;
 if(showing&&!waiting)video_stop();strcpy(current,request);showing=1;waiting=0;
 video_stop();window_city_show();window_video_show("smk/victory_senate.smk",finished);
}
