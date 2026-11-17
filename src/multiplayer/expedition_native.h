/* Read-only portable military description. Never copy figure/formation structs
 * between cities: IDs and routes are city-local. Fixture is test-only CLI. */
#ifndef EXPEDITION_NATIVE_H
#define EXPEDITION_NATIVE_H
#include "figure/formation_legion.h"
static int expedition_export(const char *out){
 char path[2048];snprintf(path,sizeof(path),"%s/legions.json",out);
 FILE *f=fopen(path,"w");if(!f)return 0;
 fputs("{\"version\":1,\"legions\":[",f);int first=1;
 for(int i=1;i<formation_count();i++){
  const formation *m=formation_get(i);if(!m->in_use || !m->is_legion && !m->mp_expedition_role)continue;
  fprintf(f,"%s{\"formation_id\":%u,\"fort_id\":%d,\"unit_type\":%d,\"morale\":%d,\"trained\":%d,\"months_from_home\":%d,\"months_low_morale\":%d,\"months_very_low_morale\":%d,\"food_modifier\":%d,\"at_fort\":%d,\"empire_service\":%d,\"distant_battle\":%d,\"mp_expedition_id\":%u,\"recent_fight\":%d,\"visitor_role\":%d,\"soldiers\":[",first?"":",",m->id,m->building_id,m->figure_type,m->morale,m->has_military_training,m->months_from_home,m->months_low_morale,m->months_very_low_morale,m->mess_hall_max_morale_modifier,m->is_at_fort,m->empire_service,m->in_distant_battle,m->mp_expedition_id,m->recent_fight,m->mp_expedition_role);first=0;
  int fs=1;
  for(unsigned j=1;j<figure_count();j++){
   const figure *v=figure_get(j);
   if(figure_is_dead(v) || v->formation_id!=m->id || (!figure_is_legion(v) && !m->mp_expedition_role))continue;
   fprintf(f,"%s{\"local_id\":%u,\"generation\":%u,\"type\":%u,\"damage\":%u,\"max_damage\":%d,\"x\":%u,\"y\":%u,\"action\":%u,\"at_rest\":%u,\"opponent\":%u,\"attackers\":%u,\"name\":%d,\"direction\":%d,\"image_id\":%d}",fs?"":",",v->id,v->created_sequence,v->type,v->damage,figure_properties_for_type(v->type)->max_damage,v->x,v->y,v->action_state,v->formation_at_rest,v->opponent_id,v->num_attackers,v->name,v->direction,v->image_id);fs=0;
  }
  fputs("]}",f);
 }
 fputs("]}",f);return fclose(f)==0;
}

