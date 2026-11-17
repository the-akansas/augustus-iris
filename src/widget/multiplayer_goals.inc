/* Live cooperative objectives use the existing game panel and never pause the multiplayer clock. */
#include "core/encoding.h"
#include "graphics/generic_button.h"
#include "graphics/scrollbar.h"
#include "input/input.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned int goal_focus;
static int goal_view;
static const char *goal_labels[]={"전체","내 도시","다른 도시","함께 달성"};
static const char *goal_files[]={"objective-status.txt","objective-status-mine.txt","objective-status-others.txt","objective-status-shared.txt"};
static void goal_scrolled(void){window_invalidate();}
static scrollbar_type goal_scroll={548,134,240,468,240,goal_scrolled,0,0,0,0,0,20};
static void goal_close(const generic_button *b){window_go_back();}
static void goal_select(const generic_button *b){goal_view=b->parameter1;scrollbar_init(&goal_scroll,0,0);window_invalidate();}
static generic_button goal_buttons[]={
 {80,94,110,26,goal_select,0,0},{194,94,110,26,goal_select,0,1},
 {308,94,110,26,goal_select,0,2},{422,94,110,26,goal_select,0,3},
 {260,390,120,28,goal_close,0,0}};
static void goal_background(void){window_draw_underlying_window();}
static void goal_foreground(void){
 graphics_in_dialog();outer_panel_draw(56,48,33,24);
 {/* 기한 경쟁 (Augustus/objectives.py race_lines): the status text names it on its first line */
  int race=0;const char *d=getenv("AUGUSTUS_MP_BRIDGE");char p[2048],first[64]="";
  if(d){snprintf(p,sizeof(p),"%s/objective-status.txt",d);FILE *f=fopen(p,"rb");if(f){if(!fgets(first,sizeof(first),f))first[0]=0;fclose(f);}race=!strncmp(first,"기한 경쟁",strlen("기한 경쟁"));}
  if(race){uint8_t t[64];encoding_from_utf8("기한 경쟁",t,sizeof(t));text_draw_centered(t,66,65,508,FONT_LARGE_BLACK,0);}
  else text_draw_centered(translation_for(TR_MP_OBJECTIVES),66,65,508,FONT_LARGE_BLACK,0);}
 for(int i=0;i<4;i++){
  int x=80+114*i;uint8_t title[64];encoding_from_utf8(goal_labels[i],title,sizeof(title));
  large_label_draw_custom_size(x,94,110,26);
  if(i==goal_view){graphics_draw_rect(x,94,110,26,COLOR_BORDER_BROWN);graphics_draw_rect(x+1,95,108,24,COLOR_BORDER_BROWN);}
  text_draw_centered(title,x,101,110,FONT_NORMAL_BLACK,(i==goal_view || goal_focus==(unsigned)(i+1))?COLOR_BORDER_BROWN:0);
 }
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],line[512];FILE *f=0;
 if(dir){snprintf(path,sizeof(path),"%s/%s",dir,goal_files[goal_view]);f=fopen(path,"rb");}
 static uint8_t lines[256][1024];int rows=0,height=0;
 while(f && rows<256 && fgets(line,sizeof(line),f)){
  line[strcspn(line,"\r\n")]=0;encoding_from_utf8(line,lines[rows],sizeof(lines[rows]));rows++;
 }
 if(f)fclose(f);
 int line_height=font_definition_for(FONT_NORMAL_BLACK)->line_height;
 if(line_height<11)line_height=11;
 for(int i=0;i<rows;i++)height+=text_measure_multiline(lines[i],456,FONT_NORMAL_BLACK,0)*(line_height+5)+8;
 scrollbar_update_total_elements(&goal_scroll,height);
 graphics_set_clip_rectangle(80,134,462,240);
 int y=136-(int)goal_scroll.scroll_position;
 for(int i=0;i<rows;i++)y+=text_draw_multiline(lines[i],80,y,456,0,FONT_NORMAL_BLACK,0)+8;
 if(!rows)text_draw_multiline(translation_for(TR_MP_OBJECTIVES_FREE),80,136,456,0,FONT_NORMAL_BLACK,0);
 graphics_reset_clip_rectangle();scrollbar_draw(&goal_scroll);
 large_label_draw_custom_size(260,390,120,28);
 text_draw_centered(translation_for(TR_BUTTON_OK),260,398,120,FONT_NORMAL_BLACK,0);
 graphics_reset_dialog();
}
static void goal_handle(const mouse *m,const hotkeys *h){
 if(scrollbar_handle_mouse(&goal_scroll,mouse_in_dialog(m),1))return;
 if(generic_buttons_handle_mouse(mouse_in_dialog(m),0,0,goal_buttons,5,&goal_focus))return;
 if(input_go_back_requested(m,h)||h->enter_pressed)window_go_back();
}
static void menu_mp_goals(int param){
 clear_state();window_city_show();
 goal_view=0;goal_focus=0;scrollbar_init(&goal_scroll,0,0);
 window_type w={WINDOW_PLAIN_MESSAGE_DIALOG,goal_background,goal_foreground,goal_handle};window_show(&w);
}
