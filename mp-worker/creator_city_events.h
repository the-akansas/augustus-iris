#ifndef CREATOR_CITY_EVENTS_H
#define CREATOR_CITY_EVENTS_H
#include "scenario/event/event.h"
#include "scenario/custom_messages.h"
#include "scenario/request.h"
#include "city/resource.h"

static int creator_event_constant(int value){
 char text[32];snprintf(text,sizeof(text),"%d",value);
 return scenario_formula_add((const uint8_t*)text,-1000000000,1000000000);   /* the game's own range: money conditions go past a million (2026-11-15) */
}
/* A custom message from the event's text ("title\nbody", Augustus/city_events.py), shown by one more action of e. */
static int creator_event_message(scenario_event_t *e,int index,const char *title,const char *body){
 custom_message_t *msg=custom_messages_create_blank();if(!msg)return 0;
 char uid[40];snprintf(uid,sizeof(uid),"city-event-%d",index+1);
 msg->linked_uid=message_media_text_blob_add_encoded(uid);
 msg->title=message_media_text_blob_add_encoded(title);
 msg->subtitle=message_media_text_blob_add_encoded("시나리오 도시 이벤트");
 msg->display_text=message_media_text_blob_add_encoded(body);
 if(!msg->linked_uid || !msg->title || !msg->subtitle || !msg->display_text)return 0;
 scenario_action_t *a=scenario_event_action_create(e,ACTION_TYPE_SHOW_CUSTOM_MESSAGE);if(!a)return 0;a->parameter1=msg->id;return 1;
}
static int creator_event_text_message(scenario_event_t *e,int index,const char *text){
 static char title[CREATOR_EVENT_TEXT];snprintf(title,sizeof(title),"%s",text);
 char *cut=strchr(title,'\n');const char *body=cut?cut+1:title;if(cut)*cut=0;else snprintf(title,sizeof(title),"%s","도시 소식");
 if(!cut)body=text;
 return creator_event_message(e,index,title,body);
}
/* One event that fires once, `month` months after the start. */
static scenario_event_t *creator_event_at(int index,int month,const char *name){
 scenario_event_t *e=scenario_event_create(0,0,1);if(!e)return 0;
 snprintf((char*)e->name,sizeof(e->name),"%s %d",name,index+1);
 scenario_condition_group_t *group;array_new_item(e->condition_groups,group);if(!group)return 0;
 scenario_condition_t *c=scenario_event_condition_create(group,CONDITION_TYPE_TIME_PASSED);if(!c)return 0;
 c->parameter1=COMPARISON_TYPE_EQUAL_OR_MORE;c->parameter2=creator_event_constant(month);if(!c->parameter2)return 0;
 return e;
}
/* Install only when creating a city. Loading an existing SAV must never reinstall. */
/* The event also waits for the city: population, prosperity, culture, health, treasury or favour at least `value`
   (the game's own conditions; both conditions are in the event's first group, which needs all of them). */
