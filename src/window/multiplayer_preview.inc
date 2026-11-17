/* Bounded data-only overview. Does not load a SAV into the running game.
 * Drawn inside the 576x448 city picker: panel x 248..536, y 80..368. */
static int room_preview_index=-1;
static color_t room_preview_color(char tile){
 switch(tile){case 'B':return 0xffb85b36;case 'D':return 0xffe5d3a3;case 'W':return 0xff397fab;
 case 'R':return 0xff88817c;case 'T':return 0xff315e35;case 'F':return 0xff90a85d;default:return 0xffbaaa72;}
}
static void room_preview_draw(void){
 inner_panel_draw(248,80,18,18);
 if(room_preview_index<0 || room_preview_index>=room_choice_count){draw_utf8("왼쪽에서 도시를 고르세요.",264,214,256,FONT_NORMAL_WHITE);return;}
 char raw[27000],city[64];int w=0,h=0,offset=0;room_read("city-preview.txt",raw,sizeof(raw));
 if(sscanf(raw,"%63s\n%d %d\n%n",city,&w,&h,&offset)!=3 || strcmp(city,room_choices[room_preview_index].id) || w<1 || w>160 || h<1 || h>160 || offset<=0 || strcspn(raw+offset,"\r\n")!=(size_t)w*h){
  char status[512];room_read("city-preview-status.txt",status,sizeof(status));draw_utf8(status[0]?status:"도시 지도를 불러오는 중입니다.",264,200,256,FONT_NORMAL_WHITE);char busy[8];room_read("city-preview-busy.txt",busy,sizeof(busy));room_busy_draw(3,busy[0]!='0',264,224,256);return;
 }
 room_busy_draw(3,0,0,0,0);
 const char *grid=raw+offset;if(strspn(grid,"BDWRTFL")!=(size_t)w*h)return;
 int width=256,height=h*width/w;if(height>232){height=232;width=w*height/h;}
 int left=264+(256-width)/2,top=106+(232-height)/2;
 for(int y=0;y<h;y++)for(int x=0;x<w;){int end=x+1;while(end<w && grid[y*w+end]==grid[y*w+x])end++;
  graphics_fill_rect(left+x*width/w,top+y*height/h,end*width/w-x*width/w,(y+1)*height/h-y*height/h,room_preview_color(grid[y*w+x]));x=end;}
 const char *caption=grid+w*h;while(*caption=='\n' || *caption=='\r')caption++;
 draw_utf8(caption,264,88,256,FONT_NORMAL_WHITE);
 const char *labels[]={"물","숲","바위","건물","길"};const char kinds[]="WTRBD";
 for(int i=0;i<5;i++){graphics_fill_rect(264+i*52,346,10,10,room_preview_color(kinds[i]));draw_utf8(labels[i],278+i*52,344,36,FONT_NORMAL_WHITE);}
}
