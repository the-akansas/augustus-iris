#include "graphics/scrollbar.h"
#include "core/time.h"
/* Mailbox lists are streamed: the number of scenarios is not tied to a UI buffer.
 * Selection stays tentative until confirmed, and filtering keeps source indices. */
#define ROOM_LIST_ROWS 8
#define SELECTOR_PANEL_X 16
#define SELECTOR_PANEL_Y 16
#define SELECTOR_PANEL_W 38
#define SELECTOR_PANEL_H 28
#define SELECTOR_ROW_Y 156
#define SELECTOR_ROW_STEP 24
#define ROOM_LIST_LINE 2048
static int selector_category,selector_profile_waiting;
#ifdef MP_HALL
static int hall_local_asked;
#endif
static char selector_profile_request[1024],selector_profile_notice[512];
static int scene_opened;
static int room_selector, selector_offset, selector_total, selector_selected=-1;
static int selector_rows, selector_hover=-1, selector_indices[ROOM_LIST_ROWS];
static char selector_labels[ROOM_LIST_ROWS][ROOM_LIST_LINE],selector_selected_label[ROOM_LIST_LINE];
static void selector_scan(void);
static void selector_scrolled(void);
/* The scenario and save lists (LAN 2, hall 5) give every entry two lines (user 2026-11-17: "여러 줄이라도 잘 보이게"):
 * the title whole, then who sent it, the date, the seats under it. Four entries show, the list scrolls. */
static int selector_tall(void){return room_selector==2 || room_selector==5;}
static int selector_view(void){return selector_tall()?4:ROOM_LIST_ROWS;}
static int selector_step(void){return selector_tall()?2*SELECTOR_ROW_STEP:SELECTOR_ROW_STEP;}
static scrollbar_type selector_scroll={.x=552,.y=156,.length=192,.scrollable_width=504,.elements_in_view=ROOM_LIST_ROWS,.on_scroll_callback=selector_scrolled,.always_visible=1,.step_size=1};
/* The n-th tab field (0 first) of a hall list line, copied. */
static const char *selector_field(const char *line,int n,char *out,size_t size){
 out[0]=0;while(n-- >0){line=strchr(line,'\t');if(!line)return out;line++;}
 snprintf(out,size,"%s",line);out[strcspn(out,"\t\r\n")]=0;return out;
}
static const char *selector_display_label(const char *label){
#ifdef MP_HALL
 if(room_selector==5 || room_selector==6){   /* hall lists: "id, seats, title, sent by, state" and "code, country" */
  static char shown[ROOM_LIST_LINE];return selector_field(label,room_selector==6?1:2,shown,sizeof(shown));   /* the other fields have their own columns */
 }
#endif
 if(room_selector==2 && (selector_category==0 || selector_category==1)){
  const char *end=strchr(label,']');if(label[0]=='[' && end && end[1]==' ')return end+2;
 }
 if(room_selector==2 && selector_category==2){
  static char saved_label[ROOM_LIST_LINE];const char *end=strchr(label,']');
  if(end){snprintf(saved_label,sizeof(saved_label),"[%s]%s",!strncmp(label,"[이전 저장]",strlen("[이전 저장]"))?"과거":"최신",end+1);return saved_label;}
 }return label;
}
static void selector_scrolled(void){selector_offset=selector_scroll.scroll_position;selector_scan();window_request_refresh();}
/* The scenario list always shows its bar (its rows leave room); the other lists show it once they overflow. */
static void selector_sync_scroll(void){
 selector_scroll.always_visible=room_selector==2;selector_scroll.elements_in_view=selector_view();scrollbar_update_total_elements(&selector_scroll,selector_total);
 if(selector_scroll.scroll_position!=(unsigned)selector_offset)scrollbar_reset(&selector_scroll,selector_offset);
}

static uint8_t selector_query[193];
static char selector_previous_query[768];
static input_box selector_input={128,86,29,2,FONT_NORMAL_WHITE,1,selector_query,sizeof(selector_query)};
static int room_defaults_loaded,room_name_waiting;
static char room_pending_name[256];
static time_millis room_name_started;

