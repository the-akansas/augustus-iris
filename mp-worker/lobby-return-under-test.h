#include <stdio.h>
#include <string.h>
#include "widget/input_box.h"
#include "multiplayer/clock.h"
#include "window/city.h"
#include "window/main_menu.h"
static input_box input;static int entered,from_city;static char notice[256];
static int can_return_to_city(void){return entered || from_city;}
static const char *return_label(void){return can_return_to_city()?"도시로 돌아가기":"메인 메뉴";}
static void return_from_lobby(void){
 if(mp_clock_trade_busy()){strcpy(notice,"거래 저장을 적용 중입니다. 완료 후 돌아갈 수 있습니다.");return;}
 notice[0]=0;input_box_stop(&input);
 if(can_return_to_city())window_city_show();else window_main_menu_show(0);
}
