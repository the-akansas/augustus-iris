/* Race for the Throne, in the city view (bridge files from throne_events.public_status via game_bridge.py).
 * throne-events.txt: "id<TAB>title<TAB>body" per anonymous coup notice. Each becomes one original custom message with a
 *   confirm-and-close popup, keyed "mpthrone:<id>": a resend, a reconnect or a reloaded save never shows it twice, and
 *   closing it only closes it (nothing is sent back, nothing is charged).
 * Confirmed plan 2026-11-14 (docs/황위-쟁탈전-확정안-20261114.md), all from throne_client.py, "key<TAB>value..." lines:
 *   throne-box.txt     the box top right of the city view: closed = icon + "평화" or the player's paranoia; a click
 *                      opens it: my coup stages, the leading plot (squares, drawn, not letters), the empire's mood,
 *                      and the buttons (peace: 끌어내리기; after: 쿠데타 지원, 충성선물). A note under it for a while.
 *                      Also the march card ("황제군이 오고 있습니다", 공물 바치기) while the legions are on their way.
 *   throne-dialog.txt  the open dialog (coup, gift, tribute): rows, the amount with the trade window's controls
 *                      ([-] value [+], +1,000 +5,000 +10,000, 초기화), the confirm button.
 *   throne-score.txt   the scoreboard at the end (everyone, every value).
 *   A click only sends "throne" + id + the treasury this game shows (a refusal hint; the host and the city's engine
 *   decide the debit). Quotes and results are prepared by the bridge.
 *   The amount works as in the trade window's money form (user 2026-11-14: every [-] [+] click waited for the room
 *   and lagged): [-] [+], the quick keys and reset change it here at once, a click on the number opens the number
 *   pad, and what follows from it (success chance, paranoia after a gift, the charge) is calculated here with the
 *   rules' own formulas from the "calc" line (throne_rules.chance_bp, gift_plan). Nothing goes to the room until the
 *   confirm button: "go" carries the amount, the host checks everything again before it charges.
 *   Texts never use arrows, middle dots or other signs that are missing from some languages' fonts. */
#include "scenario/custom_messages.h"
#include "core/mp_i18n.h"
#include "city/message.h"
#include "window/numeric_input.h"
/* One bridge file of "id<TAB>title<TAB>body" lines -> one confirm window per id, once (uid "<prefix><id>" is kept in
 * the save). Returns 1 when a window was posted, so only one opens per frame. */
static int bridge_notices_post(const char *file,const char *prefix){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir || !window_is(WINDOW_CITY))return 0;
 char path[2048];static char line[16384];snprintf(path,sizeof(path),"%s/%s",dir,file);FILE *f=fopen(path,"rb");if(!f)return 0;
 int posted=0;
 for(int n=0;n<64 && fgets(line,sizeof(line),f);n++){
  line[strcspn(line,"\r\n")]=0;char *title=strchr(line,'\t');if(!title)continue;*title++=0;char *body=strchr(title,'\t');if(!body)continue;*body++=0;
  if(strlen(line)!=32 || strspn(line,"0123456789abcdef")!=32)continue;
  char uid[64];snprintf(uid,sizeof(uid),"%s%s",prefix,line);if(custom_messages_get_id_by_uid((uint8_t*)uid))continue;
  custom_message_t *m=custom_messages_create((uint8_t*)uid);if(!m)break;
  m->title=message_media_text_blob_add_encoded(title);m->subtitle=message_media_text_blob_add_encoded(title);m->display_text=message_media_text_blob_add_encoded(body);
  city_message_post(1,MESSAGE_CUSTOM_MESSAGE,m->id,0);posted=1;break;   /* one popup at a time; the next waits for the next frame */
 }
 fclose(f);return posted;
}
/* start-message.txt: the scenario author's start message for this player (scenario_briefing.start_message_file), shown
 * first; then the anonymous coup notices. */
static void throne_notices_post(void){
 if(bridge_notices_post("start-message.txt","mpstart:"))return;
 bridge_notices_post("throne-events.txt","mpthrone:");
}
#define TH_TEXT 512
typedef struct{int x,y,w,h,on;char id[16];}th_hit;
static th_hit th_hits[32];static int th_hit_count;
#define TH_HITS ((int)(sizeof(th_hits)/sizeof(th_hits[0])))
static int th_dev_rect[4];   /* the maker panel when open (multiplayer_dev.inc), apart from its button (th_test_rect) */
static void side_close(void);   /* multiplayer_sidetabs.inc: the maker panel and a side tab are never open together */
static int window_multiplayer_overlay_at(int x,int y);
static struct{
 int state;      /* 0 off, 1 restoring, 2 peace, 3 active, 4 ended */
 int paranoia,mine,leading,stages,coup,gift,march,march_on;
 char mood[TH_TEXT],note[TH_TEXT],march_title[TH_TEXT],march_wait[TH_TEXT];
 /* 황제의 순행 (state 5; progress_client.box_file): the closed label, the title, text rows, the favour table, the bid button */
 int pg_rows,pg_favors,pg_bid,pg_me[8],pg_win[8];
 char pg_small[2][64],pg_title[TH_TEXT],pg_row[8][2][TH_TEXT],pg_favor[8][2][96];
}th_box;
static struct{
 int open,rows,lows,has_amount,has_bar,bar_value,go_on,amount_value,amount_min,amount_max;
 int calc,calc_v[7],calc_ready;char calc_reason[TH_TEXT];   /* calc: 1 coup, 2 gift (see th_local) */
 char kind[16],title[TH_TEXT],subtitle[TH_TEXT],desc[TH_TEXT],small[TH_TEXT],hint[TH_TEXT],message[TH_TEXT],go[TH_TEXT];
 char row[8][2][TH_TEXT],low[6][2][TH_TEXT],amount[2][TH_TEXT],bar[2][TH_TEXT];
}th_dialog;
static struct{
 int rows,foots,dismissed;char title[TH_TEXT],subtitle[TH_TEXT],foot[3][TH_TEXT],row[8][10][96];char stamp[64];
}th_score;
static int th_expanded,th_box_rect[4],th_dialog_rect[4],th_score_rect[4],th_card_rect[4];
static unsigned th_read_at;
#define TH_LOCAL_MS 6000
static char th_local_kind[16];static unsigned th_local_at;   /* a dialog opened at the click (th_read) */
static char th_local_note[TH_TEXT];static unsigned th_local_note_at;   /* a refusal shown at the click */
/* The amount being edited (see the header). -1: no dialog with an amount. */
static struct{int value;char kind[16];}th_amount={-1};
static void th_amount_set(int v){
 if(v<th_dialog.amount_min)v=th_dialog.amount_min;if(v>th_dialog.amount_max)v=th_dialog.amount_max;th_amount.value=v;
}
static void th_amount_typed(int v){th_amount_set(v);}
static void th_amount_follow(void){   /* after reading the dialog file: a new dialog starts from its amount */
 if(!th_dialog.open || !th_dialog.has_amount){th_amount.value=-1;th_amount.kind[0]=0;return;}
 if(th_amount.value<0 || strcmp(th_amount.kind,th_dialog.kind)){snprintf(th_amount.kind,sizeof(th_amount.kind),"%s",th_dialog.kind);th_amount.value=th_dialog.amount_value;}
 th_amount_set(th_amount.value);   /* bounds may have moved (a new minimum after a month) */
}
static void th_commas(int v,char *out,size_t size){   /* 12,500 */
 char digits[16];snprintf(digits,sizeof(digits),"%d",v<0?0:v);int n=(int)strlen(digits),o=0;char text[32];
 for(int i=0;i<n;i++){if(i && (n-i)%3==0)text[o++]=',';text[o++]=digits[i];}text[o]=0;snprintf(out,size,"%s",text);
}
static void th_dn(int v,char *out,size_t size){char n[32];th_commas(v,n,sizeof(n));snprintf(out,size,"%s Dn",n);}   /* 12,500 Dn */
/* What the amount does, here (the same formulas as throne_rules.py; the host checks again before it charges).
 * coup: calc_v = minimum, base chance, cap (basis points), next minimum after a failure, highest spend.
 * gift: calc_v = paranoia, stage floor, gift floor, price per point down to the floor, price below it, highest spend.
 * Fills the rows below the amount and the reason it cannot be sent; returns 1 when it can. */