static FILE *room_list_open(const char *name){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
 char path[2048];snprintf(path,sizeof(path),"%s/%s",dir,name);return fopen(path,"rb");
}
static int room_list_line(FILE *f,char *line,size_t size){
 if(!fgets(line,(int)size,f))return 0;
 size_t n=strcspn(line,"\r\n");
 if(!line[n] && n==size-1){int c;while((c=fgetc(f))!=EOF && c!='\n'){} }
 line[n]=0;return 1;
}
static void network_choice(const char *file,int index,char *text,size_t size,int *count){
 char line[ROOM_LIST_LINE];FILE *f=room_list_open(file);*count=0;text[0]=0;
 if(!f)return;
 while(room_list_line(f,line,sizeof(line))){if(*count==index)snprintf(text,size,"%s",line);(*count)++;}
 fclose(f);
}
static const char *selector_file(void){
 switch(room_selector){case 1:return "network-adapters.txt";case 2:return "network-starts.txt";
 case 3:return "network-recent-ips.txt";
#ifdef MP_HALL
 case 5:return selector_category==2?"hall-saves.txt":"hall-scenarios.txt";case 6:return "hall-countries.txt";
#endif
 default:return "network-player-names.txt";}
}
static int selector_matches(const char *line,const char *query){
 if(!*query)return 1;
 for(const unsigned char *start=(const unsigned char *)line;*start;start++){
  const unsigned char *a=start,*b=(const unsigned char *)query;
  while(*a && *b){unsigned int ac=*a,bc=*b;if(ac>='A' && ac<='Z')ac+=32;if(bc>='A' && bc<='Z')bc+=32;if(ac!=bc)break;a++;b++;}
  if(!*b)return 1;
 }
 return 0;
}
static int selector_category_of(const char *line){
 if(!strncmp(line,"[내 작업]",strlen("[내 작업]")))return 1;
 if(!strncmp(line,"[이어하기]",strlen("[이어하기]")))return 2;
 if(!strncmp(line,"[이전 저장]",strlen("[이전 저장]")))return 2;
 return 0;
}
static void selector_scan(void){
 char query[768],line[ROOM_LIST_LINE];encoding_to_utf8(selector_query,query,sizeof(query),0);
 if(strcmp(query,selector_previous_query)){snprintf(selector_previous_query,sizeof(selector_previous_query),"%s",query);selector_offset=0;}
 selector_rows=selector_total=0;
 FILE *f=room_list_open(selector_file());if(!f){selector_selected=-1;selector_selected_label[0]=0;selector_offset=0;return;}
 int index=0,selected_visible=0;
 while(room_list_line(f,line,sizeof(line))){
  /* the hall's lists: the input above them is the room title (5) or the ID (6), never a search; lines without a tab are
     the saves list's state words (wait / none / error) */
  int hall_list=0;
  int tab_ok=room_selector==2?selector_category_of(line)==selector_category:1;
#ifdef MP_HALL
  hall_list=room_selector==5 || room_selector==6;
  if(hall_list && !strchr(line,'\t')){index++;continue;}
  /* the room window's tabs (user 2026-11-15): the server's library, this PC's own scenarios ('local:'), the saves */
  if(room_selector==5 && selector_category<2)tab_ok=!strncmp(line,"local:",6)==(selector_category==1);
#endif
  if(tab_ok && (hall_list || selector_matches(line,query))){
   int same=1;
#ifdef MP_HALL
   /* the hall's scenario list changes under the player (a scenario sent or fetched): the pick stays only on the same entry */
   if(room_selector==5 && selector_selected_label[0]){size_t n=strcspn(line,"\t");same=!strncmp(line,selector_selected_label,n) && selector_selected_label[n]=='\t';}
#endif
   if(index==selector_selected && same){selected_visible=1;snprintf(selector_selected_label,sizeof(selector_selected_label),"%s",line);}
   if(selector_total>=selector_offset && selector_rows<selector_view()){selector_indices[selector_rows]=index;snprintf(selector_labels[selector_rows++],ROOM_LIST_LINE,"%s",line);}
   selector_total++;
  }
  index++;
 }
 fclose(f);
 if(!selected_visible){selector_selected=-1;selector_selected_label[0]=0;}
 /* Every list is one scroll range (no pages): the offset is the first row shown. */
 if(selector_offset>(selector_total>selector_view()?selector_total-selector_view():0)){selector_offset=selector_total>selector_view()?selector_total-selector_view():0;selector_scan();return;}
}
static void room_prefill(void){
 static int visual_mode_applied;
 if (!visual_mode_applied && getenv("AUGUSTUS_VISUAL_ROLE")) {
  visual_mode_applied = 1;
  network_mode = !strcmp(getenv("AUGUSTUS_VISUAL_ROLE"), "host") ? 1 : 2;
 }

 name_input.x=40;name_input.y=network_mode==2?260:network_mode==1?230:92;name_input.width_blocks=network_mode==1 || network_mode==2?22:18;
 network_input.x=40;network_input.y=106;network_input.width_blocks=18;
 if(room_defaults_loaded)return;
 char value[512];
 room_read("network-last-ip.txt",value,sizeof(value));if(!network_ip[0] && value[0])encoding_from_utf8(value,network_ip,sizeof(network_ip));
 room_read("network-last-name.txt",value,sizeof(value));if(!player_name[0] && value[0])encoding_from_utf8(value,player_name,sizeof(player_name));
 room_defaults_loaded=1;
}
static void room_ui_reset(void){
 scene_opened=0;input_box_stop(&selector_input);room_selector=0;room_name_waiting=0;room_pending_name[0]=0;
 room_defaults_loaded=0;network_mode=0;selector_offset=selector_total=0;selector_selected=-1;
}
static void selector_close(void){
 scene_opened=0;int kind=room_selector;input_box_stop(&selector_input);room_selector=0;
 if(room_network_entry()){if(network_mode==2){room_join_field=kind==4;input_box_start(room_join_field?&name_input:&network_input);}else if(network_mode==1 || network_mode==4)input_box_start(&name_input);
#ifdef MP_HALL
  else if(network_mode==5)input_box_start(&hall_input);
#endif
 }
 else if(!room_identity)input_box_start(&name_input);else input_box_start(&input);
 window_request_refresh();
}
static void selector_open(int kind){
 selector_profile_waiting=0;selector_profile_notice[0]=0;
 input_box_stop(&name_input);input_box_stop(&network_input);input_box_stop(&input);
 room_selector=kind;selector_offset=0;selector_hover=-1;selector_query[0]=0;selector_previous_query[0]=0;
 selector_selected=kind==1?network_adapter:kind==2?network_start:-1;selector_selected_label[0]=0;
#ifdef MP_HALL
 hall_transfer_wait=hall_transfer_done=0;input_box_stop(&hall_input);
 if(kind==5){hall_saves_asked=0;hall_local_asked=0;}   /* 내 저장소 read again (drawn: asked until the bridge takes it) */
 if(kind==5)selector_category=0;
 if(kind==6){
  encoding_from_utf8("",selector_query,sizeof(selector_query));memcpy(selector_query,player_name,sizeof(selector_query)<sizeof(player_name)?sizeof(selector_query)-1:sizeof(player_name));
  selector_query[sizeof(selector_query)-1]=0;
  char own[8];hall_own_country(own,sizeof(own));
  FILE *f=room_list_open(selector_file());if(f && own[0]){char line[ROOM_LIST_LINE];int index=0;while(room_list_line(f,line,sizeof(line))){if(!strncmp(line,own,2) && line[2]=='\t'){selector_selected=index;snprintf(selector_selected_label,sizeof(selector_selected_label),"%s",line);break;}index++;}}
  if(f)fclose(f);
 }
#endif
 if(kind==3 || kind==4){
  char current[256],line[ROOM_LIST_LINE];encoding_to_utf8(kind==3?network_ip:player_name,current,sizeof(current),0);
  FILE *f=room_list_open(selector_file());if(f){int index=0;while(room_list_line(f,line,sizeof(line))){if(!strcmp(line,current)){selector_selected=index;break;}index++;}fclose(f);}
 }
 if(kind==2){char current[ROOM_LIST_LINE];int count;network_choice("network-starts.txt",network_start,current,sizeof(current),&count);selector_category=selector_category_of(current);}
 if(kind==2 && selector_selected>=0){FILE *f=room_list_open(selector_file());if(f){char line[ROOM_LIST_LINE];int index=0,matched=0;while(room_list_line(f,line,sizeof(line))){if(index++==selector_selected)break;if(selector_category_of(line)==selector_category)matched++;}fclose(f);selector_offset=matched>=ROOM_LIST_ROWS?matched-ROOM_LIST_ROWS/2:0;}}
#ifdef MP_HALL
 if(kind==6)encoding_to_utf8(selector_query,selector_previous_query,sizeof(selector_previous_query),0);   /* the ID typed there is no search: keep the list where the own country is */
#endif
 if(selector_selected>=0 && kind!=2)selector_offset=selector_selected>=selector_view()?selector_selected-selector_view()/2:0;
 selector_scan();scrollbar_init(&selector_scroll,selector_offset,selector_total);input_box_start(&selector_input);window_request_refresh();
}
#include "multiplayer_scenario.inc"
static void selector_profile_poll(void){
 if(!selector_profile_waiting)return;
 char reply[2048];room_read("network-profile-result.txt",reply,sizeof(reply));
 size_t n=strlen(selector_profile_request);if(strncmp(reply,selector_profile_request,n) || reply[n]!='\n')return;
 snprintf(selector_profile_notice,sizeof(selector_profile_notice),"%s",!strcmp(reply+n+1,"ok")?"아이디 목록을 갱신했습니다.":reply+n+1);
 selector_profile_waiting=0;selector_selected=-1;selector_selected_label[0]=0;selector_scan();
}
#ifdef MP_HALL
/* Besides opening a room on it, a scenario of this PC can be sent to the hall's shared library and one of the library
 * can be fetched into this PC's own scenarios (user 2026-11-15). The label of that button, 0 when neither applies. */