static int expedition_fixture(int type){
 int fort_type;
 switch(type){
 case FIGURE_FORT_LEGIONARY:fort_type=BUILDING_FORT_LEGIONARIES;break;
 case FIGURE_FORT_JAVELIN:fort_type=BUILDING_FORT_JAVELIN;break;
 case FIGURE_FORT_MOUNTED:fort_type=BUILDING_FORT_MOUNTED;break;
 case FIGURE_FORT_INFANTRY:fort_type=BUILDING_FORT_AUXILIA_INFANTRY;break;
 case FIGURE_FORT_ARCHER:fort_type=BUILDING_FORT_ARCHERS;break;
 default:return 0;
 }
 building *b=building_create(fort_type,40,40);if(!b->id)return 0;int bid=b->id;
 building *ground=building_create(BUILDING_FORT_GROUND,44,40);if(!ground->id)return 0;
 b=building_get(bid);b->state=BUILDING_STATE_IN_USE;b->next_part_building_id=ground->id;
 ground->state=BUILDING_STATE_IN_USE;ground->prev_part_building_id=bid;
 formation *m=formation_create_legion(bid,type);if(!m->id)return 0;
 b=building_get(bid);b->formation_id=m->id;b->subtype.fort_figure_type=type;
 m->has_military_training=1;m->mess_hall_max_morale_modifier=15;m->morale=0;
 formation_change_morale(m,1000);m->months_from_home=3;m->months_low_morale=2;
 for(int i=0;i<16;i++){
  figure *v=figure_create(type,44,40,DIR_0_TOP);if(!v->id)return 0;
  v->formation_id=m->id;v->building_id=bid;v->formation_at_rest=1;
  v->action_state=FIGURE_ACTION_80_SOLDIER_AT_REST;v->damage=i%3;
 }
 formation_calculate_figures();return 1;
}
/* Private SAV transform. Paired ledger publication remains required. */
static int expedition_transform(const char *input,int returning){
 char path[2048];snprintf(path,sizeof(path),"%s/expedition.txt",input);
 FILE *f=fopen(path,"r");if(!f)return 0;
 unsigned token=0;
 int id=0,fort=0,type=0,morale=0,trained=0,months=0,low=0,verylow=0,food=0,n=0;
 int ids[16]={0},gen[16]={0},damage[16]={0},x[16]={0},y[16]={0},name[16]={0},dir[16]={0};
 int valid=fscanf(f,"EX2 %u %d %d %d %d %d %d %d %d %d %d",&token,&id,&fort,&type,&morale,&trained,&months,&low,&verylow,&food,&n)==11 && token>0;
 valid=valid && id>0 && id<formation_count() && fort>0 && fort<building_count() && n>=0 && n<=16 && morale>=0 && morale<=105 && trained>=0 && trained<=1 && months>=0 && months<=255 && low>=0 && low<=255 && verylow>=0 && verylow<=255 && food>=-30 && food<=15;
 int fort_type=type==11?BUILDING_FORT_JAVELIN:type==12?BUILDING_FORT_MOUNTED:type==13?BUILDING_FORT_LEGIONARIES:type==92?BUILDING_FORT_AUXILIA_INFANTRY:type==94?BUILDING_FORT_ARCHERS:0;
 valid=valid && fort_type;
 for(int i=0;valid && i<n;i++){
  valid=fscanf(f,"%d %d %d %d %d %d %d",&ids[i],&gen[i],&damage[i],&x[i],&y[i],&name[i],&dir[i])==7;
  valid=valid && ids[i]>0 && gen[i]>=0 && gen[i]<=65535 && damage[i]>=0 && damage[i]<=figure_properties_for_type(type)->max_damage && x[i]>=0 && x[i]<map_grid_width() && y[i]>=0 && y[i]<map_grid_height() && name[i]>=-32768 && name[i]<=32767 && dir[i]>=0 && dir[i]<=8;
  for(int j=0;j<i;j++)if(ids[j]==ids[i])valid=0;
 }
 char extra;if(valid && fscanf(f," %c",&extra)!=EOF)valid=0;fclose(f);
 if(!valid)return 0;
 formation *m=formation_get(id);building *b=building_get(fort);
 if(!m->in_use || !m->is_legion || m->building_id!=fort || m->figure_type!=type || b->state!=BUILDING_STATE_IN_USE || b->type!=fort_type)return 0;
 int alive=0;for(unsigned i=1;i<figure_count();i++){figure *v=figure_get(i);if(v->state==FIGURE_STATE_ALIVE && v->formation_id==(unsigned)id && figure_is_legion(v))alive++;}
 if(returning){
  if(alive || m->mp_expedition_id!=token || m->in_distant_battle || m->empire_service)return 0;
 }else{
  if(m->mp_expedition_id || !n || alive!=n || !m->is_at_fort || m->in_distant_battle || m->empire_service || m->recent_fight || m->morale!=morale || m->has_military_training!=trained || m->months_from_home!=months || m->months_low_morale!=low || m->months_very_low_morale!=verylow || m->mess_hall_max_morale_modifier!=food)return 0;
  for(int i=0;i<n;i++){
   if((unsigned)ids[i]>=figure_count())return 0;figure *v=figure_get(ids[i]);
   if(v->state!=FIGURE_STATE_ALIVE || v->formation_id!=(unsigned)id || v->type!=type || v->created_sequence!=gen[i] || v->damage!=damage[i] || v->x!=x[i] || v->y!=y[i] || v->name!=name[i] || v->direction!=dir[i] || !v->formation_at_rest || v->action_state!=80 || v->opponent_id || v->num_attackers)return 0;
  }
 }
 /* All validation precedes edits. Allocation failure discards this process's
  * output; engine_worker writes no final SAV unless this function succeeds. */
 if(returning){
  for(int i=0;i<n;i++){
   figure *v=army_allocate(type,x[i],y[i],dir[i]);if(!v->id){for(unsigned j=1;j<figure_count();j++)if(figure_get(j)->formation_id==(unsigned)id && !figure_is_dead(figure_get(j)))figure_delete(figure_get(j));formation_calculate_figures();return 0;}
   v->formation_id=id;v->building_id=fort;v->formation_at_rest=1;
   v->action_state=FIGURE_ACTION_80_SOLDIER_AT_REST;v->damage=damage[i];v->name=name[i];
  }
 }else for(int i=0;i<n;i++)figure_delete(figure_get(ids[i]));
 formation_calculate_figures();m=formation_get(id);
 m->morale=morale;m->has_military_training=trained;m->months_from_home=months;
 m->months_low_morale=low;m->months_very_low_morale=verylow;m->mess_hall_max_morale_modifier=food;
 m->mp_expedition_id=returning?0:token;m->is_at_fort=returning;m->legion_recruit_type=LEGION_RECRUIT_NONE;
 return 1;
}
#endif