static int th_local(int amount,char low[3][2][TH_TEXT],int *lows,char *reason){
 int *v=th_dialog.calc_v,funds=(int)city_finance_treasury(),highest=th_dialog.calc==1?v[4]:v[5];char n[32],t[TH_TEXT];
 *lows=0;reason[0]=0;
 if(th_dialog.calc==3){   /* a sealed bid (황제의 순행): calc_v = lowest bid, highest bid. Checked here; the room checks again. */
  if(!th_dialog.calc_ready){snprintf(reason,TH_TEXT,"%s",th_dialog.calc_reason);return 0;}
  if(amount<v[0]){th_commas(v[0],n,sizeof(n));snprintf(reason,TH_TEXT,"최저 입찰가는 %s Dn입니다.",n);return 0;}
  if(amount>v[1]){th_commas(v[1],n,sizeof(n));snprintf(reason,TH_TEXT,"한 번에 %s Dn까지 낼 수 있습니다.",n);return 0;}
  if(amount>funds){th_commas(funds,n,sizeof(n));snprintf(reason,TH_TEXT,"보유 자금(%s Dn)보다 큰 금액입니다.",n);return 0;}
  return 1;
 }
 if(th_dialog.calc==1){
  int m=v[0],base=v[1],cap=v[2],chance=amount>=m && amount>0?base+(int)(((long long)(cap-base)*(amount-m))/amount):0;
  /* the cap beside the chance: more money never passes it, and people look only at this row (user 2026-11-14) */
  char capped[32];snprintf(capped,sizeof(capped),"%d%%",cap/100);if(cap%100)snprintf(capped,sizeof(capped),"%d.%02d%%",cap/100,cap%100);
  snprintf(low[0][0],TH_TEXT,"예상 성공률");if(amount>=m && amount>0)snprintf(low[0][1],TH_TEXT,"%d.%02d%% (상한 %s)",chance/100,chance%100,capped);else snprintf(low[0][1],TH_TEXT,"- (상한 %s)",capped);
  snprintf(low[1][0],TH_TEXT,"실패 시 다음 최소 지원금");th_dn(v[3],low[1][1],TH_TEXT);*lows=2;
 }else{
  int paranoia=v[0],floor=v[1],bottom=v[2],price=v[3],below=v[4],value=paranoia,charge=0;
  while(value>bottom){int p=value>floor?price:below;if(charge+p>amount)break;charge+=p;value--;}
  int points=paranoia-value,next=value>bottom?(value>floor?price:below):0;
  snprintf(low[0][0],TH_TEXT,"예상 감소");if(points)snprintf(low[0][1],TH_TEXT,"-%d",points);else snprintf(low[0][1],TH_TEXT,"-");
  /* the gift floor beside the result: gifts never go below it, and people look only at this row (user 2026-11-14) */
  snprintf(low[1][0],TH_TEXT,"선물 후 편집증");snprintf(low[1][1],TH_TEXT,"%d (최저 %d)",value,bottom);
  snprintf(low[2][0],TH_TEXT,"실제 차감");th_dn(charge,low[2][1],TH_TEXT);*lows=3;
  if(!th_dialog.calc_ready){snprintf(reason,TH_TEXT,"%s",th_dialog.calc_reason);return 0;}
  if(amount<1){snprintf(reason,TH_TEXT,"금액을 정해 주세요.");return 0;}
  if(amount>highest){th_commas(highest,n,sizeof(n));snprintf(reason,TH_TEXT,"한 번에 %s Dn까지 낼 수 있습니다.",n);return 0;}
  if(amount>funds){th_commas(funds,n,sizeof(n));snprintf(reason,TH_TEXT,"보유 자금(%s Dn)보다 큰 금액입니다.",n);return 0;}
  if(!points){if(paranoia<=bottom)snprintf(reason,TH_TEXT,"편집증이 이미 선물로 낮출 수 있는 최저치입니다.");else{th_commas(next,n,sizeof(n));snprintf(t,TH_TEXT,"1점을 낮추려면 %s Dn이 필요합니다.",n);snprintf(reason,TH_TEXT,"%s",t);}return 0;}
  return 1;
 }
 if(!th_dialog.calc_ready){snprintf(reason,TH_TEXT,"%s",th_dialog.calc_reason);return 0;}
 if(amount>highest){th_commas(highest,n,sizeof(n));snprintf(reason,TH_TEXT,"한 번에 %s Dn까지 낼 수 있습니다.",n);return 0;}
 if(amount>funds){th_commas(funds,n,sizeof(n));snprintf(reason,TH_TEXT,"보유 자금(%s Dn)보다 큰 금액입니다.",n);return 0;}
 return 1;
}

