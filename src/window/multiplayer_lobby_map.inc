/* Read-only room map. Coordinates originate at the host's authored scenario.
 * Waiting room geometry: map x 48..480 / y 114..330, roster x 496..752. */
#define LOBBY_MAP_X 48
#define LOBBY_MAP_Y 114
#define LOBBY_MAP_W 432
#define LOBBY_MAP_H 216
#define LOBBY_ROSTER_X 496
#define LOBBY_ROSTER_Y 112
static struct {int flag,x,y,num,color;char name[256],status[256],id[256];} lobby_map_cities[40];
static int lobby_hover_index=-1;
static int lobby_map_count,lobby_map_mine=-1,lobby_rome_x=-1,lobby_rome_y=-1; /* Rome: optional "ROME x y" last line */
/* For the scenario window in a room: the holder of a player city ("이름 · 준비", "빈자리"). */
static int lobby_city_flag_by_name(const char *name){for(int i=0;i<lobby_map_count;i++)if(lobby_map_cities[i].flag && !strcmp(lobby_map_cities[i].name,name))return lobby_map_cities[i].flag;return 0;}
static const char *lobby_city_status_by_name(const char *name){for(int i=0;i<lobby_map_count;i++)if(lobby_map_cities[i].flag && !strcmp(lobby_map_cities[i].name,name))return lobby_map_cities[i].status[0]?lobby_map_cities[i].status:0;return 0;}
static int lobby_roster_mouse_x=-1,lobby_roster_mouse_y=-1;
static int lobby_map_load(void){
 FILE *f=room_list_open("lobby-map.txt");char line[128];int count;
 lobby_map_count=0;lobby_map_mine=-1;lobby_rome_x=lobby_rome_y=-1;if(!f)return 0;
 if(!room_list_line(f,line,sizeof(line)) || strcmp(line,"AUGLOBBYMAP3"))goto fail;
 count=scene_number(f,40);if(count<1)goto fail;
 for(int i=0;i<count;i++){
  char extra;int flag,x,y,num,color;
  if(!room_list_line(f,line,sizeof(line)) || sscanf(line,"%d %d %d %d %d %c",&flag,&x,&y,&num,&color,&extra)!=5)goto fail;
  if(flag<0 || flag>3 || x<0 || x>2000 || y<0 || y>1000 || num<0 || num>8 || color< -1 || color>7)goto fail;
  lobby_map_cities[i].flag=flag;lobby_map_cities[i].x=x;lobby_map_cities[i].y=y;lobby_map_cities[i].num=num;lobby_map_cities[i].color=color;
  if(!room_list_line(f,lobby_map_cities[i].name,256) || !room_list_line(f,lobby_map_cities[i].status,256) || !room_list_line(f,lobby_map_cities[i].id,256))goto fail;
  if(flag==3)lobby_map_mine=i;
 }
 while(room_list_line(f,line,sizeof(line))){int rx,ry;char extra;
  if(sscanf(line,"ROME %d %d %c",&rx,&ry,&extra)==2 && rx>=0 && rx<=2000 && ry>=0 && ry<=1000){lobby_rome_x=rx;lobby_rome_y=ry;}
 }
 fclose(f);lobby_map_count=count;return 1;
fail:fclose(f);lobby_map_count=0;lobby_map_mine=-1;return 0;
}
/* Eight pastel player colours (same table as multiplayer/route_post.c): sky, coral, mint, apricot, lavender, aqua, rose, lemon. */
static const color_t lobby_player_colors[8]={0xff7fb8f5,0xfff28b82,0xff7fd6a0,0xfff7b267,0xffb9a0f0,0xff6fd3cf,0xfff5a3cf,0xffe3d96b};
static color_t lobby_player_color(int color){return color>=0 && color<8?lobby_player_colors[color]:0xffcbd1d7;}
static void lobby_map_point(int i,int *x,int *y){
 *x=LOBBY_MAP_X+lobby_map_cities[i].x*LOBBY_MAP_W/2000;*y=LOBBY_MAP_Y+lobby_map_cities[i].y*LOBBY_MAP_H/1000;
 if(*x<LOBBY_MAP_X+12)*x=LOBBY_MAP_X+12;if(*x>LOBBY_MAP_X+LOBBY_MAP_W-13)*x=LOBBY_MAP_X+LOBBY_MAP_W-13;if(*y<LOBBY_MAP_Y+12)*y=LOBBY_MAP_Y+12;if(*y>LOBBY_MAP_Y+LOBBY_MAP_H-13)*y=LOBBY_MAP_Y+LOBBY_MAP_H-13;
}
static int lobby_map_hit(int x,int y){
 int best=-1,distance=225;
 for(int i=0;i<lobby_map_count;i++){int px,py;lobby_map_point(i,&px,&py);int d=(x-px)*(x-px)+(y-py)*(y-py);if(d<distance){best=i;distance=d;}}
 return best;
}
/* Match the drawn participant rows, skipping interleaved neutral cities. */
static int lobby_roster_hit(int x,int y){
 if(x<LOBBY_ROSTER_X || x>=752 || y<LOBBY_ROSTER_Y-1 || y>=LOBBY_ROSTER_Y-1+8*32)return -1;
 int wanted=(y-(LOBBY_ROSTER_Y-1))/32,row=0;
 for(int i=0;i<lobby_map_count;i++)if(lobby_map_cities[i].num){if(row++==wanted)return i;}
 return -1;
}
/* Colour swatches under the map (shown once I hold a city). */
#define LOBBY_COLOR_X 300
#define LOBBY_COLOR_Y (LOBBY_MAP_Y+LOBBY_MAP_H+9)
#define LOBBY_COLOR_STEP 22
static int lobby_color_taken(int color){for(int i=0;i<lobby_map_count;i++)if(i!=lobby_map_mine && lobby_map_cities[i].flag>=2 && lobby_map_cities[i].color==color)return 1;return 0;}
static int lobby_color_click(int x,int y){
 if(lobby_map_mine<0 || y<LOBBY_COLOR_Y || y>=LOBBY_COLOR_Y+16 || x<LOBBY_COLOR_X || x>=LOBBY_COLOR_X+8*LOBBY_COLOR_STEP)return 0;
 int c=(x-LOBBY_COLOR_X)/LOBBY_COLOR_STEP;if(x-LOBBY_COLOR_X-c*LOBBY_COLOR_STEP>=18)return 1;
 if(lobby_map_cities[lobby_map_mine].color==c)return 1;
 char phase[64];room_read("start-state.txt",phase,sizeof(phase));
 if(phase[0] && strncmp(phase,"lobby",5)){strcpy(notice,"게임 시작 준비 중이거나 시작한 뒤에는 색을 바꿀 수 없습니다.");return 1;}
 if(lobby_color_taken(c)){strcpy(notice,"다른 플레이어가 쓰고 있는 색입니다.");return 1;}
 char payload[8];snprintf(payload,sizeof(payload),"%d",c);
 if(!mp_client_command("color",payload))strcpy(notice,"이전 요청을 처리 중입니다. 잠시 기다려 주세요.");else notice[0]=0;
 return 1;
}
static int lobby_map_choose(int index){
 if(index<0 || index>=lobby_map_count || !lobby_map_cities[index].num)return 0;
 if(lobby_map_cities[index].flag==3)return 1;
 char phase[64];room_read("start-state.txt",phase,sizeof(phase));
 if(phase[0] && strncmp(phase,"lobby",5)){strcpy(notice,"게임 시작 준비 중이거나 시작한 뒤에는 도시를 변경할 수 없습니다.");return 0;}
 room_read_choices();
 for(int i=0;i<room_choice_count;i++)if(!strcmp(room_choices[i].id,lobby_map_cities[index].id)){
  if(!room_choices[i].available){strcpy(notice,"다른 플레이어가 선택한 도시입니다.");return 0;}
  char name[256],payload[384];encoding_to_utf8(player_name,name,sizeof(name),0);snprintf(payload,sizeof(payload),"%s\n%s",room_choices[i].id,name);
  if(!mp_client_command("choose-city",payload)){strcpy(notice,"도시 선택을 처리 중입니다. 잠시 기다려 주세요.");return 0;}
  notice[0]=0;return 1;
 }
 return 0;
}
static void lobby_map_draw(void){
 int valid=lobby_map_load();
 int hovered=lobby_roster_hit(lobby_roster_mouse_x,lobby_roster_mouse_y);
 if(hovered<0 && lobby_roster_mouse_x>=LOBBY_MAP_X && lobby_roster_mouse_x<LOBBY_MAP_X+LOBBY_MAP_W && lobby_roster_mouse_y>=LOBBY_MAP_Y && lobby_roster_mouse_y<LOBBY_MAP_Y+LOBBY_MAP_H){
  hovered=lobby_map_hit(lobby_roster_mouse_x,lobby_roster_mouse_y);if(hovered>=0 && !lobby_map_cities[hovered].num)hovered=-1;
 }
 lobby_hover_index=hovered;
 draw_utf8("제국지도",LOBBY_MAP_X,96,LOBBY_MAP_W,FONT_NORMAL_BLACK);
 draw_utf8("참가 플레이어",LOBBY_ROSTER_X,96,256,FONT_NORMAL_BLACK);
 { /* Head count beside the title (user 2026-11-13): "참가 6 · 도시 선택 5 · 준비 3", right-aligned in the roster column.
      The bridge writes a full and a short form; the first that fits beside the title is drawn, never clipped. */
  char counts[256];room_read("lobby-counts.txt",counts,sizeof(counts));
  uint8_t title[64];encoding_from_utf8("참가 플레이어",title,sizeof(title));
  int room_left=752-(LOBBY_ROSTER_X+text_get_width(title,FONT_NORMAL_BLACK)+10);
  char *form=strtok(counts,"\n");
  while(form){
   uint8_t converted[256];encoding_from_utf8(form,converted,sizeof(converted));int w=text_get_width(converted,FONT_SMALL_PLAIN);
   if(w<=room_left){text_draw(converted,752-w,99,FONT_SMALL_PLAIN,0);break;}
   form=strtok(0,"\n");
  }
 }
 const image *map=image_get(image_group(GROUP_EMPIRE_MAP));float scale=map->width/(float)LOBBY_MAP_W;
 graphics_set_clip_rectangle(LOBBY_MAP_X,LOBBY_MAP_Y,LOBBY_MAP_W,LOBBY_MAP_H);
 image_draw(image_group(GROUP_EMPIRE_MAP),(int)(LOBBY_MAP_X*scale),(int)(LOBBY_MAP_Y*scale),COLOR_MASK_NONE,scale);
 /* Fixed capital, display only: same place and picture as the scenario window and the editor. Cities draw on top. */
 if(lobby_rome_x>=0)mp_rome_draw(LOBBY_MAP_X+lobby_rome_x*LOBBY_MAP_W/2000,LOBBY_MAP_Y+lobby_rome_y*LOBBY_MAP_H/1000,.45f,0);
 for(int pass=0;pass<2;pass++)for(int i=0;i<lobby_map_count;i++){
  int flag=lobby_map_cities[i].flag;if((flag==3)!=(pass==1))continue;
  int x,y;lobby_map_point(i,&x,&y);
  if(!flag){graphics_fill_rect(x-5,y-5,11,11,0xfffaf7ed);graphics_draw_rect(x-6,y-6,13,13,0xff293445);graphics_fill_rect(x-2,y-2,5,5,0xff293445);continue;}
  graphics_fill_rect(x-8,y-7,17,15,flag==1?0xfff4f4f0:lobby_player_color(lobby_map_cities[i].color));graphics_draw_rect(x-8,y-7,17,15,0xff6b5638); /* a white player's square still stands out */
  graphics_draw_rect(x-9,y-8,19,17,flag==3?0xffffd278:0xffe6dbba);
  if(flag==3){graphics_draw_rect(x-12,y-11,25,23,0xffffd278);graphics_draw_rect(x-13,y-12,27,25,0xff65451b);
   int tx=x>LOBBY_MAP_X+LOBBY_MAP_W-80?x-72:x+16,ty=y>LOBBY_MAP_Y+LOBBY_MAP_H-33?y-23:y+13;
   graphics_fill_rect(tx,ty,56,17,0xfff5e4b7);draw_utf8("내 도시",tx+3,ty+2,52,FONT_NORMAL_BLACK);
  }
  char number[16];snprintf(number,sizeof(number),"%d",lobby_map_cities[i].num);draw_utf8(number,x-5,y-5,16,FONT_NORMAL_BLACK);
 }
 if(hovered>=0){
  int x,y;lobby_map_point(hovered,&x,&y);
  graphics_draw_rect(x-16,y-15,33,31,0xff543713);graphics_draw_rect(x-15,y-14,31,29,0xffffdc67);graphics_draw_rect(x-14,y-13,29,27,0xffffdc67);
  /* name and city map: the hover card (lobby_hover_preview_draw), drawn last so nothing covers it */
 }
 graphics_reset_clip_rectangle();graphics_draw_rect(LOBBY_MAP_X,LOBBY_MAP_Y,LOBBY_MAP_W,LOBBY_MAP_H,0xff6b5638);
 char own[384];
 if(lobby_map_mine>=0)snprintf(own,sizeof(own),"내 도시: %d. %s",lobby_map_cities[lobby_map_mine].num,lobby_map_cities[lobby_map_mine].name);
 else snprintf(own,sizeof(own),"%s",valid?"내 도시: 미선택 · 지도나 참가 목록에서 선택하세요":"지도 정보를 기다리고 있습니다.");
 draw_utf8(own,LOBBY_MAP_X,LOBBY_MAP_Y+LOBBY_MAP_H+10,lobby_map_mine>=0?LOBBY_COLOR_X-56-LOBBY_MAP_X:LOBBY_MAP_W,FONT_NORMAL_BLACK);
 if(lobby_map_mine>=0){
  /* My colour: eight swatches right after choosing a city. Mine has the gold frame; one another player holds is crossed out. */
  draw_utf8("내 색",LOBBY_COLOR_X-44,LOBBY_COLOR_Y+1,40,FONT_NORMAL_BLACK);
  for(int c=0;c<8;c++){
   int x=LOBBY_COLOR_X+c*LOBBY_COLOR_STEP,y=LOBBY_COLOR_Y,mine=lobby_map_cities[lobby_map_mine].color==c,taken=!mine && lobby_color_taken(c);
   graphics_fill_rect(x,y,18,16,lobby_player_colors[c]);graphics_draw_rect(x,y,18,16,0xff6b5638);
   if(mine){graphics_draw_rect(x-2,y-2,22,20,0xffffd278);graphics_draw_rect(x-3,y-3,24,22,0xff65451b);}
   else if(taken){graphics_draw_line(x+2,x+15,y+2,y+13,0xff3a2a14);graphics_draw_line(x+2,x+15,y+13,y+2,0xff3a2a14);}
   else if(lobby_roster_mouse_x>=x && lobby_roster_mouse_x<x+18 && lobby_roster_mouse_y>=y && lobby_roster_mouse_y<y+16)graphics_draw_rect(x-1,y-1,20,18,0xffffdc67);
  }
 }
 draw_utf8("흰 표식: 시작 시 중립도시",LOBBY_ROSTER_X,LOBBY_MAP_Y+LOBBY_MAP_H+12,256,FONT_SMALL_PLAIN);
 int row=0;
 for(int i=0;i<lobby_map_count;i++){
  if(!lobby_map_cities[i].num)continue;
  int y=LOBBY_ROSTER_Y+row*32,rx=LOBBY_ROSTER_X+12,rw=752-rx;char text[640];
  /* Ready players (state "준비 ...", sent by lobby_map.py) get a green row; my own row keeps its gold frame. */
  const char *last=0,*scan=lobby_map_cities[i].status;while((scan=strstr(scan," · "))){last=scan+4;scan+=4;}
  /* The host starts the game and has no ready button: its row always counts as ready. */
  int ready=lobby_map_cities[i].flag>=2 && last && (!strncmp(last,"준비",strlen("준비")) || !strncmp(last,"방장",strlen("방장")));
  if(ready){graphics_fill_rect(rx,y-1,rw,32,0xffd3ebc3);graphics_draw_rect(rx,y-1,rw,32,lobby_map_cities[i].flag==3?0xffb88836:0xff4f8a32);graphics_fill_rect(rx+1,y,4,30,0xff3f8a2a);}
  else if(lobby_map_cities[i].flag==3){graphics_fill_rect(rx,y-1,rw,32,0xffd7e5ec);graphics_draw_rect(rx,y-1,rw,32,0xffb88836);}
  else graphics_draw_rect(rx,y-1,rw,32,0xffbca782);
  if(i==hovered){graphics_fill_rect(rx,y-1,rw,32,0xffffedb7);graphics_draw_rect(rx,y-1,rw,32,0xff976a22);}
  graphics_fill_rect(LOBBY_ROSTER_X+1,y+3,8,20,lobby_player_color(lobby_map_cities[i].color));graphics_draw_rect(LOBBY_ROSTER_X,y+2,10,22,0xff6b5638);
  snprintf(text,sizeof(text),"%d. %s",lobby_map_cities[i].num,lobby_map_cities[i].name);
  draw_utf8(text,rx+6,y+1,rw-12,FONT_NORMAL_BLACK);
  snprintf(text,sizeof(text),"%s",lobby_map_cities[i].status);
  char *split=0,*next=text;while((next=strstr(next," · "))){split=next;next+=4;}
  if(split){
   /* State on the right ('대기 400ms': the player's ping follows its state), the name gets what is left. */
   const char *state=lobby_map_cities[i].flag==1?"중립 예정":split+4;uint8_t enc[256];encoding_from_utf8(state,enc,sizeof(enc));
   int sw=text_get_width(enc,FONT_SMALL_PLAIN);if(sw<70)sw=70;if(sw>120)sw=120;
   *split=0;draw_utf8(text,rx+18,y+18,220-6-sw,FONT_SMALL_PLAIN);room_right(state,752-6,y+18,sw,FONT_SMALL_PLAIN);
  }
  else draw_utf8(text,rx+18,y+18,rw-24,FONT_SMALL_PLAIN);
  row++;
 }
 if(!valid){char roster[8192];room_read("lobby-roster.txt",roster,sizeof(roster));char *line=strtok(roster,"\n");int y=LOBBY_ROSTER_Y+2;while(line && y<LOBBY_MAP_Y+LOBBY_MAP_H){draw_utf8(line,LOBBY_ROSTER_X+12,y,244,FONT_SMALL_PLAIN);line=strtok(0,"\n");y+=24;}}
}

