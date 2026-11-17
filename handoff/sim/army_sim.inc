/* Headless military logic simulation (Linux test rig only, never shipped). Appended to a copy of engine_main.c.
 * One city plays every part: its own fort legion leaves through the real mailbox (mp_army_poll, steps 1-4) and the
 * same manifest arrives here as a visiting support legion / attack force, as it would in another player's city. */
#include "figure/figure.h"
#include "figure/formation.h"
#include "figure/formation_legion.h"
#include "building/building.h"
#include "building/type.h"
#include "map/grid.h"
#include "map/terrain.h"
#include "city/map.h"
#include "game/tick.h"
#include <stdarg.h>
#include "figure/enemy_army.h"
#include "building/construction_building.h"
#include "scenario/invasion.h"
#include "multiplayer/army_live.h"
#include "multiplayer/post_city.h"
#include "city/buildings.h"
#include "city/figures.h"
#include "multiplayer/clock.h"
#include "map/routing.h"
#include "city/population.h"
#include "map/building.h"
#include "map/building_tiles.h"
#include "building/image.h"
void rig_ui_poll(void){}
static const char *SIM_DIR;static int sim_fail;
#define ROSTER "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
static void check(int ok,const char *what,const char *fmt,...){char d[512];va_list a;va_start(a,fmt);vsnprintf(d,sizeof(d),fmt,a);va_end(a);printf("%s %s | %s\n",ok?"PASS":"FAIL",what,d);if(!ok)sim_fail++;fflush(stdout);}
static void run(int n){for(int i=0;i<n;i++)game_tick_run();}
static int place(int type,int cx,int cy,int *px,int *py){
 for(int d=2;d<=60;d+=2)for(int dy=-d;dy<=d;dy+=2)for(int dx=-d;dx<=d;dx+=2){
  if(dx>-d && dx<d && dy>-d && dy<d)continue;int x=cx+dx,y=cy+dy;if(!map_grid_is_inside(x,y,8))continue;
  if(building_construction_place_building(type,x,y,1)){if(px){*px=x;*py=y;}return 1;}}
 return 0;}
static int buildings_in_use(void){int n=0;for(unsigned i=1;i<building_count();i++)if(building_get(i)->state==BUILDING_STATE_IN_USE)n++;return n;}
static int alive(int form,int *sx,int *sy,int *far,int cx,int cy,int *states){
 int n=0;long ax=0,ay=0;if(far)*far=0;
 for(unsigned i=1;i<figure_count();i++){figure*f=figure_get(i);if(f->formation_id!=(unsigned)form || figure_is_dead(f) || f->type==FIGURE_FORT_STANDARD)continue;
  n++;ax+=f->x;ay+=f->y;if(states && f->action_state<256)states[f->action_state]++;
  if(far){int d=abs(f->x-cx)>abs(f->y-cy)?abs(f->x-cx):abs(f->y-cy);if(d>*far && f->action_state!=FIGURE_ACTION_150_ATTACK)*far=d;}}
 if(n && sx){*sx=(int)(ax/n);*sy=(int)(ay/n);}return n;}
static int enemies_alive(void){int n=0;for(unsigned i=1;i<figure_count();i++){figure*f=figure_get(i);if(!figure_is_dead(f) && f->type>=FIGURE_ENEMY43_SPEAR && f->type<=FIGURE_ENEMY_CAESAR_LEGIONARY)n++;}return n;}
static int visitor(unsigned token){for(int i=1;i<formation_count();i++){formation*m=formation_get(i);if(m->in_use && m->mp_expedition_role && m->mp_expedition_id==token)return i;}return 0;}
static int seq;
/* One mailbox command, as the bridge writes it; returns applied and the receipt text. */
static int mail(unsigned token,int step,int role,int form,const char *payload,char *result){
 char path[1024],id[33];snprintf(id,sizeof(id),"%032x",++seq);
 snprintf(path,sizeof(path),"%s/army-live-request.txt",SIM_DIR);FILE*f=fopen(path,"wb");fprintf(f,"%s 0 %s %u %d %d %d\n%s",ROSTER,id,token,step,role,form,payload);fclose(f);
 mp_army_poll(SIM_DIR);
 snprintf(path,sizeof(path),"%s/army-live-response.txt",SIM_DIR);f=fopen(path,"rb");if(!f)return -1;
 char got[33];int applied=-1;char buf[4200]={0};size_t n=fread(buf,1,sizeof(buf)-1,f);fclose(f);(void)n;
 if(sscanf(buf,"%32s %d",got,&applied)!=2 || strcmp(got,id))return -1;
 char*nl=strchr(buf,'\n');strcpy(result,nl?nl+1:"");return applied;}
