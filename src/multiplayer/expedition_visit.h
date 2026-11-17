/* Native visiting troops: original unit properties, separate city-local IDs.
 * This worker changes private snapshots only. Server publication needs a paired
 * transaction and both installation acknowledgements. */
#ifndef EXPEDITION_VISIT_H
#define EXPEDITION_VISIT_H
#include "city/map.h"
#include "figure/enemy_army.h"
#include "figuretype/soldier.h"
#include "map/terrain.h"
#include "map/routing.h"
#include "building/building.h"
#include "building/type.h"
static int expedition_visit(const char *input, int remove_visit)
{
 char path[2048];snprintf(path,sizeof(path),"%s/visitor.txt",input);
 FILE *f=fopen(path,"r");if(!f)return 0;
 unsigned token;int role,type,morale,trained,months,food,n;
 int damage[16],names[16];
 int valid=fscanf(f,"VIS1 %u %d %d %d %d %d %d %d",&token,&role,&type,&morale,&trained,&months,&food,&n)==8;
 valid=valid && token && (role==1 || role==2) && (type==11 || type==12 || type==13 || type==92 || type==94)
  && morale>=0 && morale<=105 && trained>=0 && trained<=1 && months>=0 && months<=255 && food>=-30 && food<=15 && n>=0 && n<=16;
 for(int i=0;valid && i<n;i++)valid=fscanf(f,"%d %d",&damage[i],&names[i])==2 && damage[i]>=0 && damage[i]<=figure_properties_for_type(type)->max_damage && names[i]>=-32768 && names[i]<=32767;
 char extra;if(valid && fscanf(f," %c",&extra)!=EOF)valid=0;fclose(f);if(!valid)return 0;
 int existing=0;
 for(int i=1;i<formation_count();i++){
  formation *m=formation_get(i);
  if(m->in_use && m->mp_expedition_role){
   if(m->mp_expedition_id==token){if(existing)return 0;existing=i;}
   if(!remove_visit && m->mp_expedition_id==token)return 0; /* Different expeditions coexist; tokens remain unique. */
  }
 }
 if(remove_visit){
  if(!existing)return 0;
  formation *m=formation_get(existing);
  if(m->mp_expedition_role!=role || m->figure_type!=type)return 0;
  for(unsigned i=1;i<figure_count();i++){
   figure *v=figure_get(i);if(v->formation_id==(unsigned)existing && v->state==FIGURE_STATE_ALIVE)figure_delete(v);
  }
  m=formation_get(existing);m->mp_expedition_id=0;m->mp_expedition_role=0;formation_clear(existing);
  formation_calculate_figures();return 1;
 }
 if(!n)return 0;
 /* Spawn on a real clear tile near the map entrance, without repainting terrain. */
 const map_tile *entry=city_map_entry_point();int x=-1,y=-1;
 for(int d=0;d<=24 && x<0;d++)for(int dy=-d;dy<=d && x<0;dy++)for(int dx=-d;dx<=d;dx++){
  int tx=entry->x+dx,ty=entry->y+dy;
  if(map_grid_is_inside(tx,ty,1) && !map_terrain_is(map_grid_offset(tx,ty),TERRAIN_IMPASSABLE)){x=tx;y=ty;break;}
 }
 if(x<0)return 0;
 if(role==1){
  /* Support waits in the middle of the homes it came to defend, so an attack from any
   * side is about equally far; the map entrance corner left it out of every fight. */
  long sx=0,sy=0;int homes=0;
  for(unsigned i=1;i<building_count();i++){const building*b=building_get(i);
   if(b->state==BUILDING_STATE_IN_USE && building_is_house(b->type) && b->house_size){sx+=b->x;sy+=b->y;homes++;}}
  if(homes){
   int cx=(int)(sx/homes),cy=(int)(sy/homes),found=0;
   for(int d=0;d<=40 && !found;d++)for(int dy=-d;dy<=d && !found;dy++)for(int dx=-d;dx<=d;dx++){
    if(dx>-d && dx<d && dy>-d && dy<d)continue; /* ring by ring, nearest first */
    int tx=cx+dx,ty=cy+dy;
    if(map_grid_is_inside(tx,ty,1) && !map_terrain_is(map_grid_offset(tx,ty),TERRAIN_IMPASSABLE) &&
       map_routing_citizen_can_travel_over_land(entry->x,entry->y,tx,ty,8,0)){x=tx;y=ty;found=1;break;}
   }
  }
 }
 int invasion=0;
 for(int j=1;j<MAX_ENEMY_ARMIES && !invasion;j++){
  int used=0;for(int i=1;i<formation_count();i++){formation *m=formation_get(i);if(m->in_use && !m->is_herd && (!m->is_legion || m->mp_expedition_role) && m->invasion_id==j){used=1;break;}}
  if(!used)invasion=j;
 }
 if(!invasion)return 0;
 enemy_army_clear(invasion);
 int id=formation_create_enemy(type,x,y,FORMATION_COLUMN,DIR_0_TOP,0,FORMATION_ATTACK_TROOPS,invasion,0);
 if(!id)return 0;
 formation *m=formation_get(id);
 m->mp_expedition_id=token;m->mp_expedition_role=role;m->is_legion=role==1;m->faction_id=role==1;
 m->morale=morale;m->has_military_training=trained;m->months_from_home=months;m->mess_hall_max_morale_modifier=food;
 m->standard_x=m->x_home=m->destination_x=x;m->standard_y=m->y_home=m->destination_y=y;
 m->layout=role==1?FORMATION_MOP_UP:FORMATION_COLUMN;m->max_figures=16;m->is_at_fort=0;
 if(role==1)m->prev.layout=FORMATION_DOUBLE_LINE_1; /* arrives on automatic defence (mop up); the host may change it */
 /* The remote formation has already arrived; skip the invasion regroup countdown. */
 if(role==2)m->wait_ticks=32;
 int px[16],py[16];
 for(int i=0;i<n;i++){
  px[i]=x;py[i]=y;
  if(role==1){
   int found=0;
   for(int d=0;d<=24 && !found;d++)for(int dy=-d;dy<=d && !found;dy++)for(int dx=-d;dx<=d;dx++){
    int tx=x+dx,ty=y+dy,used=0;for(int j=0;j<i;j++)if(px[j]==tx && py[j]==ty)used=1;
    if(!used && map_grid_is_inside(tx,ty,1) && !map_terrain_is(map_grid_offset(tx,ty),TERRAIN_IMPASSABLE)){px[i]=tx;py[i]=ty;found=1;break;}
   }
   if(!found){for(unsigned j=1;j<figure_count();j++)if(figure_get(j)->formation_id==(unsigned)id && !figure_is_dead(figure_get(j)))figure_delete(figure_get(j));formation_get(id)->mp_expedition_id=0;formation_get(id)->mp_expedition_role=0;formation_clear(id);formation_calculate_figures();return 0;}
  }
  figure *v=army_allocate(type,px[i],py[i],DIR_0_TOP);if(!v->id){for(unsigned j=1;j<figure_count();j++)if(figure_get(j)->formation_id==(unsigned)id && !figure_is_dead(figure_get(j)))figure_delete(figure_get(j));formation_get(id)->mp_expedition_id=0;formation_get(id)->mp_expedition_role=0;formation_clear(id);formation_calculate_figures();return 0;}
  v->formation_id=id;v->mp_source=i+1;v->index_in_formation=i;v->damage=damage[i];v->name=names[i];
  v->action_state=role==1?FIGURE_ACTION_84_SOLDIER_AT_STANDARD:FIGURE_ACTION_151_ENEMY_INITIAL;
  /* First action runs on the following normal game tick, after commit. */
 }
 formation_calculate_figures();return 1;
}
#endif
