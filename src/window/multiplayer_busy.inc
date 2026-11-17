#include "core/time.h"
static time_millis room_busy_started[10];   /* 8: the hall's scenario window, 9: the update check */
static int room_busy_active[10];
static int room_menu_pending(void){char value[8];room_read("menu-leave-request.txt",value,sizeof(value));return value[0]=='1';}
static int room_connect_busy(void){char value[8],command[128];room_read("network-busy.txt",value,sizeof(value));room_read("command.txt",command,sizeof(command));return value[0]=='1' || !strncmp(command,"network-host-ip\n",strlen("network-host-ip\n")) || !strncmp(command,"network-join-ip\n",strlen("network-join-ip\n")) || !strncmp(command,"network-join-found\n",strlen("network-join-found\n"));}
/* Independent of command.txt: exiting must not be lost behind an in-flight command. */
void window_multiplayer_leave_to_menu(void){
 char entry[8];room_read("network-entry.txt",entry,sizeof(entry));
 if(room_exit_seen || (entry[0]!='0' && !room_connect_busy()))return;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048];snprintf(path,sizeof(path),"%s/menu-leave-request.txt",dir);
 FILE *file=fopen(path,"wb");if(file){fputs("1",file);fclose(file);}
}
static void room_busy_draw(int slot,int active,int x,int y,int width){
 if(!active){room_busy_active[slot]=0;return;}
 time_millis now=time_get_millis();
 if(!room_busy_active[slot]){room_busy_active[slot]=1;room_busy_started[slot]=now;}
 unsigned elapsed=(unsigned)(now-room_busy_started[slot]);
 int segment=(elapsed/160)%8,bar=width>180?120:80;
 for(int i=0;i<8;i++)graphics_fill_rect(x+i*bar/8,y+3,bar/8-2,7,i==segment?0xffd6a64e:0xff65543c);
 char text[96];snprintf(text,sizeof(text),"처리 중 %u초",elapsed/1000);
 draw_utf8(text,x+bar+8,y,width-bar-8,FONT_SMALL_PLAIN);
 window_request_refresh();
}