static int survivors_in(const char *manifest){int n=-1;unsigned t;int a,b,c,d,e,f2,g,h,i;sscanf(manifest,"EX2 %u %d %d %d %d %d %d %d %d %d %d",&t,&a,&b,&c,&d,&e,&f2,&g,&h,&i,&n);return n;}
static int depart(int form,unsigned token,int role,char *manifest){
 formation*m=formation_get(form);char payload[2048];int n=0,count=0;char ids[1500]="";
 for(unsigned i=1;i<figure_count();i++){figure*v=figure_get(i);if(v->formation_id==(unsigned)form && !figure_is_dead(v) && figure_is_legion(v)){n+=snprintf(ids+n,sizeof(ids)-n," %u %u",v->id,v->created_sequence);count++;}}
 snprintf(payload,sizeof(payload),"%d %d %d%s",m->building_id,m->figure_type,count,ids);
 return mail(token,1,role,form,payload,manifest);}
static int wait_at_rest(int form){for(int t=0;t<6000;t+=50){run(50);int ok=1,n=0;for(unsigned i=1;i<figure_count();i++){figure*v=figure_get(i);if(v->formation_id==(unsigned)form && !figure_is_dead(v) && v->type!=FIGURE_FORT_STANDARD){n++;if(v->action_state!=FIGURE_ACTION_80_SOLDIER_AT_REST)ok=0;}}if(ok && n)return t+50;}return -1;}
static int town_cx,town_cy,town_roads;
static int build_town(void){
 int cx=0,cy=0;
 /* A small town along the map's own road (buildings need road access to count as targets, as in a played city). */
 int road_x[400],road_y[400],roads=0;
 for(int ry=4;ry<map_grid_height()-4;ry++)for(int rx=6;rx<map_grid_width()-6;rx++)if(roads<400 && map_terrain_is(map_grid_offset(rx,ry),TERRAIN_ROAD)){road_x[roads]=rx;road_y[roads]=ry;roads++;}
 int lots=0,extra=0;long hx3=0,hy3=0;
 for(int r=roads/4;r<roads*3/4 && lots<24;r++)for(int side=-1;side<=1 && lots<24;side+=2){
  int tx=road_x[r],ty=road_y[r]+side,o=map_grid_offset(tx,ty);if(map_building_at(o) || map_terrain_is(o,TERRAIN_NOT_CLEAR))continue;
  building*b=building_create(BUILDING_HOUSE_SMALL_TENT,tx,ty);b->state=BUILDING_STATE_IN_USE;b->house_size=1;b->house_population=8;
  map_building_tiles_add(b->id,tx,ty,1,building_image_get(b),TERRAIN_BUILDING);city_population_add(8);lots++;hx3+=tx;hy3+=ty;}
 if(lots){cx=(int)(hx3/lots);cy=(int)(hy3/lots);}
 if(roads>8){extra+=place(BUILDING_GRANARY,road_x[roads/8],road_y[roads/8],0,0);extra+=place(BUILDING_WAREHOUSE,road_x[roads*7/8],road_y[roads*7/8],0,0);extra+=place(BUILDING_WAREHOUSE,road_x[roads/2],road_y[roads/2]+3,0,0);}
 town_cx=cx;town_cy=cy;town_roads=roads;return lots*100+extra;
}
static int army_sim(const char *dir){
 SIM_DIR=dir;int st[256];
 mp_clock_start(); /* multiplayer rules on (invaders pick any building, as in a room) */
 mp_post_city_reset();mp_army_reset();
 const map_tile*entry=city_map_entry_point();int cx=map_grid_width()/2,cy=map_grid_height()/2,x,y,fx,fy;
 int made=build_town(),lots=made/100,extra=made%100,roads=town_roads;cx=town_cx;cy=town_cy;
 place(BUILDING_MESS_HALL,cx+14,cy+14,0,0);
 int ok=place(BUILDING_FORT_LEGIONARIES,cx,cy+12,&fx,&fy);run(1700); /* road access is worked out by the monthly routine */
 building*fort=0;for(int i=(int)building_count()-1;i>0 && !fort;i--)if(building_get(i)->type==BUILDING_FORT_LEGIONARIES && building_get(i)->state!=BUILDING_STATE_UNUSED)fort=building_get(i);
 check(ok && fort && fort->formation_id && lots>=12,"setup: map, homes, stores, fort","map %dx%d entry %d,%d road tiles %d homes %d (centre %d,%d) stores %d fort at %d,%d",map_grid_width(),map_grid_height(),entry->x,entry->y,roads,lots,cx,cy,extra,fx,fy);
 if(!fort)return 1;
 int legion=fort->formation_id;formation*m=formation_get(legion);
 for(int i=0;i<16;i++){figure*f=figure_create(m->figure_type,fx-1,fy-1,DIR_0_TOP);f->formation_id=legion;f->formation_at_rest=1;f->action_state=FIGURE_ACTION_81_SOLDIER_GOING_TO_FORT;}
 formation_calculate_figures();
 int waited=wait_at_rest(legion);check(waited>0,"own legion gathers at its fort","%d ticks, %d soldiers",waited,alive(legion,0,0,0,0,0,0));
 int before_buildings=buildings_in_use();
 {int kinds[4]={BUILDING_GRANARY,BUILDING_WAREHOUSE,BUILDING_HOUSE_SMALL_TENT,BUILDING_FORT_LEGIONARIES};
  for(int k=0;k<4;k++){int n=0;for(building*b=building_first_of_type(kinds[k]);b;b=b->next_of_type){if(n<2)printf("     building type %d id %d state %d at %d,%d from_entry %d route(entry) %d route(79,20) %d terrain(entry) %x\n",kinds[k],b->id,b->state,b->x,b->y,b->distance_from_entry,map_routing_noncitizen_can_travel_through_everything(entry->x,entry->y,b->x,b->y,8),map_routing_noncitizen_can_travel_through_everything(79,20,b->x,b->y,8),map_terrain_get(entry->grid_offset));n++;}printf("     type %d count %d\n",kinds[k],n);}}

 /* ---- 1. support: leave, arrive, wait, defend, obey, go back ---- */
 char manifest[4200],receipt[4200];
 int applied=depart(legion,101,1,manifest);
 check(applied==1 && survivors_in(manifest)==16 && alive(legion,0,0,0,0,0,0)==0 && formation_get(legion)->mp_expedition_id==101,"step 1: legion leaves its fort (receipt lists 16)","applied %d listed %d left behind %d",applied,survivors_in(manifest),alive(legion,0,0,0,0,0,0));
 char again[4200];int twice=depart(legion,101,1,again);check(twice!=1,"step 1 again with a new command id is refused (already away)","applied %d",twice);
 applied=mail(101,2,1,legion,manifest,receipt);int sup=visitor(101);
 check(applied==1 && sup,"step 2: arrives as visiting support","applied %d formation %d",applied,sup);
 if(!sup)return 1;
 m=formation_get(sup);int hx=m->standard_x,hy=m->standard_y,far;
 check(m->layout==FORMATION_MOP_UP && m->is_legion && m->mp_expedition_role==1,"arrives on automatic defence (mop-up layout)","layout %d standard %d,%d (homes centre %d,%d)",m->layout,hx,hy,cx,cy);
 run(400);memset(st,0,sizeof(st));int n=alive(sup,&x,&y,&far,hx,hy,st);
 check(n==16 && far<=6 && st[FIGURE_ACTION_84_SOLDIER_AT_STANDARD]==16,"peace: waits at its standard","alive %d, farthest %d tiles, at-standard %d",n,far,st[FIGURE_ACTION_84_SOLDIER_AT_STANDARD]);
 scenario_invasion_start_from_console(INVASION_TYPE_ENEMY_ARMY,10,0);run(60);
 int foes=enemies_alive(),chased=0,fought=0,t;for(unsigned i=1;i<figure_count();i++){figure*f=figure_get(i);if(f->type>=FIGURE_ENEMY43_SPEAR && f->type<=FIGURE_ENEMY_CAESAR_LEGIONARY && f->state==FIGURE_STATE_ALIVE){printf("     invader type %d at %d,%d act %d ghost %d form %d\n",f->type,f->x,f->y,f->action_state,f->is_ghost,f->formation_id);break;}}
 for(t=0;t<12000 && enemies_alive()>0;t+=20){run(20);if(t%300==0){int ex=0,ey=0,en=0,act[256]={0},sx2=0,sy2=0,s2[256]={0};for(unsigned i=1;i<figure_count();i++){figure*f=figure_get(i);if(!figure_is_dead(f) && f->type>=FIGURE_ENEMY43_SPEAR && f->type<=FIGURE_ENEMY_CAESAR_LEGIONARY){en++;ex+=f->x;ey+=f->y;act[f->action_state]++;}}int sn=alive(sup,&sx2,&sy2,0,0,0,s2);printf("     t%-5d invaders %2d at %d,%d (march %d fight %d attack %d flee %d) | support %2d at %d,%d (standard %d mop %d attack %d)\n",t,en,en?ex/en:0,en?ey/en:0,act[153],act[154],act[150],act[148],sn,sx2,sy2,s2[84],s2[86],s2[150]);}memset(st,0,sizeof(st));alive(sup,0,0,0,0,0,st);if(st[FIGURE_ACTION_86_SOLDIER_MOPPING_UP])chased=1;if(st[FIGURE_ACTION_150_ATTACK])fought=1;}
 n=alive(sup,0,0,0,0,0,0);
 check(foes>0 && chased && enemies_alive()==0,"automatic: runs to the invaders and beats them","invaders %d, chased %d fought %d, %d ticks, invaders left %d, support alive %d",foes,chased,fought,t,enemies_alive(),n);
 run(1500);memset(st,0,sizeof(st));n=alive(sup,&x,&y,&far,hx,hy,st);
 check(n>0 && far<=6 && st[FIGURE_ACTION_84_SOLDIER_AT_STANDARD]==n,"after the fight: back at its standard","alive %d, farthest %d, at-standard %d",n,far,st[FIGURE_ACTION_84_SOLDIER_AT_STANDARD]);
 /* host moves it */
 map_tile to={hx+9,hy+7,map_grid_offset(hx+9,hy+7)};
 for(int d=0;d<12 && map_terrain_is(to.grid_offset,TERRAIN_IMPASSABLE|TERRAIN_BUILDING);d++){to.x++;to.grid_offset=map_grid_offset(to.x,to.y);}
 m=formation_get(sup);formation_legion_move_to(m,&to);
 printf("     buildings after the first invasion: %d of %d\n",buildings_in_use(),before_buildings);int moved=m->standard_x==to.x && m->standard_y==to.y;run(900);n=alive(sup,&x,&y,&far,to.x,to.y,0);
 check(moved && far<=6,"host moves the standard: the legion follows","new standard %d,%d accepted %d, farthest %d after 900 ticks",to.x,to.y,moved,far);
 /* manual: hold position */
 formation_legion_change_layout(m,FORMATION_DOUBLE_LINE_1);run(100);
 scenario_invasion_start_from_console(INVASION_TYPE_ENEMY_ARMY,8,0);run(60);foes=enemies_alive();int maxfar=0,mopping=0;
 for(t=0;t<1500;t+=20){run(20);memset(st,0,sizeof(st));alive(sup,0,0,&far,to.x,to.y,st);if(far>maxfar)maxfar=far;if(st[FIGURE_ACTION_86_SOLDIER_MOPPING_UP])mopping=1;}
 check(foes>0 && !mopping && maxfar<=8,"manual layout: holds its place, does not chase","invaders %d, mop-up seen %d, farthest from standard %d tiles (not counting men in melee), invaders left %d",foes,mopping,maxfar,enemies_alive());
 formation_legion_change_layout(m,FORMATION_MOP_UP);
 for(t=0;t<12000 && enemies_alive()>0;t+=20)run(20);
 check(enemies_alive()==0,"back to mop-up: automatic again, invaders beaten","%d ticks, support alive %d",t,alive(sup,0,0,0,0,0,0));
 run(600);n=alive(sup,0,0,0,0,0,0);
 applied=mail(101,3,1,legion,manifest,receipt);
 check(applied==1 && survivors_in(receipt)==n && !visitor(101),"step 3: sent back, receipt lists the survivors, nobody left behind","applied %d listed %d alive before %d",applied,survivors_in(receipt),n);
 { int ghosts=0;for(unsigned i=1;i<figure_count();i++){figure*f=figure_get(i);if(f->formation_id==(unsigned)sup && f->state==FIGURE_STATE_ALIVE)ghosts++;}check(!ghosts,"no soldier of the visiting formation stays on the map","%d",ghosts);}
 applied=mail(101,4,1,legion,receipt,again);m=formation_get(legion);
 check(applied==1 && alive(legion,0,0,0,0,0,0)==n && !m->mp_expedition_id && m->is_at_fort,"step 4: survivors are back in their own fort","applied %d in fort %d expected %d",applied,alive(legion,0,0,0,0,0,0),n);
 applied=mail(101,4,1,legion,receipt,again);check(applied!=1 && alive(legion,0,0,0,0,0,0)==n,"step 4 again is refused (no second set of soldiers)","applied %d in fort %d",applied,alive(legion,0,0,0,0,0,0));

 /* ---- 2. attack force: leave, arrive, act (the town is rebuilt first: the invasions above cost buildings) ---- */
 {int was=buildings_in_use();build_town();run(1700);printf("     town rebuilt for the attack part: %d -> %d buildings\n",was,buildings_in_use());}
 int guard=0;
 if(getenv("SIM_DEFEND")){ /* variant: the attacked city has its own legion at home */
  int gx,gy;if(place(BUILDING_FORT_LEGIONARIES,town_cx+6,town_cy+8,&gx,&gy) || place(BUILDING_FORT_LEGIONARIES,town_cx+20,town_cy-8,&gx,&gy) || place(BUILDING_FORT_LEGIONARIES,40,40,&gx,&gy)){building*g=0;for(int i=(int)building_count()-1;i>0 && !g;i--)if(building_get(i)->type==BUILDING_FORT_LEGIONARIES && building_get(i)->state!=BUILDING_STATE_UNUSED && building_get(i)->formation_id!=legion)g=building_get(i);
   if(g){guard=g->formation_id;formation*gm=formation_get(guard);for(int i=0;i<16;i++){figure*f=figure_create(gm->figure_type,gx-1,gy-1,DIR_0_TOP);f->formation_id=guard;f->formation_at_rest=1;f->action_state=FIGURE_ACTION_81_SOLDIER_GOING_TO_FORT;}formation_calculate_figures();wait_at_rest(guard);}}
  check(guard>0,"variant: the attacked city has a legion of its own at home","formation %d with %d soldiers",guard,guard?alive(guard,0,0,0,0,0,0):0);}
 waited=wait_at_rest(legion);int army=alive(legion,0,0,0,0,0,0);
 applied=depart(legion,202,2,manifest);
 check(waited>0 && applied==1 && survivors_in(manifest)==army,"attack: the legion leaves again","at rest after %d ticks, applied %d, listed %d",waited,applied,survivors_in(manifest));
 applied=mail(202,2,2,legion,manifest,receipt);int att=visitor(202);
 check(applied==1 && att,"attack: arrives as an attack force","applied %d formation %d",applied,att);
 if(att){
  int last_count=buildings_in_use(),retreated=0,x0=0,y0=0,x1=0,y1=0,path=0,px,py,struck=0,start=buildings_in_use(),idle_run=0,longest_idle=0;
  alive(att,&x0,&y0,0,0,0,0);px=x0;py=y0;
  printf("     attack track (every 250 ticks): tick centre alive buildings states\n");
  for(t=250;t<=7500;t+=250){run(250);memset(st,0,sizeof(st));n=alive(att,&x1,&y1,0,0,0,st);
   int step=abs(x1-px)+abs(y1-py);path+=step;px=x1;py=y1;if(st[FIGURE_ACTION_150_ATTACK])struck=1;
   if(st[89]==n && n){if(!retreated)retreated=t;}else if(step==0 && !st[FIGURE_ACTION_150_ATTACK] && buildings_in_use()==last_count){idle_run++;if(idle_run>longest_idle)longest_idle=idle_run;}else idle_run=0;
   printf("     %5d  %3d,%3d  %2d  %3d  init %d wait %d march %d fight %d attack %d flee %d |",t,x1,y1,n,buildings_in_use(),st[151],st[152],st[153],st[154],st[150],st[148]);
   for(int q=0;q<256;q++)if(st[q] && (q<148||q>154))printf(" a%d:%d",q,st[q]);
   {formation*a=formation_get(att);figure*f0=figure_get(a->figures[0]);printf(" | home %d,%d dest %d,%d bld %d wait %d nf %d inv %d armies %d | f0 id %d st %d act %d ghost %d wt %d dir %d",a->x_home,a->y_home,a->destination_x,a->destination_y,a->destination_building_id,a->wait_ticks,a->num_figures,a->invasion_id,enemy_army_total_enemy_formations(),a->figures[0],f0->state,f0->action_state,f0->is_ghost,f0->wait_ticks,f0->direction);}
   printf("\n");
   last_count=buildings_in_use();
   if(!n || (retreated && t>=retreated+500))break;}
  if(guard){int g=alive(guard,0,0,0,0,0,0);check(g<16 || n<army,"attackers engage the city's own legion (resting in its fort)","melee seen %d, attackers %d -> %d, defenders 16 -> %d",struck,army,n,g);}
  int lost=start-buildings_in_use();formation*a=formation_get(att);
  for(unsigned i=1;i<building_count();i++){building*b=building_get(i);if(b->state==BUILDING_STATE_IN_USE)printf("     left standing: id %d type %d at %d,%d size %d fire %d damage %d\n",b->id,b->type,b->x,b->y,b->size,b->fire_risk,b->damage_risk);}
  check(path>=10,"attack force moves into the city","start %d,%d end %d,%d path %d tiles, dest %d,%d building %d",x0,y0,x1,y1,path,a->destination_x,a->destination_y,a->destination_building_id);
  check(struck || lost>0,"attack force attacks something","melee seen %d, buildings lost %d (of %d)",struck,lost,start);
  check(longest_idle<8,"attack force never stands still while there is something to attack","longest stretch without moving, fighting or a building falling: %d ticks",longest_idle*250);
  check(retreated>0,"with nothing left it withdraws to the map edge and waits (hidden) for its owner's recall","withdrawn by tick %d, buildings left %d",retreated,buildings_in_use());
  n=alive(att,0,0,0,0,0,0);applied=mail(202,3,2,legion,manifest,receipt);
  check(applied==1 && survivors_in(receipt)==n && !visitor(202),"attack: recalled, receipt lists the survivors","applied %d listed %d alive %d",applied,survivors_in(receipt),n);
  applied=mail(202,4,2,legion,receipt,again);check(applied==1 && alive(legion,0,0,0,0,0,0)==n,"attack: survivors back in their fort","applied %d in fort %d",applied,alive(legion,0,0,0,0,0,0));
 }
 { char path[1024],text[512]={0};snprintf(path,sizeof(path),"%s/army-visitors.txt",SIM_DIR);FILE*f=fopen(path,"rb");if(f){size_t k=fread(text,1,511,f);(void)k;fclose(f);}
   check(!text[0],"visitor list published to the room is empty at the end","'%s'",text);}
 printf("buildings: %d at start of the military part, %d at the end\n",before_buildings,buildings_in_use());
 printf("%s: %d failed\n",sim_fail?"SIMULATION FAILED":"SIMULATION PASSED",sim_fail);return sim_fail?1:0;
}
#undef main
int main(int argc,char **argv){
 if(argc!=4)return 90;
 SDL_setenv("SDL_VIDEODRIVER","dummy",1);SDL_setenv("SDL_RENDER_DRIVER","software",1);SDL_setenv("SDL_AUDIODRIVER","dummy",1);
 augustus_args args={0};args.data_directory=argv[1];args.force_windowed=1;setup(&args);
 while(setting_difficulty()<DIFFICULTY_NORMAL)setting_increase_difficulty();
 while(setting_difficulty()>DIFFICULTY_NORMAL)setting_decrease_difficulty();
 if(!game_campaign_load(CAMPAIGN_ORIGINAL_NAME))return 91;
 int mission=atoi(argv[3]);scenario_set_campaign_mission(mission);scenario_set_campaign_rank(mission<2?mission:2+(mission-2)/2);
 if(!creator_worker_load_template(mission))return 92;
 return army_sim(argv[2]);
}
