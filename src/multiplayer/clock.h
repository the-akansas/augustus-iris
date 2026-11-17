#ifndef MP_CLOCK_H
#define MP_CLOCK_H
#define MP_CLOCK_CREDIT_TICKS 512 /* matches MAX_CREDIT_TICKS in Augustus/clock_policy.py */
int mp_clock_active(void);
int mp_clock_trade_busy(void);
void mp_clock_start(void);
void mp_clock_stop(void);
int mp_clock_budget(void);
void mp_clock_did_tick(void);
int mp_clock_speed(void);
unsigned long long mp_clock_completed(void);
#endif