/* One "a<TAB>b<TAB>c" line into fields (in place). Returns the number of fields. */
static int th_split(char *line,char **f,int max){
 int n=0;line[strcspn(line,"\r\n")]=0;
 for(char *p=line;n<max;){f[n++]=p;p=strchr(p,'\t');if(!p)break;*p++=0;}
 return n;
}
static FILE *th_open(const char *name){const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;char path[2048];snprintf(path,sizeof(path),"%s/%s",dir,name);return fopen(path,"rb");}
static void th_copy(char *to,const char *from){snprintf(to,TH_TEXT,"%s",from);}
static void th_parse_dialog(FILE *file,char *line,char **f){   /* line: 4096 bytes, f: 12 fields */
 while(fgets(line,4096,file)){
  int n=th_split(line,f,12);if(n<2)continue;
  if(!strcmp(f[0],"kind")){snprintf(th_dialog.kind,sizeof(th_dialog.kind),"%s",f[1]);th_dialog.open=1;}
  else if(!strcmp(f[0],"title"))th_copy(th_dialog.title,f[1]);else if(!strcmp(f[0],"subtitle"))th_copy(th_dialog.subtitle,f[1]);
  else if(!strcmp(f[0],"desc"))th_copy(th_dialog.desc,f[1]);else if(!strcmp(f[0],"small"))th_copy(th_dialog.small,f[1]);
  else if(!strcmp(f[0],"hint"))th_copy(th_dialog.hint,f[1]);else if(!strcmp(f[0],"message"))th_copy(th_dialog.message,f[1]);
  else if(!strcmp(f[0],"row") && n>=3 && th_dialog.rows<8){th_copy(th_dialog.row[th_dialog.rows][0],f[1]);th_copy(th_dialog.row[th_dialog.rows++][1],f[2]);}
  else if(!strcmp(f[0],"low") && n>=3 && th_dialog.lows<6){th_copy(th_dialog.low[th_dialog.lows][0],f[1]);th_copy(th_dialog.low[th_dialog.lows++][1],f[2]);}
  else if(!strcmp(f[0],"amount") && n>=6){th_dialog.has_amount=1;th_copy(th_dialog.amount[0],f[1]);th_copy(th_dialog.amount[1],f[2]);
   th_dialog.amount_value=atoi(f[3]);th_dialog.amount_min=atoi(f[4]);th_dialog.amount_max=atoi(f[5]);if(th_dialog.amount_max<th_dialog.amount_min)th_dialog.amount_max=th_dialog.amount_min;}
  else if(!strcmp(f[0],"calc") && n>=6){
   int k=!strcmp(f[1],"coup")?1:!strcmp(f[1],"gift")?2:!strcmp(f[1],"bid")?3:0,count=k==1?5:k==3?2:6;
   if(k && n>=2+count+2){th_dialog.calc=k;for(int i=0;i<count;i++)th_dialog.calc_v[i]=atoi(f[2+i]);th_dialog.calc_ready=atoi(f[2+count]);th_copy(th_dialog.calc_reason,f[3+count]);}
  }
  else if(!strcmp(f[0],"bar") && n>=4){th_dialog.has_bar=1;th_copy(th_dialog.bar[0],f[1]);th_copy(th_dialog.bar[1],f[2]);th_dialog.bar_value=atoi(f[3]);}
  else if(!strcmp(f[0],"go") && n>=3){th_copy(th_dialog.go,f[1]);th_dialog.go_on=atoi(f[2]);}
 }
}
static void th_read(void){
 unsigned now=time_get_millis();if(th_read_at && now-th_read_at<200)return;th_read_at=now?now:1;
 static char line[4096];char *f[12];FILE *file;
 memset(&th_box,0,sizeof(th_box));th_box.stages=5;
 if((file=th_open("throne-box.txt"))){
  while(fgets(line,sizeof(line),file)){
   int n=th_split(line,f,6);if(n<2)continue;
   if(!strcmp(f[0],"state"))th_box.state=!strcmp(f[1],"restoring")?1:!strcmp(f[1],"peace")?2:!strcmp(f[1],"active")?3:!strcmp(f[1],"ended")?4:!strcmp(f[1],"progress")?5:0;
   else if(!strcmp(f[0],"pg_small") && n>=3){snprintf(th_box.pg_small[0],64,"%s",f[1]);snprintf(th_box.pg_small[1],64,"%s",f[2]);}
   else if(!strcmp(f[0],"pg_title"))th_copy(th_box.pg_title,f[1]);
   else if(!strcmp(f[0],"pg_row") && n>=3 && th_box.pg_rows<8){th_copy(th_box.pg_row[th_box.pg_rows][0],f[1]);th_copy(th_box.pg_row[th_box.pg_rows++][1],f[2]);}
   else if(!strcmp(f[0],"pg_favor") && n>=5 && th_box.pg_favors<8){int k=th_box.pg_favors++;snprintf(th_box.pg_favor[k][0],96,"%s",f[1]);snprintf(th_box.pg_favor[k][1],96,"%s",f[2]);th_box.pg_me[k]=atoi(f[3]);th_box.pg_win[k]=atoi(f[4]);}
   else if(!strcmp(f[0],"bid"))th_box.pg_bid=atoi(f[1]);
   else if(!strcmp(f[0],"paranoia"))th_box.paranoia=atoi(f[1]);else if(!strcmp(f[0],"mine"))th_box.mine=atoi(f[1]);
   else if(!strcmp(f[0],"leading"))th_box.leading=atoi(f[1]);else if(!strcmp(f[0],"stages"))th_box.stages=atoi(f[1]);
   else if(!strcmp(f[0],"coup"))th_box.coup=atoi(f[1]);else if(!strcmp(f[0],"gift"))th_box.gift=atoi(f[1]);
   else if(!strcmp(f[0],"mood"))th_copy(th_box.mood,f[1]);else if(!strcmp(f[0],"note"))th_copy(th_box.note,f[1]);
   else if(!strcmp(f[0],"march") && n>=4){th_box.march=1;th_copy(th_box.march_title,f[1]);th_copy(th_box.march_wait,f[2]);th_box.march_on=atoi(f[3]);}
  }
  fclose(file);
 }
 if(th_box.stages<1 || th_box.stages>5)th_box.stages=5;
 memset(&th_dialog,0,sizeof(th_dialog));
 if(th_box.state && (file=th_open("throne-dialog.txt"))){th_parse_dialog(file,line,f);fclose(file);}
 /* A dialog opened here at the click from the bridge's prepared copy (throne-prep-*.txt), until the bridge's own
  * answer arrives (user 2026-11-15: the dialogs opened only after the room answered and felt slow). */
 if(th_dialog.open)th_local_at=0;
 else if(th_local_at && time_get_millis()-th_local_at<TH_LOCAL_MS && th_box.state){
  char name[48];snprintf(name,sizeof(name),"throne-prep-%s.txt",th_local_kind);
  if((file=th_open(name))){th_parse_dialog(file,line,f);fclose(file);if(strcmp(th_dialog.kind,th_local_kind))memset(&th_dialog,0,sizeof(th_dialog));}
 }else th_local_at=0;
 int rows=0,foots=0;char title[TH_TEXT]="",subtitle[TH_TEXT]="";
 if(th_box.state && (file=th_open("throne-score.txt"))){
  while(fgets(line,sizeof(line),file)){
   int n=th_split(line,f,12);if(n<2)continue;
   if(!strcmp(f[0],"title"))th_copy(title,f[1]);else if(!strcmp(f[0],"subtitle"))th_copy(subtitle,f[1]);
   else if(!strcmp(f[0],"foot") && foots<3)th_copy(th_score.foot[foots++],f[1]);
   else if(!strcmp(f[0],"row") && n>=11 && rows<8){for(int k=0;k<10;k++)snprintf(th_score.row[rows][k],sizeof(th_score.row[0][0]),"%s",f[k+1]);rows++;}
  }
  fclose(file);
 }
 th_amount_follow();
 if(!rows)th_score.dismissed=0;
 th_score.rows=rows;th_score.foots=foots;th_copy(th_score.title,title);th_copy(th_score.subtitle,subtitle);
}
/* A click on 쿠데타 지원 / 끌어내리기 / 충성선물: the bridge keeps a prepared copy of each dialog (throne-prep-<kind>.txt,
 * throne_client.prepared). "refuse<TAB>why" when it would not open (a coup that has to wait): the reason shows under
 * the box at once. Otherwise the dialog shows at once; the bridge's own dialog replaces it when it arrives. */
