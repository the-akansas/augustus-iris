"""Whole games of the throne tutorial (scenarios/throne-6p), played to the end by the real host code (2026-11-14).

  python handoff/sim_throne_tutorial.py [--games 200] [--income 250] [--seed 1]

Why: a default scenario is a tutorial that must END (user 2026-11-14: one to two hours). This plays six cities month
by month with the scenario's own throne rules through throne_state / throne_play / the debit ledger (the same code a
room runs), until somebody completes the fifth stage, and reports how long it took and what it cost.

Stand-ins and assumptions (this is not a measurement of the game):
  * the city's money engine is test_throne_trial.Cities (applies a debit when the treasury covers it);
  * every city starts with the scenario's starting funds and earns `--income` Dn a month, a number passed in, NOT
    measured from a real city; half the starting funds are held back for building;
  * a player funds the next coup with the minimum as soon as the rules and its money allow, pays the tribute while
    the legions march when it can, and otherwise is sacked (the engine's reports are written by this script);
  * the coup draw is the host's real one (secrets.randbelow), so every run differs; --seed fixes it for a rerun.
One real minute figures: a month is 800 ticks; at game speed 80% a tick takes 57 ms (game/speed.c), 90% 37 ms."""
import argparse,json,random,sqlite3,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent/'Augustus'
sys.path.insert(0,str(HERE));sys.path.insert(0,str(A))
import test_throne_trial as tt
import throne_play as tp

def play(scenario,income,rng,limit_months=600):
    cities=[s['id'] for s in scenario['slots']];rules=scenario['rules']['throne'];funds=scenario['rules']['starting_funds']
    tt.CITIES[:]=cities;tt.RULES=rules;tt.B.clear();tt.B.update(cities=list(cities),throne=dict(rules=rules,rome=scenario['empire']['rome']))
    real=tp.secrets.randbelow;tp.secrets.randbelow=lambda n:rng.randrange(n)
    with tempfile.TemporaryDirectory() as folder:
        host=tt.Host(folder).setup();money=tt.Cities({c:funds for c in cities});reserve=funds//2;spent={c:0 for c in cities};raids=sacks=0
        try:
            for month in range(1,limit_months+1):
                tick=month*tt.MONTH
                for c in cities:money.treasury[c]+=income
                host.settle(tick)
                for c in rng.sample(cities,len(cities)):
                    state=host.state()
                    if state['ended']:break
                    raid=state['players'][c]['secret']['expedition']
                    if raid['phase']=='preparing' and not raid['tribute_paid']:
                        q=host.quote(c,'tribute',host.own(c)['raid']['tribute'],money.treasury[c],tick)
                        if q.get('ok'):
                            before=money.treasury[c];host.spend(c,'tribute',q['amount'],money.treasury[c],tick);money.run(host,c);host.settle(tick);spent[c]+=before-money.treasury[c];continue
                    if raid['phase']=='arrived':
                        raids+=1;tp.raid_report(host.db,tt.B,c,raid['count'],tp.RAID_ATTACKING,tick);host.db.commit()
                    elif raid['phase']=='fighting' and raid['deadline_tick'] is not None and tick>=raid['deadline_tick']:
                        sacks+=1;host.settle(tick)
                    q=host.quote(c,'coup',1,None,tick);minimum=q.get('minimum')
                    if not minimum or money.treasury[c]-minimum<reserve:continue
                    q=host.quote(c,'coup',minimum,money.treasury[c],tick)
                    if not q.get('ok'):continue
                    before=money.treasury[c];host.spend(c,'coup',minimum,money.treasury[c],tick);money.run(host,c);host.settle(tick);spent[c]+=before-money.treasury[c]
                state=host.state()
                if state['ended']:
                    winner=max(cities,key=lambda c:state['players'][c]['stage'])
                    return dict(months=month,winner_spent=spent[winner],total_spent=sum(spent.values()),raids=raids,sacks=sacks)
            return dict(months=None)
        finally:
            tp.secrets.randbelow=real;host.db.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--games',type=int,default=200);ap.add_argument('--income',type=int,default=250);ap.add_argument('--seed',type=int,default=1)
    ap.add_argument('--scenario',default=str(A/'scenarios'/'throne-6p'/'scenario.json'));a=ap.parse_args()
    scenario=json.loads(Path(a.scenario).read_text(encoding='utf-8-sig'));rng=random.Random(a.seed)
    done=[play(scenario,a.income,rng) for _ in range(a.games)]
    ended=[d for d in done if d['months']];q=lambda v,p:sorted(v)[min(len(v)-1,int(len(v)*p))]
    print(f'games {len(done)}, ended {len(ended)}, not ended within 600 months {len(done)-len(ended)} (income {a.income} Dn a month, assumed)')
    if ended:
        m=[d['months'] for d in ended];minutes=lambda months,ms:months*800*ms/60000
        print(f'months to the end: median {q(m,.5)}, 9 in 10 within {q(m,.9)}, shortest {min(m)}, longest {max(m)}')
        print(f'real time at 80%: median {minutes(q(m,.5),57):.0f} min, 9 in 10 within {minutes(q(m,.9),57):.0f} min; at 90%: median {minutes(q(m,.5),37):.0f} min')
        print(f"winner's spending: median {q([d['winner_spent'] for d in ended],.5):,} Dn; expeditions that reached a city per game: {sum(d['raids'] for d in ended)/len(ended):.1f}")
    return 0 if len(ended)==len(done) else 1
if __name__=='__main__':sys.exit(main())
