/* Validated creator layout. Coordinates are icon centers in the 2000x1000 empire map. */
#include "empire/empire.h"
#include "core/image_group.h"
#include "core/image.h"
#include "empire/object.h"
#include "scenario/data.h"
#include "scenario/empire.h"
#include "scenario/allowed_building.h"
#include "building/menu.h"
typedef struct { int month,amount,point,target,enemy,repeat_every,repeat_times; } creator_city_invasion;   /* enemy: -1 = the city's people (RAIDERS); repeat: INVREPEAT, 0 = once */
typedef struct { int kind,month,amount,resource,deadline,cond,cond_value,repeat_every,repeat_times; } creator_city_event;   /* cond: EVENTCOND, 0 = time only; repeat: EVENTREPEAT, 0 = once */
/* Kinds (Augustus/city_events.py KINDS): 0 grant, 1 favor, 2 request, 3 building, 4 god, 5 goods, 6 health,
   7 migration, 8 revolt, 9 message. The texts of the EVENTTEXT section (UTF-8, "title\nbody") are kept here, outside
   the layout struct that lives on the stack. */
#define CREATOR_EVENT_TEXT 608
#define CREATOR_EVENTS 64   /* per city, repeats laid out (Augustus/city_events.py MAX_LAID_OUT) */
static char creator_event_text[8][CREATOR_EVENTS][CREATOR_EVENT_TEXT];
typedef struct {
 int invasion_count[8];creator_city_invasion invasions[8][16];
 int event_count[8];creator_city_event events[8][CREATOR_EVENTS];
 int version,template_id,count,slots,starting_funds;
 int slot_funds[8],slot_funds_set[8]; /* FUNDS section: a slot's own starting funds, else starting_funds */
 int start_year,start_year_set; /* YEAR section (2026-11-17): the scenario's first year (-500..300, never 0), else -350 */
 int enemy[8],enemy_set[8]; /* ENEMIES section (2026-11-14): the enemy people of a slot's invasions, else the map's */
 int gov[8],rank[8],salary[8],savings[8],favor[8],fixed[8];
 char path[2048];long edit_offset[8];int edit_count[8],native_map[8];
 int access[64];int names[64],roles[64],sea[64],costs[64],x[64],y[64],sells[64][22],buys[64][22];
 char ids[8][32];int slot_name[8],mission[8],num_allowed[8],allowed[8][512];
} creator_layout;
static int creator_load_layout(creator_layout *d,const char *input,const char *exe){
 memset(d,0,sizeof(*d));memset(creator_event_text,0,sizeof(creator_event_text));char path[2048];snprintf(path,sizeof(path),"%s/empire-layout.txt",input);FILE *fp=fopen(path,"rb");
 if(!fp){
  if(errno!=ENOENT)return 0;snprintf(path,sizeof(path),"%s",exe);char *slash=strrchr(path,'/'),*back=strrchr(path,92);
  if(back && (!slash || back>slash))slash=back;if(!slash)return 0;slash[1]=0;
  if(strlen(path)+strlen("scenarios/capua-tarentum/empire-layout.txt")>=sizeof(path))return 0;
  strcat(path,"scenarios/capua-tarentum/empire-layout.txt");fp=fopen(path,"rb");
 }
 if(!fp)return 0;snprintf(d->path,sizeof(d->path),"%s",path);
 int valid=fscanf(fp,"%d %d %d",&d->version,&d->template_id,&d->count)==3 && d->version>=1 && d->version<=4 && d->count>=1 && d->count<=(d->version>=3?39:32);
 if(d->version<3 && d->template_id!=25)valid=0;
 if(d->version>=3 && !((d->template_id>=0 && d->template_id<=98) || (d->template_id>=1000 && d->template_id<=1098)))valid=0;
 if(d->version==1 && d->count!=7)valid=0;
 for(int n=0;n<64;n++)d->access[n]=255;
 int players=0;
 for(int n=0;valid && n<d->count;n++){
  valid=fscanf(fp,"%d %d %d %d",&d->names[n],&d->roles[n],&d->sea[n],&d->costs[n])==4;
  valid=valid && d->names[n]>0 && d->names[n]<=(d->version>=2?39:255) && (d->roles[n]==0 || d->roles[n]==1 || (d->version>=4 && d->roles[n]==2)) && (d->sea[n]==0 || d->sea[n]==1) && d->costs[n]>=0 && d->costs[n]<=1000000;
  if(d->version>=2)valid=valid && fscanf(fp,"%d %d",&d->x[n],&d->y[n])==2 && d->x[n]>=16 && d->x[n]<=1984 && d->y[n]>=16 && d->y[n]<=984;
  for(int j=0;j<n;j++)if(d->names[j]==d->names[n])valid=0;
  for(int r=1;r<=21 && valid;r++)valid=fscanf(fp,"%d",&d->sells[n][r])==1 && d->sells[n][r]>=0 && d->sells[n][r]<=10000;
  for(int r=1;r<=21 && valid;r++)valid=fscanf(fp,"%d",&d->buys[n][r])==1 && d->buys[n][r]>=0 && d->buys[n][r]<=10000;
  if(d->roles[n]==1){players++;if(d->costs[n])valid=0;for(int r=1;r<=21;r++)if(d->sells[n][r] || d->buys[n][r])valid=0;}
 }
 if(valid && d->version>=2){
  valid=fscanf(fp,"%d",&d->slots)==1 && d->slots>=1 && d->slots<=(d->version>=3?8:4) && players==d->slots;
  for(int s=0;valid && s<d->slots;s++){
   valid=fscanf(fp,"%31s %d %d %d",d->ids[s],&d->slot_name[s],&d->mission[s],&d->num_allowed[s])==4 && (d->version>=3?creator_template_valid(d->mission[s]):d->mission[s]>=2 && d->mission[s]<=5) && d->num_allowed[s]>=0 && d->num_allowed[s]<512;
   for(const char *p=d->ids[s];*p;p++)if(!((*p>='a' && *p<='z') || (*p>='0' && *p<='9') || *p=='_' || *p=='-'))valid=0;
   int found=0;for(int n=0;n<d->count;n++)if(d->names[n]==d->slot_name[s] && d->roles[n]==1)found++;
   if(found!=1)valid=0;
   for(int k=0;k<s;k++)if(!strcmp(d->ids[s],d->ids[k]) || d->slot_name[s]==d->slot_name[k])valid=0;
   for(int j=0;valid && j<d->num_allowed[s];j++){
    valid=fscanf(fp,"%d",&d->allowed[s][j])==1 && d->allowed[s][j]>0 && d->allowed[s][j]<BUILDING_TYPE_MAX;
    for(int k=0;k<j;k++)if(d->allowed[s][j]==d->allowed[s][k])valid=0;
   }
  }
 }else if(players!=2)valid=0;
 if(valid && d->version>=3){char tag[16];valid=fscanf(fp,"%15s %d",tag,&d->starting_funds)==2 && !strcmp(tag,"START") && d->starting_funds>=0 && d->starting_funds<=1000000;}
 char extra;
 if(valid && d->version>=2 && fscanf(fp," %c",&extra)!=EOF){
  ungetc(extra,fp);char tag[16];int sections=0;
  valid=fscanf(fp,"%15s %d",tag,&sections)==2 && !strcmp(tag,"TERRAIN") && sections==d->slots;
  int seen[8]={0};
  for(int k=0;valid && k<sections;k++){
   char id[32];int count;valid=fscanf(fp,"%31s %d",id,&count)==2 && count>=0 && count<=25600;int slot=-1;if(!valid)break;
   for(int j=0;j<d->slots;j++)if(!strcmp(id,d->ids[j]))slot=j;
   if(slot<0 || seen[slot]){valid=0;break;}seen[slot]=1;d->edit_count[slot]=count;d->edit_offset[slot]=ftell(fp);
   unsigned char tiles[25600]={0};
   for(int j=0;valid && j<count;j++){int x,y,kind;valid=fscanf(fp,"%d %d %d",&x,&y,&kind)==3 && x>=0 && y>=0 && x<160 && y<160 && kind>=0 && kind<=2;if(valid){int n=y*160+x;if(tiles[n])valid=0;tiles[n]=1;}}
  }
  if(valid && d->version>=4){
   int maps=0;valid=fscanf(fp,"%15s %d",tag,&maps)==2 && !strcmp(tag,"MAPS") && maps>=0 && maps<=d->slots;
   for(int j=0;valid && j<maps;j++){
    char id[32];valid=fscanf(fp,"%31s",id)==1;int slot=-1;
    for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(slot<0 || d->native_map[slot])valid=0;else d->native_map[slot]=1;
   }
  }
  if(valid && d->version>=4 && fscanf(fp," %c",&extra)!=EOF){
   ungetc(extra,fp);int count;valid=fscanf(fp,"%15s %d",tag,&count)==2 && !strcmp(tag,"ACCESS") && count==d->count;
   for(int n=0;valid && n<count;n++){int name,mask;valid=fscanf(fp,"%d %d",&name,&mask)==2 && name==d->names[n] && mask>=0 && mask<(1<<d->slots);if(valid)d->access[n]=mask;}
  }
  if(valid && d->version>=4 && fscanf(fp," %c",&extra)!=EOF){
   ungetc(extra,fp);int count;valid=fscanf(fp,"%15s %d",tag,&count)==2 && !strcmp(tag,"GOVERNANCE") && count>=0 && count<=d->slots;
   for(int n=0;valid && n<count;n++){
    char id[32];int rank,salary,savings,favor,fixed;
    valid=fscanf(fp,"%31s %d %d %d %d %d",id,&rank,&salary,&savings,&favor,&fixed)==6;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || d->gov[slot] || rank<0 || rank>10 || salary< -1 || salary>10 || savings<0 || savings>1000000 || favor<0 || favor>100 || fixed<0 || fixed>1){valid=0;break;}
    d->gov[slot]=1;d->rank[slot]=rank;d->salary[slot]=salary;d->savings[slot]=savings;d->favor[slot]=favor;d->fixed[slot]=fixed;
   }
  }
  if(valid && d->version>=4 && fscanf(fp," %c",&extra)!=EOF){
   ungetc(extra,fp);int count;valid=fscanf(fp,"%15s %d",tag,&count)==2 && !strcmp(tag,"EVENTS") && count>=0 && count<=8*CREATOR_EVENTS;
   for(int n=0;valid && n<count;n++){
    char id[32];creator_city_event e;e.cond=e.cond_value=e.repeat_every=e.repeat_times=0;valid=fscanf(fp,"%31s %d %d %d %d %d",id,&e.kind,&e.month,&e.amount,&e.resource,&e.deadline)==6;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || d->event_count[slot]>=CREATOR_EVENTS || e.kind<0 || e.kind>9 || e.month<1 || e.month>1200){valid=0;break;}
    if((e.kind==0 && (e.amount<1 || e.amount>1000000)) || (e.kind==1 && (!e.amount || e.amount< -100 || e.amount>100)) || (e.kind==2 && (e.amount<1 || e.amount>10000 || e.resource<1 || e.resource>21 || e.deadline<1 || e.deadline>20))
       || (e.kind==3 && (e.amount<1 || e.amount>2 || e.resource<1 || e.resource>=BUILDING_TYPE_MAX)) || (e.kind==4 && (e.amount<1 || e.amount>3 || e.resource<1 || e.resource>5))
       || (e.kind==5 && (!e.amount || e.amount< -1000 || e.amount>1000 || e.resource<1 || e.resource>21)) || (e.kind==6 && (!e.amount || e.amount< -100 || e.amount>100))
       || (e.kind==7 && (e.amount<10 || e.amount>400 || e.amount==100 || e.deadline<1 || e.deadline>120)) || ((e.kind==8 || e.kind==9) && e.amount!=1)
       || (e.kind!=2 && e.kind!=3 && e.kind!=4 && e.kind!=5 && e.resource) || (e.kind!=2 && e.kind!=7 && e.deadline) || ((e.kind==1 || e.kind==2) && d->gov[slot] && d->fixed[slot])){valid=0;break;}
    d->events[slot][d->event_count[slot]++]=e;
   }
  }
  if(valid && d->version>=4 && fscanf(fp," %c",&extra)!=EOF){
   ungetc(extra,fp);int count;valid=fscanf(fp,"%15s %d",tag,&count)==2 && !strcmp(tag,"INVASIONS") && count>=0 && count<=128;
   for(int n=0;valid && n<count;n++){
    char id[32];creator_city_invasion e;valid=fscanf(fp,"%31s %d %d %d %d",id,&e.month,&e.amount,&e.point,&e.target)==5;e.enemy=-1;e.repeat_every=e.repeat_times=0;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || d->invasion_count[slot]>=16 || e.month<1 || e.month>1200 || e.amount<5 || e.amount>150 || e.point<0 || e.point>8 || e.target<0 || e.target>4){valid=0;break;}
    d->invasions[slot][d->invasion_count[slot]++]=e;
   }
  }
  /* Optional tail sections, in this order: YEAR, FUNDS, ENEMIES, RAIDERS. A layout without them is read as before. */
  int tail_count=-1;tag[0]=0;
  if(valid && d->version>=4 && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  if(valid && !strcmp(tag,"YEAR")){   /* "YEAR <year>": the number is the year itself, no rows follow */
   valid=tail_count>=-500 && tail_count<=300 && tail_count!=0;d->start_year=tail_count;d->start_year_set=1;
   tag[0]=0;if(valid && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  }
  if(valid && !strcmp(tag,"FUNDS")){
   int count=tail_count;valid=count>=1 && count<=d->slots;
   for(int n=0;valid && n<count;n++){
    char id[32];int amount;valid=fscanf(fp,"%31s %d",id,&amount)==2;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || d->slot_funds_set[slot] || amount<0 || amount>1000000){valid=0;break;}
    d->slot_funds[slot]=amount;d->slot_funds_set[slot]=1;
   }
  }
  if(valid && !strcmp(tag,"FUNDS")){tag[0]=0;if(fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}}
  if(valid && !strcmp(tag,"ENEMIES")){
   int count=tail_count;valid=count>=1 && count<=d->slots;
   for(int n=0;valid && n<count;n++){
    char id[32];int enemy;valid=fscanf(fp,"%31s %d",id,&enemy)==2;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || d->enemy_set[slot] || enemy<0 || enemy>19){valid=0;break;}
    d->enemy[slot]=enemy;d->enemy_set[slot]=1;
   }
   tag[0]=0;if(valid && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  }
  if(valid && !strcmp(tag,"RAIDERS")){   /* attacks with their own enemy people (2026-11-15): "<slot> <index> <people>" */
   int count=tail_count;valid=count>=1 && count<=128;
   for(int n=0;valid && n<count;n++){
    char id[32];int index,enemy;valid=fscanf(fp,"%31s %d %d",id,&index,&enemy)==3;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || index<0 || index>=d->invasion_count[slot] || d->invasions[slot][index].enemy>=0 || enemy<0 || enemy>19){valid=0;break;}
    d->invasions[slot][index].enemy=enemy;
   }
   tag[0]=0;if(valid && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  }
  if(valid && !strcmp(tag,"EVENTTEXT")){   /* city event messages (2026-11-15): "<slot> <index> <UTF-8 hex>" */
   int count=tail_count;valid=count>=1 && count<=8*CREATOR_EVENTS;static char hex[2*CREATOR_EVENT_TEXT+2];   /* every event may have a text */
   for(int n=0;valid && n<count;n++){
    char id[32];int index;valid=fscanf(fp,"%31s %d %1217s",id,&index,hex)==3;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    size_t len=valid?strlen(hex):0;
    if(!valid || slot<0 || index<0 || index>=d->event_count[slot] || len<2 || len%2 || len/2>=CREATOR_EVENT_TEXT || creator_event_text[slot][index][0]){valid=0;break;}
    for(size_t k=0;k<len/2;k++){unsigned v;if(sscanf(hex+2*k,"%2x",&v)!=1 || !v){valid=0;break;}creator_event_text[slot][index][k]=(char)v;}
    if(valid)creator_event_text[slot][index][len/2]=0;
   }
   tag[0]=0;if(valid && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  }
  if(valid && !strcmp(tag,"EVENTCOND")){   /* events that wait for the city (2026-11-15): "<slot> <index> <stat 1..6> <value>" */
   int count=tail_count;valid=count>=1 && count<=8*CREATOR_EVENTS;
   for(int n=0;valid && n<count;n++){
    char id[32];int index,type,value;valid=fscanf(fp,"%31s %d %d %d",id,&index,&type,&value)==4;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || index<0 || index>=d->event_count[slot] || d->events[slot][index].cond || type<1 || type>6 || value<1 || value>(type==1?1000000:type==5?1000000000:100)){valid=0;break;}
    d->events[slot][index].cond=type;d->events[slot][index].cond_value=value;
   }
   tag[0]=0;if(valid && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  }
  if(valid && !strcmp(tag,"EVENTREPEAT")){   /* a waiting event that repeats (2026-11-15): "<slot> <index> <every months 1..240> <times 2..24>",
                                                the game's own repeat: `every` months after it happened, when the city still qualifies */
   int count=tail_count;valid=count>=1 && count<=8*CREATOR_EVENTS;
   for(int n=0;valid && n<count;n++){
    char id[32];int index,every,times;valid=fscanf(fp,"%31s %d %d %d",id,&index,&every,&times)==4;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || index<0 || index>=d->event_count[slot] || !d->events[slot][index].cond || d->events[slot][index].repeat_every || d->events[slot][index].kind==7 || every<1 || every>240 || times<2 || times>24){valid=0;break;}
    d->events[slot][index].repeat_every=every;d->events[slot][index].repeat_times=times;
   }
   tag[0]=0;if(valid && fscanf(fp," %c",&extra)!=EOF){ungetc(extra,fp);valid=fscanf(fp,"%15s %d",tag,&tail_count)==2;}
  }
  if(valid && !strcmp(tag,"INVREPEAT")){   /* an attack that comes again (2026-11-15): "<slot> <index> <every months 1..240> <times 2..24>",
                                              the game's own repeat of the attack's event: `every` months after each attack */
   int count=tail_count;valid=count>=1 && count<=128;
   for(int n=0;valid && n<count;n++){
    char id[32];int index,every,times;valid=fscanf(fp,"%31s %d %d %d",id,&index,&every,&times)==4;
    int slot=-1;for(int k=0;k<d->slots;k++)if(!strcmp(id,d->ids[k]))slot=k;
    if(!valid || slot<0 || index<0 || index>=d->invasion_count[slot] || d->invasions[slot][index].repeat_every || every<1 || every>240 || times<2 || times>24){valid=0;break;}
    d->invasions[slot][index].repeat_every=every;d->invasions[slot][index].repeat_times=times;
   }
   tag[0]=0;
  }
  if(valid && tag[0])valid=0; /* an unknown or misplaced section */
  if(valid && fscanf(fp," %c",&extra)!=EOF)valid=0;
 }else if(valid && d->version==1 && fscanf(fp," %c",&extra)!=EOF)valid=0;
 fclose(fp);return valid;
}
static int creator_slot(const creator_layout *d,const char *mode){
 if(strncmp(mode,"start-",6))return -1;
 for(int i=0;i<d->slots;i++)if(!strcmp(mode+6,d->ids[i]))return i;return -1;
}
int worker_campaign_mission(const char *mode,const char *input,const char *exe){
 int preset=creator_template_from_mode(mode);if(preset!=-1)return preset;
 if(strncmp(mode,"start-",6))return -1;
 creator_layout d;if(!creator_load_layout(&d,input,exe))return -2;
 if(d.version==1)return !strcmp(mode,"start-capua")?2:!strcmp(mode,"start-tarentum")?3:-2;
 int i=creator_slot(&d,mode);return i>=0?d.mission[i]:-2;
}
static int build_shared_empire(int own_name,const char *input,const char *exe){
 creator_layout d;if(!creator_load_layout(&d,input,exe))return 0;
 int own_count=0;for(int n=0;n<d.count;n++)if(d.roles[n]==1 && d.names[n]==own_name)own_count++;if(own_count!=1)return 0;
 int own_slot=0;for(int s=0;s<d.slots;s++)if(d.slot_name[s]==own_name)own_slot=s;
 int production[RESOURCE_MAX]={0};
 for(int i=0;i<empire_city_get_array_size();i++){
  empire_city *c=empire_city_get(i);if(c->in_use && c->type==EMPIRE_CITY_OURS)memcpy(production,empire_object_get_full(c->empire_object_id)->city_sells_resource,sizeof(production));
 }
 if(d.version>=3){
  for(int r=RESOURCE_MIN;r<RESOURCE_MAX;r++){
   if(!resource_is_food(r) && !resource_is_raw_material(r))continue;
   int industry=resource_get_data(r)->industry;production[r]=0;
   for(int k=0;k<d.num_allowed[own_slot];k++)if(d.allowed[own_slot][k]==industry){production[r]=1;break;}
  }
 }
 empire_load(d.template_id>=1000,d.template_id%1000);
 full_empire_object templates[64],fallback;int have_fallback=0;
 for(int i=0;i<empire_object_count();i++){
  full_empire_object *f=empire_object_get_full(i);if(f->in_use && f->obj.type==EMPIRE_OBJECT_CITY){fallback=*f;have_fallback=1;break;}
 }
 if(!have_fallback)return 0;
 for(int n=0;n<d.count;n++){
  int found=0;
  for(int i=0;i<empire_object_count();i++){
   full_empire_object *f=empire_object_get_full(i);if(f->in_use && f->obj.type==EMPIRE_OBJECT_CITY && f->city_name_id==d.names[n]){templates[n]=*f;found=1;break;}
  }
  if(!found){if(d.version==1)return 0;templates[n]=fallback;}
 }
 empire_object_clear();scenario.empire.id=SCENARIO_CUSTOM_EMPIRE;scenario.empire.is_expanded=0;scenario.empire.expansion_year=0;
 for(int n=0;n<d.count;n++){
  full_empire_object *f=empire_object_get_new();if(!f)return 0;unsigned int id=f->obj.id;*f=templates[n];f->obj.id=id;f->city_name_id=d.names[n];
  if(d.version>=2){f->obj.x=d.x[n]-16;f->obj.y=d.y[n]-16;}
  f->obj.parent_object_id=0;f->obj.order_index=0;f->obj.trade_route_id=0;
  int reserved=d.roles[n]==2;
  int denied=reserved || (!d.roles[n] && !(d.access[n] & (1<<own_slot)));
  f->city_type=d.names[n]==own_name?EMPIRE_CITY_OURS:reserved?EMPIRE_CITY_FUTURE_ROMAN:denied?EMPIRE_CITY_DISTANT_FOREIGN:EMPIRE_CITY_TRADE;f->trade_route_open=0;f->trade_route_cost=d.costs[n];f->route_hidden=0;
  memset(f->city_sells_resource,0,sizeof(f->city_sells_resource));memset(f->city_buys_resource,0,sizeof(f->city_buys_resource));memset(f->route_resource_cost,0,sizeof(f->route_resource_cost));
  f->empire_city_icon=f->obj.empire_city_icon=f->city_type==EMPIRE_CITY_OURS?EMPIRE_CITY_ICON_OUR_CITY:EMPIRE_CITY_ICON_TRADE_CITY;f->obj.image_id=empire_city_get_icon_image_id(f->empire_city_icon);
  if(f->city_type==EMPIRE_CITY_OURS)memcpy(f->city_sells_resource,production,sizeof(production));
  else if(!denied)for(int r=1;r<=21;r++){f->city_sells_resource[r]=d.sells[n][r];f->city_buys_resource[r]=d.buys[n][r];}
  if(f->city_type==EMPIRE_CITY_TRADE){
   int x=f->obj.x,y=f->obj.y;full_empire_object *route=empire_object_get_new();if(!route)return 0;
   route->in_use=1;route->obj.type=d.sea[n]?EMPIRE_OBJECT_SEA_TRADE_ROUTE:EMPIRE_OBJECT_LAND_TRADE_ROUTE;route->obj.parent_object_id=id;route->obj.x=x;route->obj.y=y;
   route->obj.image_id=image_group(d.sea[n]?GROUP_EMPIRE_TRADE_SEA:GROUP_EMPIRE_TRADE_LAND);route->obj.width=32;route->obj.height=20;
  }
 }
 empire_object_init_cities(SCENARIO_CUSTOM_EMPIRE);
 for(int n=0;n<d.count;n++)if(d.roles[n]==1 && d.names[n]!=own_name && !empire_city_reserve_for_player(d.names[n]))return 0;
 empire_clear_selected_object();empire_center_on_our_city(768,448);return 1;
}
#include "creator_city_events.h"
#include "creator_city_invasions.h"
static int creator_start_profile(const char *mode,const char *input,const char *exe){
 creator_layout d;if(!creator_load_layout(&d,input,exe))return 0;
 if(d.version==1)return build_shared_empire(!strcmp(mode,"start-capua")?2:1,input,exe);
 int s=creator_slot(&d,mode);if(s<0)return 0;
 if(d.native_map[s]){
  char map[2048];snprintf(map,sizeof(map),"%s/maps/%s.mapx",input,d.ids[s]);
  if(!creator_load_native_map(map))return 0;
 }
 if(!build_shared_empire(d.slot_name[s],input,exe))return 0;
 if(d.version>=3)creator_reset_mission(d.slot_funds_set[s]?d.slot_funds[s]:d.starting_funds);
 if(d.gov[s]){
  scenario.player_rank=d.rank[s];scenario.settings.starting_personal_savings=d.savings[s];scenario.settings.starting_favor=d.favor[s];
  /* 0 = original, 1 = original open-play reset to 50, 2 = authored fixed favor. Stored in existing SAV field. */
  scenario.reset_favour_monthly=d.fixed[s]?2:0;
  city_data.emperor.player_rank=d.rank[s];city_data.emperor.personal_savings=d.savings[s];
  city_emperor_set_salary_rank(d.salary[s]<0?d.rank[s]:d.salary[s]);
  city_data.ratings.favor=city_data.ratings.favor_last_year=d.favor[s];
 }
 scenario.start_year=d.start_year_set?d.start_year:-350;
 if(d.start_year_set){game_time_init(scenario.start_year);scenario_criteria_init_max_year();}   /* as creator_reset_mission does for -350 */
 if(!creator_install_events(d.events[s],d.event_count[s],creator_event_text[s]))return 0;
 scenario_allowed_building_disable_all();
 for(int i=0;i<d.num_allowed[s];i++)scenario_allowed_building_set(d.allowed[s][i],1);
 building_menu_update();if(!creator_apply_terrain(d.path,d.edit_offset[s],d.edit_count[s]))return 0;
 if(d.enemy_set[s])scenario.enemy_id=d.enemy[s]; /* saved with the city; the game loads this people's pictures */
 return creator_install_invasions(d.invasions[s],d.invasion_count[s]);
}