static void th_open_local(const char *kind){
 char name[48],line[4096];snprintf(name,sizeof(name),"throne-prep-%s.txt",kind);FILE *file=th_open(name);if(!file)return;
 if(fgets(line,sizeof(line),file) && !strncmp(line,"refuse\t",7)){
  line[strcspn(line,"\r\n")]=0;th_copy(th_local_note,line+7);th_local_note_at=time_get_millis();if(!th_local_note_at)th_local_note_at=1;th_local_at=0;
 }else{snprintf(th_local_kind,sizeof(th_local_kind),"%s",kind);th_local_at=time_get_millis();if(!th_local_at)th_local_at=1;th_local_note_at=0;}
 fclose(file);
}
/* Text helpers: the text is shown in the reader's language (encoding_from_utf8 translates a whole line). */
static int th_width(const char *s,font_t f){uint8_t t[2048];encoding_from_utf8(s,t,sizeof(t));return text_get_width(t,f);}
static void th_left(const char *s,int x,int y,font_t f,color_t c){uint8_t t[2048];encoding_from_utf8(s,t,sizeof(t));text_draw(t,x,y,f,c);}
static void th_center(const char *s,int x,int y,int w,font_t f,color_t c){uint8_t t[2048];encoding_from_utf8(s,t,sizeof(t));text_draw_centered(t,x,y,w,f,c);}
static void th_right(const char *s,int x,int y,int w,font_t f,color_t c){uint8_t t[2048];encoding_from_utf8(s,t,sizeof(t));text_draw(t,x+w-text_get_width(t,f),y,f,c);}
static void th_paper(int x,int y,int w,int h){unbordered_panel_draw_px(x,y,w,h);graphics_draw_rect(x,y,w,h,0xff5a4a3a);graphics_draw_line(x+w,x+w,y+2,y+h,0x80000000);graphics_draw_line(x+2,x+w,y+h,y+h,0x80000000);}
static int th_over(int x,int y,int w,int h){const mouse *m=mouse_get();return m->x>=x && m->x<x+w && m->y>=y && m->y<y+h;}
/* An ordinary button; remembered for the click. A disabled one is drawn pale and takes no click. */
static void th_button(const char *id,const char *label,int x,int y,int w,int h,int on){
 button_border_draw(x,y,w,h,on && th_over(x,y,w,h));th_center(label,x,y+(h-14)/2,w,on?FONT_NORMAL_BLACK:FONT_SMALL_PLAIN,0);
 if(th_hit_count<TH_HITS){th_hit *b=&th_hits[th_hit_count++];b->x=x;b->y=y;b->w=w;b->h=h;b->on=on;snprintf(b->id,sizeof(b->id),"%s",id);}
}
/* Stage squares: drawn, not letters, so no font can lack them. */
static void th_pips(int x,int y,int filled,int total){for(int k=0;k<total;k++){graphics_fill_rect(x+k*13,y,11,10,k<filled?0xffb0241c:0xffcbbf9f);graphics_draw_rect(x+k*13,y,11,10,0xff3a2a1a);}}
/* A value "@goods 1 15 18" is drawn as goods: each with its icon and the game's own name (user 2026-11-15). */
static int th_goods(const char *v,int *ids){
 if(strncmp(v,"@goods",6))return 0;int n=0;const char *p=v+6;
 while(n<4){while(*p==' ')p++;if(!*p)break;int id=atoi(p);if(id>=RESOURCE_MIN && id<RESOURCE_MAX)ids[n++]=id;while(*p && *p!=' ')p++;}
 return n;
}
static int th_value_width(const char *v){
 int ids[4],n=th_goods(v,ids);if(!n)return th_width(v,FONT_NORMAL_BLACK);
 int w=0;for(int i=0;i<n;i++)w+=28+text_get_width(resource_get_data(ids[i])->text,FONT_NORMAL_BLACK)+(i?10:0);
 return w;
}
static void th_row(const char *k,const char *v,int x,int y,int w){
 th_left(k,x,y,FONT_NORMAL_BLACK,0);int ids[4],n=th_goods(v,ids);
 if(!n){th_right(v,x,y,w,FONT_NORMAL_BLACK,0);return;}
 int gx=x+w-th_value_width(v);
 for(int i=0;i<n;i++){
  const resource_data *d=resource_get_data(ids[i]);image_draw(d->image.icon,gx,y-5,COLOR_MASK_NONE,SCALE_NONE);
  text_draw(d->text,gx+28,y,FONT_NORMAL_BLACK,0);gx+=28+text_get_width(d->text,FONT_NORMAL_BLACK)+10;
 }
}
/* A line broken between words into rows no wider than `width` (never cut with "..."). Returns the rows drawn. */
static int th_wrapped(const char *utf8,int x,int y,int width,font_t font,int step,int draw){
 char text[2048];snprintf(text,sizeof(text),"%s",mp_i18n_translate(utf8));char rowtext[1024]="";int rows=0;char *p=text;
 while(*p){
  while(*p==' ')p++;char *end=strchr(p,' ');size_t length=end?(size_t)(end-p):strlen(p);if(!length)break;
  char candidate[1024];if(snprintf(candidate,sizeof(candidate),"%s%s%.*s",rowtext,rowtext[0]?" ":"",(int)length,p)>=(int)sizeof(candidate))break;
  uint8_t t[2048];mp_i18n_suspend(1);encoding_from_utf8(candidate,t,sizeof(t));mp_i18n_suspend(0);
  if(rowtext[0] && text_get_width(t,font)>width){
   if(draw){mp_i18n_suspend(1);encoding_from_utf8(rowtext,t,sizeof(t));mp_i18n_suspend(0);text_draw(t,x,y+rows*step,font,0);}
   rows++;rowtext[0]=0;continue;
  }
  strcpy(rowtext,candidate);p+=length;
 }
 if(rowtext[0]){if(draw){uint8_t t[2048];mp_i18n_suspend(1);encoding_from_utf8(rowtext,t,sizeof(t));mp_i18n_suspend(0);text_draw(t,x,y+rows*step,font,0);}rows++;}
 return rows;
}
/* "보내기" pressed: the dialog goes away at once and the box says it is on its way (user 2026-11-14: the dialog
 * stayed until the room answered and the result did not feel like one). It comes back only with a message from the
 * room (the state changed, refused), or after 5 s without any answer. */
static unsigned th_go_at;static char th_go_message[TH_TEXT];
static int th_sending(void){return th_go_at && time_get_millis()-th_go_at<5000;}
static int th_dialog_shown(void){
 if(!th_dialog.open){th_go_at=0;return 0;}
 if(th_sending() && !strcmp(th_dialog.message,th_go_message))return 0;
 return 1;
}
/* A dialog or the scoreboard: nothing else is clicked, so it is drawn over everything (multiplayer_sidetabs.inc). */
static int throne_hud_modal(void){return (th_score.rows && !th_score.dismissed) || th_dialog_shown();}
/* The developer panel under the box (user 2026-11-17: a developer room of the game hall; Korean edition only,
 * multiplayer_dev.inc). Without that file: the test launcher's panel (multiplayer_throne_test.inc, in no release;
 * MP_TEST_TOOLS, multiplayer_lobby.c). Without either nothing is drawn and no key of it exists. */
