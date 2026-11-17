"""Rome on the in-game empire map (user 2026-11-13): drawn at the shared capital position and, when clicked, its name,
description and facts in the bottom panel, the same texts the waiting room and the scenario screen use.
Display only: no city object, no trade, no visit; a city under the same spot is clicked first."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus'
sys.path.insert(0,str(A))
import rome_capital

class Rome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inc=(ROOT/'src/window/empire_rome.inc').read_text(encoding='utf8').split('*/',1)[1]
        cls.c=(ROOT/'src/window/empire.c').read_text(encoding='utf8')
        cls.bridge=(A/'game_bridge.py').read_text(encoding='utf8')
    def test_bridge_sends_the_shared_texts(self):
        self.assertIn("'empire-rome.txt'",self.bridge)
        block=self.bridge[self.bridge.index('rome_ok='):self.bridge.index("self.write_changed('empire-rome.txt'")]
        for word in ('rome_capital.texts()',"get('description')","spec().get('name'"):self.assertIn(word,block)
        self.assertNotIn("get('facts')",block)                                    # user 2026-11-13: two lines, no facts line
        # run the bridge's own lines on the real texts: the description splits after the first sentence
        ns=dict(rome=dict(x=768,y=496),rome_ok=True);code='\n'.join(l.strip() for l in block.split('\n') if l.startswith('   '))
        exec('import rome_capital\n'+code,ns);lines=ns['rome_text'].split('\n')
        self.assertEqual(lines[0],'768 496');self.assertEqual(lines[1],'로마');self.assertEqual(lines[4],'')
        self.assertTrue(lines[2].endswith('발밑에 있습니다.'));self.assertTrue(lines[3].startswith('당신은'))
        self.assertEqual(lines[2]+' '+lines[3],' '.join(rome_capital.texts()['description'].split()))
    def test_click_picks_rome_only_where_no_city_is(self):
        click=self.c[self.c.index('static void determine_selected_object'):];click=click[:click.index('\n}\n')]
        self.assertIn('if (!empire_get_hovered_object(map_x, map_y) && mp_empire_rome_hit(m->x, m->y))',click)
        self.assertIn('empire_clear_selected_object();',click);self.assertIn('mp_empire_rome.selected = 0;',click)
    def test_panel_shows_rome_instead_of_the_hint(self):
        self.assertIn('} else if (!draw_mp_empire_rome_info()) {',self.c)
        info=self.inc[self.inc.index('static int draw_mp_empire_rome_info'):]
        self.assertIn('if (empire_selected_object()) {',info)            # a city chosen meanwhile wins
        for field in ('mp_empire_rome.name','mp_empire_rome.text','mp_empire_rome.text2'):self.assertIn(field,info)
        self.assertNotIn('facts',info);self.assertNotIn('text_draw_multiline',info)
        self.assertNotIn('trade',info.lower().replace('trade_',''));self.assertNotIn('visit',info.lower())
    def test_flag_waves_like_the_city_flags(self):
        draw=self.inc[self.inc.index('static void draw_mp_empire_rome(void)'):]
        self.assertIn('game_animation_should_advance(icon->animation->speed_id)',draw)
        self.assertIn('image_draw(trade + frame,',draw);self.assertNotIn('image_draw(trade + 1,',draw)
    def test_file_is_read_line_by_line(self):
        self.assertIn('mp_empire_rome_line(&cursor, first, sizeof(first));',self.inc)
        self.assertIn('sscanf(first, "%d %d %c", &x, &y, &extra) != 2',self.inc)

if __name__=='__main__':unittest.main()