/* 이어하기 (user 2026-11-16): the same place deletes the chosen save; a second click within 3 s does it, a save with a
 * recovery password asks for it first. */
static time_millis hall_delete_armed_at;static char hall_delete_armed_key[128];
static int hall_delete_armed(const char *key){return hall_delete_armed_key[0] && !strcmp(key,hall_delete_armed_key) && time_get_millis()-hall_delete_armed_at<3000;}
static void hall_delete_send(const char *key,const char *secret){
 char payload[768];snprintf(payload,sizeof(payload),"%s\n%s",key,secret);hall_delete_armed_key[0]=0;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(dir){char path[2048];snprintf(path,sizeof(path),"%s/hall-transfer.txt",dir);remove(path);}
 if(mp_client_command("hall-save-delete",payload)){hall_transfer_wait=1;hall_transfer_done=0;}
}
static const char *selector_transfer_label(void){
 if(room_selector!=5 || selector_selected<0)return 0;
 if(selector_category==2){char key[128];selector_field(selector_selected_label,0,key,sizeof(key));return hall_delete_armed(key)?"한 번 더":"저장 지우기";}
 char state[8];selector_field(selector_selected_label,4,state,sizeof(state));
 return state[0]=='L'?"서버에 올리기":state[0]=='0'?"내 PC로 받기":0;
}
#endif
static void selector_action(const generic_button *b){
 int id=b->parameter1;
#ifdef MP_HALL
 if(id==9){
  const char *label=selector_transfer_label();if(!label || hall_transfer_wait)return;
  char key[128],state[8];selector_field(selector_selected_label,0,key,sizeof(key));selector_field(selector_selected_label,4,state,sizeof(state));
  if(selector_category==2){   /* 저장 지우기 */
   int admin=0;
#ifdef MP_HALL_ADMIN
   admin=hall_admin_on();
#endif
   if(state[0]=='K' && !admin){hall_secret_open(2,selector_selected_label,"");return;}   /* its password first */
   if(!hall_delete_armed(key)){snprintf(hall_delete_armed_key,sizeof(hall_delete_armed_key),"%s",key);hall_delete_armed_at=time_get_millis();window_request_refresh();return;}
   hall_delete_send(key,"");return;
  }
  const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(dir){char path[2048];snprintf(path,sizeof(path),"%s/hall-transfer.txt",dir);remove(path);}
  if(mp_client_command(state[0]=='L'?"hall-upload":"hall-download",key)){hall_transfer_wait=1;hall_transfer_done=0;}
  return;
 }
#endif
 if((id==7 || id==8) && room_selector==4){
  if(selector_profile_waiting)return;
  char name[768];
  if(id==7)encoding_to_utf8(selector_query,name,sizeof(name),0);
  else{if(selector_selected<0)return;int count;network_choice(selector_file(),selector_selected,name,sizeof(name),&count);}
  if(!name[0]){snprintf(selector_profile_notice,sizeof(selector_profile_notice),"저장할 아이디를 위 입력칸에 적어 주세요.");return;}
  const char *verb=id==7?"network-save-name":"network-forget-name";
  const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(dir){char path[2048];snprintf(path,sizeof(path),"%s/network-profile-result.txt",dir);remove(path);}
  if(mp_client_command(verb,name)){snprintf(selector_profile_request,sizeof(selector_profile_request),"%s\n%s",verb,name);selector_profile_waiting=1;snprintf(selector_profile_notice,sizeof(selector_profile_notice),"아이디 목록을 갱신하고 있습니다.");}
  return;
 }
#ifdef MP_HALL
 if(id==60 && room_selector==5){   /* 개발자 모드: the saves of the other kind are not listed */
  if(hall_transfer_wait)return;
  hall_dev_mode=!hall_dev_mode;hall_transfer_done=0;
  if(selector_category==2){selector_selected=-1;selector_selected_label[0]=0;hall_saves_asked=mp_client_command("hall-saves",hall_dev_mode?"1":"");}
  selector_scan();window_request_refresh();return;
 }
 if(id>=30 && id<=32 && room_selector==5){
  selector_category=id-30;selector_offset=0;selector_selected=-1;selector_selected_label[0]=0;hall_transfer_done=0;
  if(selector_category==2)hall_saves_asked=mp_client_command("hall-saves",hall_dev_mode?"1":"");   /* not taken now: asked again when drawn */
  if(selector_category==1)hall_local_asked=0;
  selector_scan();window_request_refresh();return;
 }
#endif
 if(id>=30 && id<=32){selector_category=id-30;selector_offset=0;selector_selected=-1;selector_selected_label[0]=0;selector_scan();window_request_refresh();return;}
#ifdef MP_HALL
 if(id>=40 && id<40+selector_rows && room_selector==5){
  int row=id-40;if(hall_transfer_wait)return;hall_transfer_done=0;selector_selected=selector_indices[row];snprintf(selector_selected_label,sizeof(selector_selected_label),"%s",selector_labels[row]);scene_open_hall();return;
 }
#endif
 if(id>=40 && id<40+selector_rows && room_selector==2){
  int row=id-40;selector_selected=selector_indices[row];snprintf(selector_selected_label,sizeof(selector_selected_label),"%s",selector_labels[row]);scene_open();return;
 }
 if(id==5 && room_selector==2){if(mp_client_command("network-refresh-starts","")){selector_selected=-1;selector_selected_label[0]=0;notice[0]=0;window_request_refresh();}return;}
 if(id==4){selector_close();return;}
 if(id==3){
  if(selector_selected<0)return;
  char value[ROOM_LIST_LINE];int count;network_choice(selector_file(),selector_selected,value,sizeof(value),&count);
  if(selector_selected>=count || !value[0])return;
#ifdef MP_HALL
  if(room_selector==5 || room_selector==6){char typed[768];encoding_to_utf8(selector_query,typed,sizeof(typed),0);
   /* a room: its recovery password first (a new room sets one, a guarded save asks for it; user 2026-11-15) */
   if(room_selector==5){char state[8];selector_field(value,4,state,sizeof(state));
    if(selector_category!=2 || state[0]=='K'){hall_secret_open(selector_category==2,value,typed);return;}}
   if(!hall_selected(room_selector,value,typed,""))return;selector_close();return;}
#endif
  if(room_selector==1)network_adapter=selector_selected;
  else if(room_selector==2){if(strcmp(value,selector_selected_label)){selector_selected=-1;selector_scan();return;}network_start=selector_selected;}
  else if(room_selector==3)encoding_from_utf8(value,network_ip,sizeof(network_ip));
  else encoding_from_utf8(value,player_name,sizeof(player_name));
  selector_close();return;
 }
 if(id>=10 && id<10+selector_rows){int row=id-10;
#ifdef MP_HALL
  hall_transfer_done=0;
#endif
  selector_selected=selector_indices[row];snprintf(selector_selected_label,sizeof(selector_selected_label),"%s",selector_labels[row]);}
}
static generic_button selector_buttons[]={
 {56,400,112,28,selector_action,0,1},{176,400,112,28,selector_action,0,2},
 {472,400,112,28,selector_action,0,3},{352,400,112,28,selector_action,0,4},   /* select right, cancel left */
 {56,SELECTOR_ROW_Y+0*SELECTOR_ROW_STEP,528,24,selector_action,0,10},{56,SELECTOR_ROW_Y+1*SELECTOR_ROW_STEP,528,24,selector_action,0,11},
 {56,SELECTOR_ROW_Y+2*SELECTOR_ROW_STEP,528,24,selector_action,0,12},{56,SELECTOR_ROW_Y+3*SELECTOR_ROW_STEP,528,24,selector_action,0,13},
 {56,SELECTOR_ROW_Y+4*SELECTOR_ROW_STEP,528,24,selector_action,0,14},{56,SELECTOR_ROW_Y+5*SELECTOR_ROW_STEP,528,24,selector_action,0,15},
 {56,SELECTOR_ROW_Y+6*SELECTOR_ROW_STEP,528,24,selector_action,0,16},{56,SELECTOR_ROW_Y+7*SELECTOR_ROW_STEP,528,24,selector_action,0,17}
};
static generic_button selector_refresh_button={56,400,112,28,selector_action,0,5};
static generic_button selector_categories[]={
 {56,126,172,20,selector_action,0,30},{238,126,172,20,selector_action,0,31},
 {420,126,172,20,selector_action,0,32}};
