/* Loaded SAV only: change peer ownership without rebuilding the empire or city. */
static int creator_expand_roster(const char *input,const char *exe,int own_name)
{
 creator_layout d;if(!creator_load_layout(&d,input,exe) || d.version<2)return 0;
 int ours=0;
 for(int i=0;i<empire_city_get_array_size();i++){
  empire_city *c=empire_city_get(i);
  if(c->in_use && c->type==EMPIRE_CITY_OURS && c->name_id==own_name)ours++;
 }
 if(ours!=1)return 0;
 /* Validate every conversion before changing any state. Active NPC traders must
    finish first: deleting them would silently lose an in-flight transaction. */
 for(int s=0;s<d.slots;s++){
  if(d.slot_name[s]==own_name)continue;
  empire_city *found=0;
  for(int i=0;i<empire_city_get_array_size();i++){
   empire_city *c=empire_city_get(i);if(c->in_use && c->name_id==d.slot_name[s]){found=c;break;}
  }
  if(!found || (found->type!=EMPIRE_CITY_TRADE && found->type!=EMPIRE_CITY_PLAYER && found->type!=EMPIRE_CITY_FUTURE_ROMAN))return 0;
  for(int i=0;i<EMPIRE_CITY_MAX_TRADERS;i++)if(found->trader_figure_ids[i]){
   fprintf(stderr,"Roster expansion blocked: active NPC trader\n");return 0;
  }
 }
 for(int s=0;s<d.slots;s++){
  if(d.slot_name[s]==own_name)continue;
  for(int i=0;i<empire_city_get_array_size();i++){
   empire_city *c=empire_city_get(i);if(!c->in_use || c->name_id!=d.slot_name[s])continue;
   c->is_open=0;
   empire_object_get_full(c->empire_object_id)->trade_route_open=0;
   if(!empire_city_reserve_for_player(c->name_id))return 0;
  }
 }
 return 1;
}
/* Set only the fresh city's calendar. Do not simulate taxes, events or growth. */
static int creator_align_roster_time(uint64_t ticks)
{
 uint64_t days=ticks/GAME_TIME_TICKS_PER_DAY;
 if(days>INT_MAX)return 0;
 uint8_t raw[20];buffer b;buffer_init(&b,raw,sizeof(raw));
 buffer_write_i32(&b,ticks%GAME_TIME_TICKS_PER_DAY);
 buffer_write_i32(&b,days%GAME_TIME_DAYS_PER_MONTH);
 buffer_write_i32(&b,(days/GAME_TIME_DAYS_PER_MONTH)%GAME_TIME_MONTHS_PER_YEAR);
 buffer_write_i32(&b,scenario_property_start_year()+days/(GAME_TIME_DAYS_PER_MONTH*GAME_TIME_MONTHS_PER_YEAR));
 buffer_write_i32(&b,days);buffer_reset(&b);game_time_load_state(&b);return 1;
}
