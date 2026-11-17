/* Trade history: a task-sized dialog over the empire map (576x448 at 32,16). */
static void history_back_to_form(void){history_from_form=0;history_tab=0;trade_tab=1;notice[0]=0;window_invalidate();}
static void history_open_trade(void);
static void history_back(void){if(history_from_form==1)history_back_to_form();else if(history_from_form==3){history_from_form=0;history_open_trade();}else{history_from_form=0;return_from_lobby();}}
static void history_open_trade(void){if(history_from_form && history_from_form!=3){history_back();return;}history_from_form=0;gift_send_pending=0;gift_send_error[0]=0;gift_peer_locked=0;gift_picker=0;gift_received=5;partner_direct=0;partner_page=0;partner_read_at=0;history_tab=0;trade_tab=1;notice[0]=0;window_invalidate();}
static void history_click(const generic_button *b){if(b->parameter1==1)history_open_trade();else{if(history_from_form==2)side_return_tab=0;history_from_form=0;return_from_lobby();}}
static generic_button history_buttons[]={{72,408,200,28,history_click,0,1},{368,408,200,28,history_click,0,2}};
static int history_focus;
/* Up to 50 recent trades (live_history); ten rows show at once under the original scrollbar. */
#include "graphics/scrollbar.h"
#define HISTORY_ROWS 10
static char history_lines[50][256];static int history_count;
static void history_scrolled(void){window_invalidate();}
static scrollbar_type history_scroll={.x=536,.y=100,.length=288,.scrollable_width=464,.on_scroll_callback=history_scrolled,.step_size=1};
static void history_read(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],buf[16384]={0};history_count=0;
 if(dir){snprintf(path,sizeof(path),"%s/trade-history.txt",dir);FILE *f=fopen(path,"rb");if(f){fread(buf,1,sizeof(buf)-1,f);fclose(f);}}
 for(char *line=strtok(buf,"\n");line && history_count<50;line=strtok(0,"\n")){line[strcspn(line,"\r")]=0;if(line[0] && strcmp(line,"아직 거래 이력이 없습니다."))snprintf(history_lines[history_count++],256,"%s",line);}
}
static void history_scroll_open(void){history_scroll.elements_in_view=HISTORY_ROWS;history_read();scrollbar_init(&history_scroll,0,(unsigned)history_count);}
static void history_screen_draw(void){
 graphics_in_dialog();outer_panel_draw(32,16,36,28);
 draw_utf8("거래 이력",72,40,496,FONT_LARGE_BLACK);
 history_read();scrollbar_update_total_elements(&history_scroll,(unsigned)history_count);
 draw_utf8(history_count>HISTORY_ROWS?"최근 거래 50건까지 · 새 거래가 맨 위 · 휠이나 막대로 넘겨 보세요.":"최근 거래 50건까지 · 새 거래가 맨 위에 표시됩니다.",72,72,496,FONT_NORMAL_BLACK);
 int scroll=history_count>HISTORY_ROWS,width=scroll?29:31;
 inner_panel_draw(72,100,width,18);
 int y=110;
 for(int row=0;row<HISTORY_ROWS;row++){
  int i=row+(scroll?(int)history_scroll.scroll_position:0);if(i>=history_count)break;
  draw_utf8(history_lines[i],84,y+6,width*16-24,FONT_NORMAL_WHITE);if(row<HISTORY_ROWS-1 && i<history_count-1)graphics_draw_line(80,72+width*16-8,y+27,y+27,0xff6d6750);y+=27;
 }
 if(scroll)scrollbar_draw(&history_scroll);
 if(!history_count){uint8_t empty[256];encoding_from_utf8("아직 거래 이력이 없습니다.",empty,sizeof(empty));text_draw_centered(empty,72,236,496,FONT_NORMAL_WHITE,0);}
 if(notice[0])draw_utf8(notice,72,390,496,FONT_NORMAL_RED);
 /* from the form both buttons go back (form left); otherwise back to the city/map on the left, trade on the right */
 history_buttons[0].x=history_from_form?72:368;history_buttons[1].x=history_from_form?368:72;
 mp_label_button(history_buttons[0].x,408,200,28,history_from_form?"뒤로":"플레이어 교역",0);mp_label_button(history_buttons[1].x,408,200,28,return_label(),0);
 graphics_reset_dialog();
}
static void history_screen_handle(const mouse *m,const hotkeys *h){
 if(h->close_pressed){if(history_from_form)history_back();else return_from_lobby();return;}
 const mouse *local=mouse_in_dialog(m);if(history_count>HISTORY_ROWS && scrollbar_handle_mouse(&history_scroll,local,1))return;
 generic_buttons_handle_mouse(local,0,0,history_buttons,2,&history_focus);
}
