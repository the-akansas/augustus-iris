#ifndef CREATOR_CITY_INVASIONS_H
#define CREATOR_CITY_INVASIONS_H
#include "scenario/invasion.h"
#include "map/grid.h"
#include "map/terrain.h"

static int creator_invasion_point_valid(map_point p){
 if(p.x<0 || p.y<0 || p.x>=map_grid_width() || p.y>=map_grid_height())return 0;
 int off=map_grid_offset(p.x,p.y);
 if(map_terrain_is(off,TERRAIN_ELEVATION|TERRAIN_ROCK|TERRAIN_TREE))return 0;
 if(map_terrain_is(off,TERRAIN_WATER) && !map_terrain_is(off,TERRAIN_ROAD))return 0;
 return 1;
}
static int creator_install_invasions(const creator_city_invasion *spec,int count){
 /* Every attack names its people (2026-11-15): its own (RAIDERS) or the city's at the start. The game switches the
  * pictures when a different people comes (scenario/invasion.c), so an attack without one must not take whatever
  * people came last. */
 int base=scenario.enemy_id;if(base<0 || base>19)base=0;
 for(int i=0;i<count;i++){
  const creator_city_invasion *s=&spec[i];int point=s->point-1;
  if(!s->point){
   for(int j=0;j<MAX_INVASION_POINTS;j++)if(creator_invasion_point_valid(scenario.invasion_points[j])){point=j;break;}
   if(point<0 && creator_invasion_point_valid(scenario.exit_point)){
    /* Only fill an unused marker; preserve authored markers even if blocked. */
    for(int j=0;j<MAX_INVASION_POINTS;j++)if(scenario.invasion_points[j].x<0){scenario.invasion_points[j]=scenario.exit_point;point=j;break;}
   }
  }
  if(point<0 || point>=MAX_INVASION_POINTS || !creator_invasion_point_valid(scenario.invasion_points[point])){
   fprintf(stderr,"Creator invasion rejected: event %d point %d\n",i+1,s->point);return 0;
  }
  scenario_event_t *e=scenario_event_create(0,0,1);if(!e)return 0;
  snprintf((char*)e->name,sizeof(e->name),"City invasion %d",i+1);
  scenario_condition_group_t *g;array_new_item(e->condition_groups,g);if(!g)return 0;
  scenario_condition_t *c=scenario_event_condition_create(g,CONDITION_TYPE_TIME_PASSED);if(!c)return 0;
  c->parameter1=COMPARISON_TYPE_EQUAL_OR_MORE;c->parameter2=creator_event_constant(s->month);if(!c->parameter2)return 0;
  scenario_action_t *a=scenario_event_action_create(e,ACTION_TYPE_INVASION_IMMEDIATE);if(!a)return 0;
  a->parameter1=INVASION_TYPE_ENEMY_ARMY;a->parameter2=creator_event_constant(s->amount);
  a->parameter3=creator_event_constant(point+1);a->parameter4=s->target;a->parameter5=s->enemy>=0 && s->enemy<=19?s->enemy:base;
  if(!a->parameter2 || !a->parameter3)return 0;
  /* INVREPEAT: the attack comes again `every` months (16 days each) after the last one, `times` attacks in all
     (scenario/event/event.c repeat; the condition "at least N months passed" stays true) */
  if(s->repeat_every){e->repeat_days_min=e->repeat_days_max=s->repeat_every*16;e->max_number_of_repeats=s->repeat_times;}
  scenario_event_init(e);
 }
 return 1;
}
static int creator_export_military(const char *out){
 char path[2048];snprintf(path,sizeof(path),"%s/military-audit.json",out);FILE *f=fopen(path,"w");if(!f)return 0;
 fprintf(f,"{\"enemy_template\":%d,\"points\":[",scenario.enemy_id);
 for(int i=0;i<MAX_INVASION_POINTS;i++)fprintf(f,"%s[%d,%d]",i?",":"",scenario.invasion_points[i].x,scenario.invasion_points[i].y);
 fputs("],\"formations\":[",f);int first=1;
 for(int i=1;i<formation_count();i++){
  const formation *m=formation_get(i);if(!m->in_use || m->is_herd)continue;
  int alive=0;for(unsigned j=1;j<figure_count();j++){const figure *v=figure_get(j);if(v->state && v->formation_id==i)alive++;}
  fprintf(f,"%s{\"id\":%u,\"legion\":%d,\"morale\":%d,\"months_from_home\":%d,\"soldiers\":%d,\"enemy_type\":%d,\"target\":%d,\"x\":%d,\"y\":%d,\"sequence\":%d}",first?"":",",m->id,m->is_legion,m->morale,m->months_from_home,alive,m->enemy_type,m->attack_type,m->x,m->y,m->invasion_sequence);first=0;
 }
 fputs("]}",f);return fclose(f)==0;
}
#endif