static int creator_event_wait(scenario_event_t *e,int type,int value){
 static const int kinds[]={0,CONDITION_TYPE_CITY_POPULATION,CONDITION_TYPE_STATS_PROSPERITY,CONDITION_TYPE_STATS_CULTURE,CONDITION_TYPE_STATS_CITY_HEALTH,CONDITION_TYPE_MONEY,CONDITION_TYPE_STATS_FAVOR};
 if(type<1 || type>6)return 0;
 scenario_condition_group_t *group=array_item(e->condition_groups,0);if(!group)return 0;
 scenario_condition_t *c=scenario_event_condition_create(group,kinds[type]);if(!c)return 0;
 c->parameter1=COMPARISON_TYPE_EQUAL_OR_MORE;c->parameter2=creator_event_constant(value);if(!c->parameter2)return 0;
 if(type==1)c->parameter3=1;   /* the whole population */
 return 1;
}
static int creator_install_events(const creator_city_event *spec,int count,char texts[][CREATOR_EVENT_TEXT]){
 for(int i=0;i<count;i++){
  const creator_city_event *s=&spec[i];const char *text=texts[i];
  scenario_event_t *e=creator_event_at(i,s->month,"City event");if(!e)return 0;
  if(s->cond && !creator_event_wait(e,s->cond,s->cond_value))return 0;
  /* EVENTREPEAT: the game's own repeat (scenario/event/event.c), `every` months (16 days each) after each time it
     happened and while the city still qualifies - a late condition no longer fires every missed repeat at once */
  if(s->repeat_every){e->repeat_days_min=e->repeat_days_max=s->repeat_every*16;e->max_number_of_repeats=s->repeat_times;}
  scenario_action_t *a;
  switch(s->kind){
   case 0:case 1:{
    a=scenario_event_action_create(e,s->kind==0?ACTION_TYPE_ADJUST_MONEY:ACTION_TYPE_ADJUST_FAVOR);if(!a)return 0;
    a->parameter1=creator_event_constant(s->amount);if(!a->parameter1)return 0;
    char body[256];snprintf(body,sizeof(body),s->kind==0?"도시 지원금 %d 데나리를 받았습니다.":"황제 지지도가 %+d만큼 변경되었습니다. 지지도는 0에서 100 사이로 제한됩니다.",s->amount);
    if(!creator_event_message(e,i,s->kind==0?"도시 지원금":"황제 지지도 변화",body))return 0;
    break;}
   case 2:{
    a=scenario_event_action_create(e,ACTION_TYPE_REQUEST_IMMEDIATELY_START);if(!a)return 0;
    int id=scenario_request_new();if(id<0)return 0;scenario_request r=*scenario_request_get(id);
    /* No calendar trigger: event action starts it, including late city activation. */
    r.year=30000;r.month=0;r.resource=s->resource;r.amount.min=r.amount.max=s->amount;
    r.deadline_years=s->deadline;r.months_to_comply=s->deadline*12;r.repeat.times=0;
    scenario_request_update(&r);a->parameter1=id;
    break;}
   case 3:   /* allowed or forbidden from now on; buildings already standing stay */
    a=scenario_event_action_create(e,ACTION_TYPE_CHANGE_ALLOWED_BUILDINGS);if(!a)return 0;a->parameter1=s->resource;a->parameter2=s->amount==1;break;
   case 4:   /* the game's own blessing or curse, with its own message */
    a=scenario_event_action_create(e,s->amount==1?ACTION_TYPE_CAUSE_BLESSING:s->amount==2?ACTION_TYPE_CAUSE_MINOR_CURSE:ACTION_TYPE_CAUSE_MAJOR_CURSE);if(!a)return 0;a->parameter1=s->resource-1;break;
   case 5:   /* warehouses and granaries, whatever their settings; what does not fit or is not there is left out */
    a=scenario_event_action_create(e,ACTION_TYPE_CHANGE_RESOURCE_STOCKPILES);if(!a)return 0;
    a->parameter1=s->resource;a->parameter2=creator_event_constant(s->amount);if(!a->parameter2)return 0;a->parameter3=STORAGE_TYPE_ALL;a->parameter4=0;break;
   case 6:
    a=scenario_event_action_create(e,ACTION_TYPE_ADJUST_CITY_HEALTH);if(!a)return 0;a->parameter1=creator_event_constant(s->amount);if(!a->parameter1)return 0;a->parameter2=0;break;
   case 7:{  /* the share for `deadline` months, then normal (100) again by a second one-shot event */
    a=scenario_event_action_create(e,ACTION_TYPE_IMMIGRATION_PERCENTAGE);if(!a)return 0;a->parameter1=creator_event_constant(s->amount);if(!a->parameter1)return 0;a->parameter2=1;
    scenario_event_t *back=creator_event_at(i,s->month+s->deadline,"City event end");if(!back)return 0;
    scenario_action_t *b=scenario_event_action_create(back,ACTION_TYPE_IMMIGRATION_PERCENTAGE);if(!b)return 0;b->parameter1=creator_event_constant(100);if(!b->parameter1)return 0;b->parameter2=1;
    scenario_event_init(back);
    break;}
   case 8:   /* the game's own revolt and messages */
    a=scenario_event_action_create(e,ACTION_TYPE_GLADIATOR_REVOLT);if(!a)return 0;break;
   case 9:break;   /* only the message below */
   default:return 0;
  }
  if(text[0] && !creator_event_text_message(e,i,text))return 0;
  if(s->kind==9 && !text[0])return 0;
  scenario_event_init(e);
 }
 return 1;
}
static int creator_export_events(const char *out){
 char path[2048];snprintf(path,sizeof(path),"%s/events-audit.json",out);FILE *f=fopen(path,"w");if(!f)return 0;
 fprintf(f,"{\"months\":%d,\"events\":[",game_time_total_months());
 for(int i=0;i<scenario_events_get_count();i++){const scenario_event_t *e=scenario_event_get(i);fprintf(f,"%s{\"state\":%d,\"executions\":%d}",i?",":"",e->state,e->execution_count);}
 fputs("],\"requests\":[",f);
 for(unsigned i=0;i<scenario_request_count_total();i++){const scenario_request *r=scenario_request_get(i);fprintf(f,"%s{\"visible\":%d,\"state\":%d,\"amount\":%u,\"resource\":%d,\"months_left\":%d}",i?",":"",r->visible,r->state,r->amount.requested,r->resource,r->months_to_comply);}
 fputs("]}",f);return fclose(f)==0;
}
#endif