#if defined(__has_include)
#if __has_include("multiplayer_dev.inc")
#define MP_DEV_PANEL 1
#endif
#endif
#ifdef MP_DEV_PANEL
#include "multiplayer_dev.inc"
#elif defined(MP_TEST_TOOLS)
#include "multiplayer_throne_test.inc"
#else
static int th_test_rect[4];
static void th_test_draw(int vx,int vw,int y,int box_w){(void)vx;(void)vw;(void)y;(void)box_w;th_test_rect[2]=0;}
static int th_test_click(const char *id){(void)id;return 0;}
#endif
#ifndef MP_DEV_PANEL
static void th_dev_close(void){}
#endif
static void th_box_draw(int vx,int vy,int vw){
 th_box_rect[2]=0;th_test_rect[2]=0;th_dev_rect[2]=0;if(!th_box.state){th_test_draw(vx,vw,vy+2,0);return;}   /* no box: the developer panel's own button, in a developer room */
 int peace=th_box.state==2,icon=image_group(GROUP_ADVISOR_ICONS)+2;
 char number[16];snprintf(number,sizeof(number),"%d",th_box.paranoia);
 if(th_box.state==1){   /* restoring: only the note */
  int w=th_width(th_box.note,FONT_SMALL_PLAIN)+24;if(w>vw-20)w=vw-20;int x=vx+vw-w-1,y=vy+2;th_paper(x,y,w,30);th_wrapped(th_box.note,x+12,y+9,w-24,FONT_SMALL_PLAIN,14,1);
  th_box_rect[0]=x;th_box_rect[1]=y;th_box_rect[2]=w;th_box_rect[3]=30;return;
 }
 if(th_local_note_at && time_get_millis()-th_local_note_at>8000)th_local_note_at=0;
 const char *box_note=th_box.note[0]?th_box.note:th_local_note_at?th_local_note:"";
 int note=box_note[0]!=0,x,y=vy+2,w,h;
 if(th_box.state==5 && !th_expanded){   /* 황제의 순행, closed: the icon, "순행" and which one of how many */
  w=th_width(th_box.pg_small[0],FONT_NORMAL_BLACK)+8;if(w<52)w=52;h=104;x=vx+vw-w-1;th_paper(x,y,w,h);image_draw(icon,x+(w-40)/2,y+6,COLOR_MASK_NONE,SCALE_NONE);
  th_center(th_box.pg_small[0],x,y+54,w,FONT_NORMAL_BLACK,0);mp_i18n_suspend(1);th_center(th_box.pg_small[1],x,y+76,w,FONT_NORMAL_BLACK,0);mp_i18n_suspend(0);
 }else if(th_box.state==5){   /* open: the rows, every governor's favour, the bid button */
  int kw=0,vw2=0,fw=0;
  for(int i=0;i<th_box.pg_rows;i++){int t=th_width(th_box.pg_row[i][0],FONT_NORMAL_BLACK);if(t>kw)kw=t;t=th_value_width(th_box.pg_row[i][1]);if(t>vw2)vw2=t;}
  for(int i=0;i<th_box.pg_favors;i++){mp_i18n_suspend(1);int t=th_width(th_box.pg_favor[i][0],FONT_NORMAL_BLACK)+th_width(th_box.pg_favor[i][1],FONT_NORMAL_BLACK)+24;mp_i18n_suspend(0);if(t>fw)fw=t;}
  w=kw+16+vw2+24;if(fw+24>w)w=fw+24;{int t=th_width(th_box.pg_title,FONT_NORMAL_BLACK)+24;if(t>w)w=t;}if(w<240)w=240;if(w>vw-20)w=vw-20;
  h=34+th_box.pg_rows*20+10+18+th_box.pg_favors*20+8+32+34;x=vx+vw-w-1;th_paper(x,y,w,h);
  th_center(th_box.pg_title,x,y+10,w,FONT_NORMAL_BLACK,0);int r=y+34;
  for(int i=0;i<th_box.pg_rows;i++,r+=20)th_row(th_box.pg_row[i][0],th_box.pg_row[i][1],x+12,r,w-24);
  r+=4;graphics_draw_line(x+10,x+w-10,r,r,0xff5a4a3a);r+=6;th_left("황제의 총애",x+12,r,FONT_SMALL_PLAIN,0);r+=18;
  for(int i=0;i<th_box.pg_favors;i++,r+=20){
   if(th_box.pg_win[i])graphics_fill_rect(x+8,r-3,w-16,19,0x50ffd24a);
   uint8_t name[256];mp_i18n_suspend(1);encoding_from_utf8(th_box.pg_favor[i][0],name,sizeof(name));
   text_draw_ellipsized(name,x+12,r,w-24-48,th_box.pg_me[i]?FONT_NORMAL_RED:FONT_NORMAL_BLACK,0);th_right(th_box.pg_favor[i][1],x+12,r,w-24,FONT_NORMAL_BLACK,0);mp_i18n_suspend(0);
  }
  th_button("bid","입찰하기",x+8,y+h-64,w-16,26,th_box.pg_bid);
 }else if(!th_expanded){
  /* the label of another language can be wider than the Korean one: the box grows with it */
  w=th_width(peace?"평화":"편집증",peace?FONT_NORMAL_BLACK:FONT_NORMAL_RED)+8;if(w<52)w=52;h=peace?84:104;x=vx+vw-w-1;th_paper(x,y,w,h);image_draw(icon,x+(w-40)/2,y+6,COLOR_MASK_NONE,SCALE_NONE);
  if(peace)th_center("평화",x,y+56,w,FONT_NORMAL_BLACK,0);
  else{th_center("편집증",x,y+54,w,FONT_NORMAL_RED,0);th_center(number,x,y+74,w,FONT_LARGE_PLAIN,COLOR_RED);}
 }else if(peace){
  const char *l1="제국은 평화롭습니다",*l2="황제는 아직 총독들을 의심하지 않습니다";
  int tw=th_width(l1,FONT_NORMAL_BLACK),t2=th_width(l2,FONT_SMALL_PLAIN);if(t2>tw)tw=t2;
  w=66+tw+12;if(w<224)w=224;h=150;x=vx+vw-w-1;th_paper(x,y,w,h);image_draw(icon,x+8,y+8,COLOR_MASK_NONE,SCALE_NONE);
  th_center("평화",x+4,y+56,50,FONT_NORMAL_BLACK,0);th_left(l1,x+66,y+10,FONT_NORMAL_BLACK,0);th_left(l2,x+66,y+32,FONT_SMALL_PLAIN,0);
  th_button("coup","끌어내리기",x+66,y+84,w-74,26,th_box.coup);
 }else{
  const char *mine="내 쿠데타 준비",*lead="가장 앞선 모의";
  int label=th_width(lead,FONT_NORMAL_BLACK),l2=th_width(mine,FONT_NORMAL_BLACK);if(l2>label)label=l2;
  int tw=label+6+th_box.stages*13,t3=th_width(th_box.mood,FONT_SMALL_PLAIN);if(t3>tw)tw=t3;
  int b1=th_width("쿠데타 지원",FONT_NORMAL_BLACK)+20,b2=th_width("충성선물",FONT_NORMAL_BLACK)+20,bw=b1>b2?b1:b2;
  int ox=th_width("편집증",FONT_NORMAL_RED)-50;if(ox<0)ox=0;   /* a wider label widens the left column */
  w=66+ox+tw+12;if(w<bw*2+24)w=bw*2+24;if(w<224)w=224;h=162;x=vx+vw-w-1;   /* 132 + the close row */
  th_paper(x,y,w,h);image_draw(icon,x+8+ox/2,y+8,COLOR_MASK_NONE,SCALE_NONE);
  th_center("편집증",x+4,y+54,50+ox,FONT_NORMAL_RED,0);th_center(number,x+4,y+70,50+ox,FONT_LARGE_PLAIN,COLOR_RED);
  int lx=x+66+ox,px=lx+label+6;
  th_left(mine,lx,y+10,FONT_NORMAL_BLACK,0);th_pips(px,y+12,th_box.mine,th_box.stages);
  th_left(lead,lx,y+32,FONT_NORMAL_BLACK,0);th_pips(px,y+34,th_box.leading,th_box.stages);
  th_left(th_box.mood,lx,y+56,FONT_SMALL_PLAIN,0);
  if(th_box.state==3){bw=(w-24)/2;th_button("coup","쿠데타 지원",x+8,y+98,bw,26,th_box.coup);th_button("gift","충성선물",x+16+bw,y+98,bw,26,th_box.gift);}
  /* ended: no buttons; the close button stays at the bottom of the drawn frame */
 }
 if(th_expanded)th_button("boxclose","닫기",x+8,y+h-32,w-16,26,1);   /* the box's own close, full width (user 2026-11-14) */
 th_box_rect[0]=x;th_box_rect[1]=y;th_box_rect[2]=w;th_box_rect[3]=h;
 int below=y+h+2;
 if(!note && th_sending())note=1;
 if(note){   /* a note for a while (a coup that has to wait, a spend being charged): its own strip under the box, as wide as it needs */
  const char *text=box_note[0]?box_note:"요청 전송 중입니다.";   /* sent from the dialog, before the room's own note */
  int nw=th_width(text,FONT_SMALL_PLAIN)+24;if(nw<w)nw=w;if(nw>vw-20)nw=vw-20;
  int rows=th_wrapped(text,0,0,nw-24,FONT_SMALL_PLAIN,14,0),nh=rows*14+12,nx=vx+vw-nw-1,ny=y+h+2;
  th_paper(nx,ny,nw,nh);th_wrapped(text,nx+12,ny+7,nw-24,FONT_SMALL_PLAIN,14,1);below=ny+nh+2;
 }
 th_test_draw(vx,vw,below,w);
}
/* The march card: the same look as the trade-post reminder (label, yellow frame, red bar, one button). */
static void th_card_draw(int vx,int vy,int vw){
 th_card_rect[2]=0;if(!th_box.march || th_box.state!=3)return;
 /* Left of the box, right of the side tabs: never under either. Under the box when there is no room beside it. */
 int bw=th_width("공물 바치기",FONT_NORMAL_BLACK)+24;if(bw<112)bw=112;
 /* wide enough for the waiting time beside the button and for the title (longer in other languages) */
 int want=24+th_width(th_box.march_wait,FONT_SMALL_PLAIN)+12+bw+8,t=24+th_width(th_box.march_title,FONT_NORMAL_BLACK)+12;if(t>want)want=t;if(want<360)want=360;
 /* nor under the maker button or its open panel (user 2026-11-17: nothing may cover another thing's keys) */
 int right=th_box_rect[2]?th_box_rect[0]:vx+vw;
 if(th_dev_rect[2] && th_dev_rect[1]<vy+30+64 && th_dev_rect[0]<right)right=th_dev_rect[0];
 int left=vx+60,room=right-8-left,w=room>want?want:room,h=64,beside=room>=240;if(!beside){w=vw-70;if(w>want)w=want;}
 int x=beside?left:vx+vw-w-1,y=beside?vy+30:th_box_rect[1]+th_box_rect[3]+(th_box.note[0]?44:6);
 if(!beside && th_test_rect[2] && y<th_test_rect[1]+th_test_rect[3]+6)y=th_test_rect[1]+th_test_rect[3]+6;
 if(!beside && th_dev_rect[2] && x+w>th_dev_rect[0] && y<th_dev_rect[1]+th_dev_rect[3]+6)y=th_dev_rect[1]+th_dev_rect[3]+6;
 large_label_draw_custom_size(x,y,w,h);graphics_draw_rect(x,y,w,h,0xffffcf70);
 graphics_fill_rect(x+8,y+8,8,h-16,0xffb0241c);graphics_draw_rect(x+8,y+8,8,h-16,COLOR_BLACK);
 th_left(th_box.march_title,x+24,y+9,FONT_NORMAL_BLACK,0);th_left(th_box.march_wait,x+24,y+40,FONT_SMALL_PLAIN,0);
 large_label_draw_custom_size(x+w-bw-8,y+31,bw,26);th_button("tribute","공물 바치기",x+w-bw-8,y+31,bw,26,th_box.march_on);
 th_card_rect[0]=x;th_card_rect[1]=y;th_card_rect[2]=w;th_card_rect[3]=h;
}
static void th_meter(int x,int y,int w,int v){if(v<0)v=0;if(v>100)v=100;graphics_fill_rect(x,y,w,10,0xff3a3022);int c=v<40?0xff3f9a3a:v<70?0xffd6b22a:0xffc8261e;graphics_fill_rect(x+1,y+1,(w-2)*v/100,8,c);graphics_draw_rect(x,y,w,10,0xff1a120a);}
static void th_dialog_draw(int vx,int vy,int vw,int vh){
 th_dialog_rect[2]=0;if(!th_dialog_shown())return;
 int w=448,inner=w-56;
 /* the rows under the amount and the reason it cannot be sent: calculated here when the dialog carries the rules */
 static char local_low[3][2][TH_TEXT];static char local_reason[TH_TEXT];local_reason[0]=0;int local_lows=0,local_ok=0;
 if(th_dialog.calc && th_dialog.has_amount && th_amount.value>=0){
  local_ok=th_local(th_amount.value,local_low,&local_lows,local_reason);
  th_dialog.lows=local_lows;for(int i=0;i<local_lows;i++){th_copy(th_dialog.low[i][0],local_low[i][0]);th_copy(th_dialog.low[i][1],local_low[i][1]);}
  th_dialog.go_on=local_ok;
 }
 /* a message from the room (the state changed ...) comes first, else why this amount cannot be sent */
 const char *message=th_dialog.message[0]?th_dialog.message:th_dialog.calc?local_reason:"";
 int desc_rows=th_dialog.desc[0]?th_wrapped(th_dialog.desc,0,0,w-56,FONT_NORMAL_PLAIN,18,0):0;
 int hint_rows=th_dialog.hint[0]?th_wrapped(th_dialog.hint,0,0,inner,FONT_SMALL_PLAIN,14,0):0;
 int message_rows=message[0]?th_wrapped(message,0,0,inner,FONT_NORMAL_BLACK,16,0):0;
 int panel_blocks=desc_rows?(desc_rows*18+(th_dialog.small[0]?26:0)+20+15)/16:0;
 int h=74+(panel_blocks?panel_blocks*16+14:0)+th_dialog.rows*24+(th_dialog.has_bar?24:0)+(th_dialog.has_amount?66:0)+th_dialog.lows*24
       +(hint_rows?hint_rows*14+8:0)+(message_rows?message_rows*16+8:0)+12+28+20;
 int blocks=(h+15)/16;h=blocks*16;
 int x=vx+(vw-w)/2,y=vy+(vh-h)/2;if(y<vy+4)y=vy+4;
 outer_panel_draw(x,y,w/16,blocks);
 th_center(th_dialog.title,x,y+16,w,FONT_LARGE_BLACK,0);th_center(th_dialog.subtitle,x,y+46,w,FONT_NORMAL_BLACK,0);
 int r=y+74,lx=x+28;
 if(panel_blocks){
  inner_panel_draw(x+16,r-4,(w-32)/16,panel_blocks);th_wrapped(th_dialog.desc,lx,r+6,w-56,FONT_NORMAL_PLAIN,18,1);
  if(th_dialog.small[0])th_left(th_dialog.small,lx,r+6+desc_rows*18+8,FONT_SMALL_PLAIN,0);
  r+=panel_blocks*16+14;
 }
 for(int i=0;i<th_dialog.rows;i++,r+=24)th_row(th_dialog.row[i][0],th_dialog.row[i][1],lx,r,inner);
 if(th_dialog.has_bar){
  th_left(th_dialog.bar[0],lx,r,FONT_NORMAL_BLACK,0);th_right(th_dialog.bar[1],lx,r,inner,FONT_NORMAL_BLACK,0);
  int from=lx+th_width(th_dialog.bar[0],FONT_NORMAL_BLACK)+12,to=lx+inner-th_width(th_dialog.bar[1],FONT_NORMAL_BLACK)-12;if(to-from>=40)th_meter(from,r+3,to-from,th_dialog.bar_value);
  r+=24;
 }
 if(th_dialog.has_amount){   /* as in the trade window: [-] value [+], then +1,000 +5,000 +10,000 and reset */
  int ax=x+w-28-256;r+=6;
  th_left(th_dialog.amount[0],lx,r+6,FONT_NORMAL_BLACK,0);
  char shown[48];th_dn(th_amount.value>=0?th_amount.value:th_dialog.amount_value,shown,sizeof(shown));
  th_button("less","-",ax,r,32,26,1);graphics_fill_rect(ax+43,r+3,170,20,0xfff3e4c5);button_border_draw(ax+40,r,176,26,1);
  mp_i18n_suspend(1);th_center(shown,ax+40,r+6,176,FONT_NORMAL_BLACK,0);mp_i18n_suspend(0);
  if(th_hit_count<TH_HITS){th_hit *b=&th_hits[th_hit_count++];b->x=ax+40;b->y=r;b->w=176;b->h=26;b->on=1;snprintf(b->id,sizeof(b->id),"amountbox");}   /* the number pad */
  th_button("more","+",ax+224,r,32,26,1);
  {int rw=th_width("초기화",FONT_NORMAL_BLACK)+12;if(rw<58)rw=58;int bx=ax-(rw-58);   /* a longer word of another language: the row moves left, its right edge stays */
  th_button("add1000","+1,000",bx,r+30,58,22,1);th_button("add5000","+5,000",bx+66,r+30,58,22,1);th_button("add10000","+10,000",bx+132,r+30,58,22,1);th_button("reset","초기화",bx+198,r+30,rw,22,1);}
  r+=60;
 }
 for(int i=0;i<th_dialog.lows;i++,r+=24)th_row(th_dialog.low[i][0],th_dialog.low[i][1],lx,r,inner);
 if(hint_rows){th_wrapped(th_dialog.hint,lx,r+2,inner,FONT_SMALL_PLAIN,14,1);r+=hint_rows*14+8;}
 if(message_rows){th_wrapped(message,lx,r+2,inner,FONT_NORMAL_BLACK,16,1);r+=message_rows*16+8;}
 int by=y+h-28-20;
 th_button("go",th_dialog.go,x+w/2-190,by,180,28,th_dialog.go_on);th_button("close","취소",x+w/2+10,by,180,28,1);
 th_dialog_rect[0]=x;th_dialog_rect[1]=y;th_dialog_rect[2]=w;th_dialog_rect[3]=h;
}
static void th_score_draw(int vx,int vy,int vw,int vh){
 th_score_rect[2]=0;if(!th_score.rows || th_score.dismissed)return;
 static const char *H[]={"순위","총독","단계","쿠데타","지원금","선물","원정","편집증"};
 static const char *H2[]={"","","","성공 / 실패","합계","합계","횟수 / 공물","최종"};
 /* Columns as wide as their widest text (headers of other languages are longer); the name column gives way first. */
 int X[8],W[8],name_w=134,max_w=vw-8;
 for(int k=0;k<8;k++){W[k]=th_width(H[k],FONT_SMALL_PLAIN);int v=H2[k][0]?th_width(H2[k],FONT_SMALL_PLAIN):0;if(v>W[k])W[k]=v;
  if(k!=1)for(int i=0;i<th_score.rows;i++){v=th_width(th_score.row[i][k],FONT_NORMAL_BLACK)+(k==0?10:0);if(v>W[k])W[k]=v;}}
 int gap=10;if(vw>=620)max_w=(vw-60)/16*16;   /* beside the side tabs when the view allows it */
 for(;;){if(W[1]<name_w)W[1]=name_w;X[0]=8;for(int k=1;k<8;k++)X[k]=X[k-1]+W[k-1]+gap;if(X[7]+W[7]+8+24<=max_w)break;if(gap>6)gap--;else if(name_w>80){name_w-=4;W[1]=0;}else if(gap>3)gap--;else break;}
 int w=560,foot_rows=0;if(X[7]+W[7]+8+24>w)w=(X[7]+W[7]+8+24+15)/16*16;for(int i=0;i<th_score.foots;i++)foot_rows+=th_wrapped(th_score.foot[i],0,0,w-48,FONT_SMALL_PLAIN,14,0);
 int blocks=8+2*th_score.rows+foot_rows+5,h=blocks*16;
 int x=vx+(vw-w)/2,y=vy+(vh-h)/2;if(x<vx+56 && vw>=w+60)x=vx+56;if(y<vy+2)y=vy+2;   /* clear of the side tabs when the view is narrow */
 outer_panel_draw(x,y,w/16,blocks);
 th_center(th_score.title,x,y+14,w,FONT_LARGE_BLACK,0);th_center(th_score.subtitle,x,y+46,w,FONT_NORMAL_BLACK,0);
 int rows_blocks=2*th_score.rows+3;inner_panel_draw(x+12,y+74,(w-24)/16,rows_blocks);
 for(int i=0;i<8;i++){th_left(H[i],x+12+X[i],y+82,FONT_SMALL_PLAIN,0);if(H2[i][0])th_left(H2[i],x+12+X[i],y+96,FONT_SMALL_PLAIN,0);}
 for(int i=0;i<th_score.rows;i++){
  int r=y+122+i*32;if(atoi(th_score.row[i][8]))graphics_fill_rect(x+16,r-7,w-32,30,0x50ffd24a);   /* the new emperor */
  char rank[32];snprintf(rank,sizeof(rank),"%s",th_score.row[i][0]);th_left(rank,x+12+10,r,FONT_NORMAL_BLACK,0);
  uint8_t name[256];mp_i18n_suspend(1);encoding_from_utf8(th_score.row[i][1],name,sizeof(name));mp_i18n_suspend(0);text_draw_ellipsized(name,x+12+X[1],r,W[1],atoi(th_score.row[i][9])?FONT_NORMAL_RED:FONT_NORMAL_BLACK,0);
  for(int k=2;k<8;k++)th_left(th_score.row[i][k],x+12+X[k],r,FONT_NORMAL_BLACK,0);
 }
 int fy=y+74+rows_blocks*16+10;for(int i=0;i<th_score.foots;i++)fy+=14*th_wrapped(th_score.foot[i],x+24,fy,w-48,FONT_SMALL_PLAIN,14,1)+2;
 th_button("scoreclose","도시로 돌아가기",x+w/2-90,y+h-28-16,180,28,1);
 th_score_rect[0]=x;th_score_rect[1]=y;th_score_rect[2]=w;th_score_rect[3]=h;
}
static void throne_hud_draw(void){
 th_read();th_hit_count=0;window_multiplayer_overlay_hook=window_multiplayer_overlay_at;
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);
 th_box_draw(vx,vy,vw);th_card_draw(vx,vy,vw);
 if(th_score.rows && !th_score.dismissed){int count=th_hit_count;th_hit_count=0;(void)count;th_score_draw(vx,vy,vw,vh);}   /* the end: only the scoreboard takes clicks */
 else th_dialog_draw(vx,vy,vw,vh);
}
static int th_inside(const int *r,const mouse *m){return r[2] && m->x>=r[0] && m->x<r[0]+r[2] && m->y>=r[1] && m->y<r[1]+r[3];}
static int window_multiplayer_overlay_at(int x,int y){
 if(th_dialog_shown() || (th_score.rows && !th_score.dismissed))return 1;
 const int *r[]={th_box_rect,th_card_rect,th_test_rect,th_dev_rect};
 for(int i=0;i<4;i++)if(r[i][2] && x>=r[i][0] && x<r[i][0]+r[i][2] && y>=r[i][1] && y<r[i][1]+r[i][3])return 1;
 return 0;
}
/* What the side tabs draw over the box, the card and the maker tools (they come later in a frame): an open panel,
 * the to-do cards and the note beside the tabs. A click there is theirs, never the box's below (user 2026-11-17). */