static generic_button selector_details[ROOM_LIST_ROWS]={
 {472,156,72,23,selector_action,0,40},{472,180,72,23,selector_action,0,41},
 {472,204,72,23,selector_action,0,42},{472,228,72,23,selector_action,0,43},
 {472,252,72,23,selector_action,0,44},{472,276,72,23,selector_action,0,45},
 {472,300,72,23,selector_action,0,46},{472,324,72,23,selector_action,0,47}
};
#ifdef MP_HALL
static generic_button selector_transfer_button={56,400,112,28,selector_action,0,9};
/* 개발자 모드 (user 2026-11-17): a developer room; its scenario stays out of the shared library, its saves are listed
 * under 이어하기 only while this is ticked (game_hall.py). */
static generic_button selector_dev_button={56,432,528,22,selector_action,0,60};
/* The room window (user 2026-11-16): each row's 상세보기 stands where the sender's name was (the line under the list names
 * the sender); the saves' player IDs moved to that line the same way. Placed for the row width of the moment. */
static void selector_hall_details(int row_w){
 int when_w=selector_category?0:92,x=56+row_w-48-48-when_w-88-8+8;
 (void)when_w;x=56+row_w-72-8;   /* two-line rows: at the right end of the entry */
 for(int i=0;i<ROOM_LIST_ROWS;i++){selector_details[i].x=x;selector_details[i].y=SELECTOR_ROW_Y+i*selector_step()+(selector_step()-24)/2;selector_details[i].width=72;selector_details[i].height=24;}
}
#endif
static void selector_lan_details(void){for(int i=0;i<ROOM_LIST_ROWS;i++){selector_details[i].x=472;selector_details[i].y=156+i*selector_step()+(selector_step()-24)/2;selector_details[i].width=72;selector_details[i].height=24;}}
static generic_button selector_profile_buttons[]={
 {56,400,112,28,selector_action,0,7},{176,400,112,28,selector_action,0,8}};
