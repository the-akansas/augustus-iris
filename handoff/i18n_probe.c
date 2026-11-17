/* mp_i18n matcher probe (built by test_i18n.py with the game's core/mp_i18n.c). */
#include <stdio.h>
#include <string.h>
#include "core/mp_i18n.h"
static int bad;
static void expect(const char *in, const char *want){const char *got=mp_i18n_translate(in);if(strcmp(got,want)){printf("FAIL [%s] -> [%s] want [%s]\n",in,got,want);bad++;}}
int main(int argc,char**argv){
 if(mp_i18n_load(argv[1])<=0){printf("FAIL load\n");return 1;}
 expect("공동 저장 중입니다.","Joint save in progress.");
 expect("선물: 30 데나리","Gift: 30 Dn");
 expect("방장 버전: v4.0 / 261113-rc1","Host version: v4.0 / 261113-rc1");
 expect("3개 도시 진행 중 / 방장 목표 80%","Host target 80% / 3 cities running");
 expect("모르는 문장","모르는 문장");
 expect("공동 저장 중입니다.\n선물: 5 데나리","Joint save in progress.\nGift: 5 Dn");
 expect("요청을 처리하지 못했습니다(원인: room full). 잠시 후 다시 시도해 주세요.","Request failed (cause: room full). Please try again shortly.");
 mp_i18n_suspend(1);expect("공동 저장 중입니다.","공동 저장 중입니다.");mp_i18n_suspend(0);
 expect("탭\\t그대로","tab kept");
 /* a known word filled into a slot is translated too; numbers and unknown names stay */
 expect("밀 30포대를 900 Dn에 사겠다고 합니다.","They want to buy: Wheat, 30 loads for 900 Dn.");
 expect("보리 2포대를 9 Dn에 사겠다고 합니다.","They want to buy: 보리, 2 loads for 9 Dn.");
 printf(bad?"FAILED %d\n":"OK\n",bad);return bad!=0;
}