static int th_in(int x,int y,int w,int h,const mouse *m){return m->x>=x && m->x<x+w && m->y>=y && m->y<y+h;}
static int th_covered(const mouse *m){
 int x,y,w,h;
 if(!side_hidden && side_tab && th_in(side_px,side_py,side_pw,side_ph,m))return 1;
 if(side_toast_rect(&x,&y,&w,&h) && th_in(x,y,w,h,m))return 1;
 if(side_tab!=1){
  int others;
  if(post_reminder_find(&others)>=0 && post_reminder_rect(&x,&y,&w) && th_in(x,y,w,city_card_h(),m))return 1;
  if(cash_card_find(&others)>=0 && cash_card_rect(&x,&y,&w) && th_in(x,y,w,city_card_h(),m))return 1;
 }
 return 0;
}
/* The left edge of the box, the card and the maker tools between `top` and `bottom` (the screen's width when none):
 * the status notes at the top left of the screen end before it (multiplayer_chat.c). */
int window_multiplayer_hud_left(int top,int bottom){
 int left=screen_width();const int *r[]={th_box_rect,th_card_rect,th_test_rect,th_dev_rect};
 for(int i=0;i<4;i++)if(r[i][2] && r[i][1]<bottom && r[i][1]+r[i][3]>top && r[i][0]<left)left=r[i][0];
 return left;
}
/* The bottom of the box, the card and the maker tools that reach left of `x` near the top (0 when none): a note with
 * no room beside them goes below them (multiplayer_chat.c). */
