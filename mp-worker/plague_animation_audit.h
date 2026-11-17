/* Read-only resource audit, exports original pixels to private local evidence. */
static int plague_animation_audit(const char *out) {
 if(!image_load_climate(scenario_property_climate(),0,1,1))return 0;
 char p[2048];snprintf(p,sizeof(p),"%s/sprites.txt",out);
 FILE*f=fopen(p,"w");if(!f)return 0;int ok=1;
 int skull=image_group(GROUP_PLAGUE_SKULL),smoke=image_group(GROUP_FIGURE_EXPLOSION);
 building b={0};b.type=BUILDING_BURNING_RUIN;b.size=1;
 int fire=building_image_get(&b);const image*base=image_get(fire);
 fprintf(f,"# skull %d smoke %d fire %d frames %d\n",skull,smoke,fire,base->animation?base->animation->num_sprites:0);
 for(int n=0;n<5;n++){
  int id=n==0?skull:smoke+n-1;const image*im=image_get(id);
  if(!walk_plane(out,f,im,id,0))ok=0;
 }
 if(!walk_plane(out,f,base,fire,0))ok=0;
 if(base->top&&!walk_plane(out,f,base->top,fire,1))ok=0;
 if(!base->animation)ok=0;
 else for(int n=1;n<=base->animation->num_sprites;n++){
  int id=fire+base->animation->start_offset+n;
  if(!walk_plane(out,f,image_get(id),id,0))ok=0;
 }
 if(fclose(f))ok=0;return ok;
}