/* Waiting room chat: five lines show, up to 100 are kept; the original scrollbar on the right appears once there
 * are more than five. It stays at the newest line unless the player scrolled up. */
#include "graphics/scrollbar.h"
#define LOBBY_CHAT_ROWS 5
static scrollbar_type lobby_chat_sb={.x=752-28,.y=ROOM_CHAT_Y+4,.length=72,.scrollable_width=704,.step_size=1,.elements_in_view=LOBBY_CHAT_ROWS};
static int lobby_chat_total,lobby_chat_ready;
static int lobby_chat_first(int count){
 if(!lobby_chat_ready){lobby_chat_ready=1;scrollbar_init(&lobby_chat_sb,0,0);}
 int old_max=lobby_chat_total>LOBBY_CHAT_ROWS?lobby_chat_total-LOBBY_CHAT_ROWS:0,new_max=count>LOBBY_CHAT_ROWS?count-LOBBY_CHAT_ROWS:0;
 int at_bottom=(int)lobby_chat_sb.scroll_position>=old_max;
 if(count!=lobby_chat_total){
  int keep=(int)lobby_chat_sb.scroll_position;
  lobby_chat_sb.elements_in_view=LOBBY_CHAT_ROWS;scrollbar_update_total_elements(&lobby_chat_sb,(unsigned)count);
  scrollbar_reset(&lobby_chat_sb,(unsigned)(at_bottom || keep>new_max?new_max:keep));lobby_chat_total=count;
 }
 int first=(int)lobby_chat_sb.scroll_position;return first>new_max?new_max:first;
}
static int lobby_chat_scroll_input(const mouse *m){return lobby_chat_total>LOBBY_CHAT_ROWS && scrollbar_handle_mouse(&lobby_chat_sb,m,1);}
static void lobby_chat_draw(void){
 static char buf[65536];room_read("lobby-chat-colors.txt",buf,sizeof(buf));
 if(strncmp(buf,"AUGCHAT1",8) || (buf[8]!='\n' && !(buf[8]=='\r' && buf[9]=='\n'))){char chat[8192];room_read("lobby-chat.txt",chat,sizeof(chat));char *rows[64];int count=0;char *line=strtok(chat,"\n");while(line && count<64){rows[count++]=line;line=strtok(0,"\n");}for(int i=count>5?count-5:0,y=ROOM_CHAT_Y+5;i<count;i++,y+=15){if(i)draw_chat_utf8(rows[i],60,y,680,FONT_NORMAL_WHITE);else draw_utf8(rows[i],60,y,680,FONT_NORMAL_WHITE);}return;}
 char *rows[100];int count=0;char *line=strtok(strchr(buf,'\n')+1,"\n");while(line && count<100){rows[count++]=line;line=strtok(0,"\n");}
 int first=lobby_chat_first(count),body_w=count>LOBBY_CHAT_ROWS?496:520;
 if(count>LOBBY_CHAT_ROWS)scrollbar_draw(&lobby_chat_sb);
 for(int i=first,y=ROOM_CHAT_Y+5;i<count && i<first+LOBBY_CHAT_ROWS;i++,y+=15){
  char *name=strchr(rows[i],'\t');if(!name)continue;*name++=0;char *body=strchr(name,'\t');if(!body)continue;*body++=0;body[strcspn(body,"\r\n")]=0;
  int color=atoi(rows[i]);color_t ink=lobby_player_color(color);
  mp_chat_draw_chip(60,y+2,7,10,color); /* colour at sending; none for system, no city yet, old record */
  /* players' names and what they type are never looked up in the language catalog; a notice (시스템) is (2026-11-14) */
  int player_row=strcmp(name,"시스템")!=0;if(player_row)mp_i18n_suspend(1);
  uint8_t converted[1024];encoding_from_utf8(name,converted,sizeof(converted));text_draw_ellipsized(converted,74,y,136,FONT_NORMAL_WHITE,ink);
  draw_utf8(body,220,y,body_w,FONT_NORMAL_WHITE);
  if(player_row)mp_i18n_suspend(0);
 }
}