int window_multiplayer_hud_bottom(int x,int top,int bottom){
 int low=0;const int *r[]={th_box_rect,th_card_rect,th_test_rect,th_dev_rect};
 for(int i=0;i<4;i++)if(r[i][2] && r[i][1]<bottom && r[i][1]+r[i][3]>top && r[i][0]<x && r[i][1]+r[i][3]>low)low=r[i][1]+r[i][3];
 return low;
}
/* Clicks on the box, the card, a dialog or the scoreboard never reach the city below. A button sends
 * "throne\n<id>\n<treasury>" (mp_client_command); opening and closing the box and closing the scoreboard are local. */
static int throne_hud_input(const mouse *m){
 int score=th_score.rows && !th_score.dismissed,modal=score || th_dialog_shown();
 int inside=th_inside(th_box_rect,m) || th_inside(th_card_rect,m) || th_inside(th_dialog_rect,m) || th_inside(th_score_rect,m) || th_inside(th_test_rect,m) || th_inside(th_dev_rect,m);
 /* the open paranoia box closes on a click anywhere else, as a menu does (user 2026-11-14); the click still goes on */
 if(th_expanded && (m->left.went_down || m->right.went_down) && !th_inside(th_box_rect,m) && !th_inside(th_test_rect,m) && !th_inside(th_dev_rect,m))th_expanded=0;
 if(!inside && !modal)return 0;
 if(!modal && th_covered(m))return 0;   /* drawn over by a side panel, a to-do card or a note: the click is theirs */
 if(m->left.went_up){
  int hit=0;
  for(int i=0;i<th_hit_count;i++){
   th_hit *b=&th_hits[i];if(m->x<b->x || m->x>=b->x+b->w || m->y<b->y || m->y>=b->y+b->h)continue;
   hit=1;if(!b->on)break;
   if(!strcmp(b->id,"scoreclose")){th_score.dismissed=1;break;}
   if(!strcmp(b->id,"boxclose")){th_expanded=0;break;}
   if(th_test_click(b->id))break;   /* the test panel's own keys (test build only) */
   if(th_dialog_shown() && th_dialog.has_amount && th_amount.value>=0){   /* the amount: here, at once (see the header) */
    int v=th_amount.value,local=1;
    if(!strcmp(b->id,"less"))v-=100;else if(!strcmp(b->id,"more"))v+=100;
    else if(!strcmp(b->id,"add1000"))v+=1000;else if(!strcmp(b->id,"add5000"))v+=5000;else if(!strcmp(b->id,"add10000"))v+=10000;
    else if(!strcmp(b->id,"reset"))v=th_dialog.amount_min;
    else if(!strcmp(b->id,"amountbox")){
     static generic_button pad;pad.x=b->x;pad.y=b->y;pad.width=b->w;pad.height=b->h;
     window_numeric_input_bound_show(-screen_dialog_offset_x(),-screen_dialog_offset_y(),&pad,7,th_dialog.amount_min,th_dialog.amount_max,th_amount_typed);break;
    }
    else local=0;
    if(local){th_amount_set(v);break;}
   }
   if(!strcmp(b->id,"coup") || !strcmp(b->id,"gift") || !strcmp(b->id,"bid"))th_open_local(b->id);   /* at once; the bridge's answer follows */
   if(!strcmp(b->id,"close"))th_local_at=0;
   char text[64];
   if(!strcmp(b->id,"go") && th_dialog.has_amount && th_amount.value>=0)snprintf(text,sizeof(text),"go\n%d\n%d",(int)city_finance_treasury(),th_amount.value);   /* the amount shown here */
   else snprintf(text,sizeof(text),"%s\n%d",b->id,(int)city_finance_treasury());
   if(mp_client_command("throne",text) && !strcmp(b->id,"go")){th_go_at=time_get_millis();if(!th_go_at)th_go_at=1;th_copy(th_go_message,th_dialog.message);}
   th_read_at=0;break;
  }
  if(!hit && !modal && th_inside(th_box_rect,m) && th_box.state>=2)th_expanded=!th_expanded;
 }
 if(m->right.went_up && th_dialog_shown() && !score){th_local_at=0;char text[64];snprintf(text,sizeof(text),"close\n%d",(int)city_finance_treasury());mp_client_command("throne",text);th_read_at=0;}
 return 1;   /* while a dialog or the scoreboard is open nothing else is clicked */
}