static void selector_draw(void){
 if(scene_opened){scene_draw();return;}
#ifdef MP_HALL
 if(room_selector==7){room_selector=5;selector_draw();room_selector=7;hall_secret_draw();return;}   /* over the room window */
#endif
#ifdef MP_HALL_ADMIN
 if(room_selector==8){hall_admin_draw();return;}   /* the administrator's login (Korean edition) */
 if(room_selector==9){hall_admin_panel_draw();return;}   /* the administrator's window */
#endif
#ifdef MP_HALL
 if(room_selector==10){hall_board_draw();return;}   /* 알림판 (user 2026-11-17) */
#ifdef MP_SPECTATE
 if(room_selector==11){spectate_draw();return;}   /* 관전 (user 2026-11-17) */
#endif
#endif
 selector_profile_poll();selector_scan();outer_panel_draw(SELECTOR_PANEL_X,SELECTOR_PANEL_Y,SELECTOR_PANEL_W,SELECTOR_PANEL_H);
 draw_utf8(room_selector==1?"네트워크 선택":room_selector==2?"시나리오 / 공동 저장 선택":room_selector==3?"최근 접속한 IP":room_selector==5?"방 만들기":room_selector==6?"국가와 아이디":"저장한 아이디",56,54,536,FONT_LARGE_BLACK);
 draw_utf8(room_selector==4 || room_selector==6?"아이디":room_selector==5?"방 제목":"검색",56,96,64,FONT_NORMAL_BLACK);input_box_draw(&selector_input);
#ifdef MP_HALL
 if(room_selector==5 && !selector_query[0]){char name[256],shown[300];encoding_to_utf8(player_name,name,sizeof(name),0);snprintf(shown,sizeof(shown),"%s의 방 (비워 두면)",name);mp_i18n_suspend(1);draw_utf8(shown,selector_input.x+16,selector_input.y+10,300,FONT_SMALL_PLAIN);mp_i18n_suspend(0);}
#endif
 if(room_selector==4){draw_utf8("입력한 이름으로 검색하거나 아래 저장 버튼으로 등록하세요.",56,126,536,FONT_SMALL_PLAIN);const char *labels[]={"아이디 저장","아이디 삭제"};for(int i=0;i<2;i++){generic_button *b=&selector_profile_buttons[i];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(labels[i],b->x+8,b->y+(b->height-12)/2,b->width-16,FONT_NORMAL_BLACK);}}
 inner_panel_draw(48,152,34,13);
#ifdef MP_HALL
 if(room_selector==5){const char *names[]={"서버 저장소","내 저장소","이어하기"};
 for(int i=0;i<3;i++){generic_button *b=&selector_categories[i];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(names[i],b->x+7,b->y+(b->height-12)/2,b->width-14,selector_category==i?FONT_NORMAL_RED:FONT_NORMAL_BLACK);}
 if(selector_category<2 && !hall_local_asked)hall_local_asked=mp_client_command("hall-local","");
 if(selector_category==2){char state[16];room_read("hall-saves.txt",state,sizeof(state));
  if(!hall_saves_asked)hall_saves_asked=mp_client_command("hall-saves",hall_dev_mode?"1":"");
  if(!strncmp(state,"wait",4) || !state[0])draw_utf8("서버에서 이어할 저장을 찾고 있습니다.",64,160,500,FONT_NORMAL_WHITE);
  else if(!strncmp(state,"none",4))draw_utf8("이 서버에 이어할 수 있는 저장이 없습니다.",64,160,500,FONT_NORMAL_WHITE);
  else if(!strncmp(state,"error",5))draw_utf8("저장 목록을 받지 못했습니다. 탭을 다시 눌러 주세요.",64,160,500,FONT_NORMAL_RED);}}
#endif
 if(room_selector==2){const char *names[]={"기본 시나리오","내 시나리오","이어하기"};
 for(int i=0;i<3;i++){generic_button *b=&selector_categories[i];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(names[i],b->x+7,b->y+(b->height-12)/2,b->width-14,selector_category==i?FONT_NORMAL_RED:FONT_NORMAL_BLACK);}}
 selector_sync_scroll();scrollbar_draw(&selector_scroll);
 int row_w=room_selector==2?408:selector_total>selector_view()?488:528,step=selector_step();
 int band_w=room_selector==2?492:row_w;   /* the highlight and the rules reach under 상세보기 (472+72) on the LAN list too */
 for(int i=0;i<ROOM_LIST_ROWS;i++){selector_buttons[4+i].y=SELECTOR_ROW_Y+i*step;selector_buttons[4+i].height=step;}

 for(int row=0;row<selector_rows;row++){
  int selected=selector_selected==selector_indices[row],y=SELECTOR_ROW_Y+row*step;
  selector_buttons[4+row].width=row_w;
  if(selected)large_label_draw_custom_size(56,y,band_w,step);
  else if(row && selector_tall())graphics_draw_line(60,56+band_w-4,y,y,0xff6e5f4a);   /* a rule between entries */
  font_t title_font=selected?FONT_NORMAL_BLACK:selector_hover==row?FONT_NORMAL_GREEN:FONT_NORMAL_WHITE;
  color_t soft=selected?0:0xffe0d4bc;
  int text_x=64;
#ifdef MP_HALL
  if(room_selector==6){char code[8];snprintf(code,sizeof(code),"%.2s",selector_labels[row]);hall_flag_draw(code,66,y+4);text_x=96;}
  if(room_selector==5){   /* the title; under it who sent it · the date · seats · 받음/올림/잠금; 상세보기 at the right */
   char seats[16],by[128],state[8],key[32],when[64],second[512];
   selector_field(selector_labels[row],1,seats,sizeof(seats));selector_field(selector_labels[row],3,by,sizeof(by));selector_field(selector_labels[row],4,state,sizeof(state));selector_field(selector_labels[row],0,key,sizeof(key));selector_field(selector_labels[row],5,when,sizeof(when));
   if(when[0]>='0' && when[0]<='9')when[10]=0;   /* the date without the time */
   const char *mark=state[0]=='K'?"잠금":state[0]=='U'?"올림":(state[0]=='1' && strncmp(key,"built-in:",9))?"받음":"";
   char people[64];snprintf(people,sizeof(people),"%d인",atoi(seats));
   int at=snprintf(second,sizeof(second),"%s",by);
   if(when[0] && at<(int)sizeof(second))at+=snprintf(second+at,sizeof(second)-at,"%s%s",at?" · ":"",when);
   if(at<(int)sizeof(second))at+=snprintf(second+at,sizeof(second)-at,"%s%s",at?" · ":"",mp_i18n_translate(people));
   if(mark[0] && at<(int)sizeof(second))snprintf(second+at,sizeof(second)-at," · %s",mp_i18n_translate(mark));
   int text_w=row_w-16-72-16;
   hall_plain(selector_display_label(selector_labels[row]),text_x,y+6,text_w,title_font,0);
   hall_plain(second,text_x,y+27,text_w,FONT_SMALL_PLAIN,soft);
   selector_hall_details(row_w);{generic_button *b=&selector_details[row];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center("상세보기",b->x+4,b->y+(b->height-12)/2,b->width-8,FONT_NORMAL_BLACK);}
   continue;
  }
#endif
  if(room_selector==2){   /* the LAN list: the title, the rest of the line (players, date ...) under it */
   /* scenarios: "title (4인 / 협동)" -> the title; "4인 · 협동". Saves: "[최신]when · title · date #id" -> the title; the rest */
   char first[ROOM_LIST_LINE],second[ROOM_LIST_LINE],*rest=0;snprintf(first,sizeof(first),"%s",selector_display_label(selector_labels[row]));second[0]=0;
   if(selector_category==2){
    /* " · " is four bytes (the dot is two): counted, not written as 3 - the title kept a blank in front and found no
     * translation (user 2026-11-17). The title is the last-but-date part: "when · title [· title's own parts] · date #id". */
    size_t dot=strlen(" · ");char *a=strstr(first," · "),*b=0;
    for(char *q=a?strstr(a+dot," · "):0;q;q=strstr(q+dot," · ")){   /* the date part starts 기원전/서기; a title may hold " · " itself */
     const char *era[]={"기원전","서기"};int date=0;
     for(int k=0;k<2;k++){size_t n=strlen(era[k]);if(!strncmp(q+dot,era[k],n) && q[dot+n]==' ')date=1;}
     if(date){b=q;break;}
     if(!b)b=q;
    }
    if(a && b){*b=0;snprintf(second,sizeof(second),"%.*s · %s",(int)(a-first),first,b+dot);memmove(first,a+dot,strlen(a+dot)+1);rest=second;}
   }else{
    char *open=strrchr(first,'(');size_t n=strlen(first);
    if(open && open>first+1 && open[-1]==' ' && n && first[n-1]==')'){
     first[n-1]=0;int k=0;for(const char *q=open+1;*q && k<(int)sizeof(second)-4;q++){if(q[0]==' ' && q[1]=='/' && q[2]==' '){memcpy(second+k," · ",strlen(" · "));k+=strlen(" · ");q+=2;}else second[k++]=*q;}
     second[k]=0;open[-1]=0;rest=second;
    }
   }
   int text_w=row_w-16;   /* 상세보기 stands right of the LAN rows */
   draw_utf8(first,text_x,rest?y+6:y+16,text_w,title_font);
   if(rest){
    /* each part between " · " in the reader's language by itself ("6인", "자유 건설", "기원전 350년 1월 #3"; user
     * 2026-11-17: the line stayed Korean in the Global edition), never the whole line: a pattern of one part must
     * not meet another part */
    char shown[ROOM_LIST_LINE*2];size_t o=0;shown[0]=0;
    for(char *part=rest;part && o+4<sizeof(shown);){
     char *next=strstr(part," · ");if(next)*next=0;
     o+=snprintf(shown+o,sizeof(shown)-o,"%s%s",o?" · ":"",mp_i18n_translate(part));
     if(next){*next=' ';part=next+strlen(" · ");}else part=0;
    }
    mp_i18n_suspend(1);uint8_t e[ROOM_LIST_LINE*2];encoding_from_utf8(shown,e,sizeof(e));text_draw_ellipsized(e,text_x,y+27,text_w,FONT_SMALL_PLAIN,soft);mp_i18n_suspend(0);}
   selector_lan_details();generic_button *b=&selector_details[row];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center("상세보기",b->x+4,b->y+(b->height-12)/2,b->width-8,FONT_NORMAL_BLACK);
   continue;
  }
  draw_utf8(selector_display_label(selector_labels[row]),text_x,y+5,row_w-16-(text_x-64),title_font);
 }
#ifdef MP_HALL
 if(!selector_total && room_selector==5 && selector_category<2)draw_utf8(selector_category?"이 PC에 시나리오가 없습니다. 에디터로 만들거나 서버 저장소에서 받으세요.":"서버 저장소가 비어 있습니다. 내 저장소에서 올려 주세요.",64,156,512,FONT_NORMAL_WHITE);
 else
#endif
 if(!selector_total && room_selector!=5)draw_utf8(room_selector==6?"선택할 항목이 없습니다.":selector_query[0]?"검색 결과가 없습니다.":room_selector==3?"아직 접속한 IP가 없습니다. 직접 입력해 주세요.":room_selector==4?"저장한 아이디가 없습니다. 새 아이디를 입력해 주세요.":"선택할 항목이 없습니다.",64,156,512,FONT_NORMAL_WHITE);
 /* Lists scroll under the original scrollbar alone: no page buttons, counters or banners explaining it. */
#ifdef MP_HALL
 if(room_selector==5){   /* sending or fetching: what the bridge says, then the result until the next pick */
  char transfer[512];room_read("hall-transfer.txt",transfer,sizeof(transfer));transfer[strcspn(transfer,"\r\n")]=0;
  if(hall_transfer_wait && transfer[0]){hall_transfer_wait=0;hall_transfer_done=1;if(selector_category==2 && transfer[0]=='1'){selector_selected=-1;selector_selected_label[0]=0;}}   /* a deleted save is off the list */
  const char *label=selector_transfer_label();
  if(label){generic_button *b=&selector_transfer_button;large_label_draw_custom_size(b->x,b->y,b->width,b->height);
   if(hall_transfer_wait)mp_button_text(label,b->x+8,b->y+(b->height-12)/2,b->width-16,2);else gift_center(label,b->x+8,b->y+(b->height-12)/2,b->width-16,FONT_NORMAL_BLACK);}
#ifdef MP_HALL_ADMIN
  hall_admin_selector_draw();   /* the administrator: 서버에서 내리기 */
#endif
  {generic_button *b=&selector_dev_button;   /* 개발자 모드: the original options checkbox, then its line */
   button_border_draw(b->x,b->y+1,20,20,0);if(hall_dev_mode)draw_utf8("x",b->x+6,b->y+4,12,FONT_NORMAL_BLACK);
   draw_utf8(hall_dev_mode?"시나리오 제작자 모드: 시험용 방 (공용 보관함에 올리지 않음)":"시나리오 제작자 모드",b->x+28,b->y+5,b->width-28,hall_dev_mode?FONT_NORMAL_RED:FONT_NORMAL_BLACK);}
  if(hall_transfer_wait){char status[512];room_read("hall-status.txt",status,sizeof(status));status[strcspn(status,"\r\n")]=0;draw_utf8(status[0]?status:"서버와 주고받는 중입니다.",56,370,400,FONT_SMALL_PLAIN);room_busy_draw(7,1,424,370,168);}
  else{room_busy_draw(7,0,0,0,0);
   int line_w=536;
   if(hall_transfer_done && transfer[0] && transfer[1]==' ')draw_utf8(transfer+2,56,370,line_w,transfer[0]=='0'?FONT_NORMAL_RED:FONT_SMALL_PLAIN);
   else if(selector_selected>=0){   /* the chosen one in full: title, who sent it and when (a save: its players' IDs and game date) */
    char line[768],by[128],when[64];selector_field(selector_selected_label,3,by,sizeof(by));selector_field(selector_selected_label,5,when,sizeof(when));
    snprintf(line,sizeof(line),"%s%s%s%s%s",selector_display_label(selector_selected_label),by[0]?" · ":"",by,when[0]?" · ":"",when);draw_utf8(line,56,370,line_w,FONT_SMALL_PLAIN);}
   else draw_utf8(selector_selected>=0?selector_display_label(selector_selected_label):selector_category==2?(hall_dev_mode?"제작자 방의 저장만 보입니다. 고른 뒤 만들기를 누르세요.":"이어할 저장을 고른 뒤 만들기를 누르세요."):selector_category?(hall_dev_mode?"제작자 방은 시나리오를 공용 보관함에 올리지 않고 이 방에서만 씁니다.":"서버에 올리면 모두가 서버 저장소에서 고를 수 있습니다."):"시나리오를 고른 뒤 만들기를 누르세요.",56,370,line_w,FONT_SMALL_PLAIN);}
 }
 else
#endif
 if(room_selector!=2)
 draw_utf8(room_selector==4 && selector_profile_notice[0]?selector_profile_notice:selector_selected>=0?selector_display_label(selector_selected_label):"항목을 고른 뒤 선택을 누르세요.",56,370,536,FONT_SMALL_PLAIN);
 const char *labels[]={room_selector==5?"만들기":"선택","취소"};
 for(int i=2;i<4;i++){generic_button *b=&selector_buttons[i];int enabled=i==2?selector_selected>=0:1;
  large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(labels[i-2],b->x+8,b->y+(b->height-12)/2,b->width-16,enabled?FONT_NORMAL_BLACK:FONT_SMALL_PLAIN);}
 if(room_selector==2){large_label_draw_custom_size(56,400,112,28);gift_center("새로고침",64,408,96,FONT_NORMAL_BLACK);}
 if(room_selector==2){draw_utf8("항목 클릭: 선택 · 상세보기: 지도와 설명",232,440,360,FONT_SMALL_PLAIN);if(selector_category==2)draw_utf8("최신·과거 공동 저장",56,440,176,FONT_SMALL_PLAIN);}
}
static void selector_handle(const mouse *m,const hotkeys *h){
 if(scene_opened){scene_handle(m,h);return;}
#ifdef MP_HALL
 if(room_selector==7){hall_secret_handle(m,h);return;}
#endif
#ifdef MP_HALL_ADMIN
 if(room_selector==8){hall_admin_handle(m,h);return;}
 if(room_selector==9){hall_admin_panel_handle(m,h);return;}
 if(room_selector==5 && hall_admin_selector_handle(m))return;   /* 서버에서 내리기 */
#endif
#ifdef MP_HALL
 if(room_selector==10){hall_board_handle(m,h);return;}
#ifdef MP_SPECTATE
 if(room_selector==11){spectate_handle(m,h);return;}
#endif
#endif
 if(h->close_pressed){selector_close();return;}
 selector_profile_poll();input_box_handle_mouse(m,&selector_input);selector_scan();selector_hover=-1;
 for(int i=0;i<selector_rows;i++){generic_button *b=&selector_buttons[4+i];if(m->x>=b->x && m->x<b->x+b->width && m->y>=b->y && m->y<b->y+b->height)selector_hover=i;}
 selector_sync_scroll();
 if(selector_scroll.is_dragging_scrollbar_dot || (m->x>=48 && m->x<592 && m->y>=152 && m->y<360)){if(scrollbar_handle_mouse(&selector_scroll,m,0) || m->scrolled){window_request_refresh();return;}}
 if(input_box_is_accepted()){
  /* Enter after searching chooses a unique result; ambiguous searches stay open. The hall's inputs are no search. */
  if(room_selector!=5 && room_selector!=6 && selector_total==1 && selector_rows==1){selector_selected=selector_indices[0];snprintf(selector_selected_label,sizeof(selector_selected_label),"%s",selector_labels[0]);generic_button b={0};b.parameter1=3;selector_action(&b);return;}
  input_box_start(&selector_input);
 }
 if(room_selector==4 && generic_buttons_handle_mouse(m,0,0,selector_profile_buttons,2,&focus))return;
#ifdef MP_HALL
 if(room_selector==5 && !hall_transfer_wait){selector_hall_details(selector_total>selector_view()?488:528);if(generic_buttons_handle_mouse(m,0,0,selector_details,selector_rows,&focus))return;}
 if(room_selector==5 && selector_transfer_label() && generic_buttons_handle_mouse(m,0,0,&selector_transfer_button,1,&focus))return;
 if(room_selector==5 && generic_buttons_handle_mouse(m,0,0,selector_categories,3,&focus))return;
 if(room_selector==5 && generic_buttons_handle_mouse(m,0,0,&selector_dev_button,1,&focus))return;
#endif
 if(room_selector==2){
 if(generic_buttons_handle_mouse(m,0,0,selector_categories,3,&focus))return;
 selector_lan_details();if(generic_buttons_handle_mouse(m,0,0,selector_details,selector_rows,&focus))return;
 if(generic_buttons_handle_mouse(m,0,0,&selector_refresh_button,1,&focus))return;}

 generic_buttons_handle_mouse(m,0,0,selector_buttons+2,2+selector_rows,&focus);window_request_refresh();
}
static void room_poll_name(void){
 if(!room_name_waiting)return;
 if(time_get_millis()-room_name_started>=10000){room_name_waiting=0;strcpy(notice,"아이디 저장 응답이 없습니다. 다시 입장해 주세요.");input_box_start(&name_input);return;}
 char result[1024];room_read("network-name-result.txt",result,sizeof(result));
 char *state=strchr(result,'\n');if(!state)return;*state++=0;
 result[strcspn(result,"\r")]=0;
 if(strcmp(result,room_pending_name))return;
 char *value=strchr(state,'\n');if(!value)return;*value++=0;
 state[strcspn(state,"\r")]=0;value[strcspn(value,"\r\n")]=0;
 room_name_waiting=0;
 if(!strcmp(state,"ok")){
  encoding_from_utf8(value,player_name,sizeof(player_name));room_identity=1;lobby_name_active=0;notice[0]=0;input_box_start(&input);
 }else{snprintf(notice,sizeof(notice),"%s",value);input_box_start(&name_input);}
}
