/* A read overlay: the personal values[] and augustus.ini are never replaced. */
#include "game/settings.h"
#include "game/cheats.h"
static const struct {int key,maximum,default_value;const char *label;} room_option_rows[CONFIG_ROOM_OPTION_COUNT]={
#include "room_options_rows.inc"
};
static int room_options_active,room_option_values[CONFIG_ROOM_OPTION_COUNT],room_config_values[CONFIG_MAX_ENTRIES],room_config_mask[CONFIG_MAX_ENTRIES];
int config_room_active(void){return room_options_active;}
int config_room_index(int key){for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)if(room_option_rows[i].key==key)return i;return -1;}
int config_room_max(int i){return i>=0 && i<CONFIG_ROOM_OPTION_COUNT?room_option_rows[i].maximum:0;}
const char *config_room_label(int i){return i>=0 && i<CONFIG_ROOM_OPTION_COUNT?room_option_rows[i].label:"";}
int config_room_default(int i){return i>=0 && i<CONFIG_ROOM_OPTION_COUNT?room_option_rows[i].default_value:0;}
int config_room_value(int i){
 if(i<0 || i>=CONFIG_ROOM_OPTION_COUNT)return 0;
 if(room_options_active)return room_option_values[i];
 int key=room_option_rows[i].key;
 /* Weather darkens the view; a new room starts with it off unless the host enables it. */
 if(key==CONFIG_UI_DRAW_WEATHER)return room_option_rows[i].default_value;
 return key==-1?setting_difficulty():key==-2?setting_gods_enabled():key==-3?0:values[key];
}
int config_room_apply(const int *v){
 for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)if(v[i]<0 || v[i]>room_option_rows[i].maximum)return 0;
 if(!room_options_active || room_option_values[CONFIG_ROOM_ALLOW_CHEATS]!=v[CONFIG_ROOM_ALLOW_CHEATS])game_cheat_reset();
 memset(room_config_mask,0,sizeof(room_config_mask));
 for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++){room_option_values[i]=v[i];int key=room_option_rows[i].key;if(key>=0){room_config_mask[key]=1;room_config_values[key]=v[i];}}
 room_options_active=1;return 1;
}
void config_room_clear(void){if(room_options_active)game_cheat_reset();room_options_active=0;}