/* Hover card (user 2026-11-13, replaces the "도시 변경" button and its picker): resting the mouse on a roster row or a
 * player city on the map shows that city's map, the same bounded overview as the picker (city_preview.py). The request
 * goes out after 250 ms on the same city; the bridge keeps each city's answer, so going back to a city is immediate. */
static int lobby_hover_last=-1;static unsigned int lobby_hover_since;static char lobby_hover_asked[256];
/* Its own file, not command.txt: a hover request there held the one command slot and the city click that followed was
 * dropped (user 2026-11-13). "id\ncounter": the counter makes a repeated ask for the same city a new request. */
static int lobby_hover_request(const char *id){
 static unsigned int counter;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
 char path[2048],tmp[2048];snprintf(path,sizeof(path),"%s/preview-request.txt",dir);snprintf(tmp,sizeof(tmp),"%s/preview-request.tmp",dir);
 FILE *f=fopen(tmp,"wb");if(!f)return 0;fprintf(f,"%s\n%u",id,++counter);if(fclose(f))return 0;
 remove(path);return rename(tmp,path)==0;   /* Windows rename does not replace: the bridge only misses one look at worst */
}
static void lobby_hover_preview_draw(void){
 int i=lobby_hover_index;unsigned int now=time_get_millis();
 if(i<0 || i>=lobby_map_count || !lobby_map_cities[i].num || !lobby_map_cities[i].id[0]){lobby_hover_last=-1;lobby_hover_asked[0]=0;return;}   /* hovering again asks again (the bridge answers from its own copy) */
 if(i!=lobby_hover_last){lobby_hover_last=i;lobby_hover_since=now;}
 static char raw[27000];char city[64];int w=0,h=0,offset=0;room_read("city-preview.txt",raw,sizeof(raw));
 int ready=sscanf(raw,"%63s\n%d %d\n%n",city,&w,&h,&offset)==3 && !strcmp(city,lobby_map_cities[i].id) && w>=1 && w<=160 && h>=1 && h<=160 && offset>0
  && strcspn(raw+offset,"\r\n")==(size_t)w*h && strspn(raw+offset,"BDWRTFL")==(size_t)w*h;
 if(!ready && strcmp(lobby_hover_asked,lobby_map_cities[i].id) && now-lobby_hover_since>=250)
  if(lobby_hover_request(lobby_map_cities[i].id))snprintf(lobby_hover_asked,sizeof(lobby_hover_asked),"%s",lobby_map_cities[i].id);
 const int CW=208,MW=192,MH=144;int mw=MW,mh=MH;
 if(ready){mh=h*MW/w;if(mh>MH){mh=MH;mw=w*MH/h;}}
 int ch=ready?8+18+4+MH+4+14+6:8+18+6+16+8;
 int mx=lobby_roster_mouse_x,my=lobby_roster_mouse_y,px,py;
 if(mx>=LOBBY_ROSTER_X)px=LOBBY_ROSTER_X-CW-8;                 /* roster row: the card sits over the map, left of the list */
 else{px=mx+18;if(px+CW>792)px=mx-CW-12;}
 py=my+12;if(py+ch>440)py=440-ch;if(py<8)py=8;if(px<8)px=8;
 graphics_fill_rect(px,py,CW,ch,0xffffedb7);graphics_draw_rect(px,py,CW,ch,0xff976a22);graphics_draw_rect(px+1,py+1,CW-2,ch-2,0xffe6cf8f);
 char title[320];snprintf(title,sizeof(title),"%d. %s",lobby_map_cities[i].num,lobby_map_cities[i].name);draw_utf8(title,px+8,py+7,CW-16,FONT_NORMAL_BLACK);
 if(!ready){
  char status[512];room_read("city-preview-status.txt",status,sizeof(status));status[strcspn(status,"\r\n")]=0;
  draw_utf8(status[0] && !strcmp(lobby_hover_asked,lobby_map_cities[i].id)?status:"도시 지도를 불러오는 중입니다.",px+8,py+8+18+6,CW-16,FONT_SMALL_PLAIN);return;
 }
 const char *grid=raw+offset;int left=px+8+(MW-mw)/2,top=py+8+18+4+(MH-mh)/2;
 graphics_fill_rect(px+8,py+8+18+4,MW,MH,0xffd9c79a);
 for(int y=0;y<h;y++)for(int x=0;x<w;){int end=x+1;while(end<w && grid[y*w+end]==grid[y*w+x])end++;
  graphics_fill_rect(left+x*mw/w,top+y*mh/h,end*mw/w-x*mw/w,(y+1)*mh/h-y*mh/h,room_preview_color(grid[y*w+x]));x=end;}
 graphics_draw_rect(left-1,top-1,mw+2,mh+2,0xff6b5638);
 const char *caption=grid+w*h;while(*caption=='\n' || *caption=='\r')caption++;
 char cap[256];snprintf(cap,sizeof(cap),"%s",caption);cap[strcspn(cap,"\r\n")]=0;
 draw_utf8(cap,px+8,py+8+18+4+MH+4,CW-16,FONT_SMALL_PLAIN);
}
