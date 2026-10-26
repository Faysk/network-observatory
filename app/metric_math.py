"""Explicit measurement semantics; no extrapolation across missing observations."""
import math
from datetime import datetime

FRESHNESS_SECONDS = 180

def percentile(values, fraction=.95):
    values = sorted(v for v in values if type(v) in (int,float) and math.isfinite(v))
    return values[max(0, math.ceil(len(values)*fraction)-1)] if values else None

def observation_coverage(db, table, start, end, mac=None):
    if table not in ('huawei_samples','router_client_samples'):raise ValueError('Unknown source')
    a,b=start.timestamp(),end.timestamp();span=b-a
    context=datetime.fromtimestamp(a-FRESHNESS_SECONDS,start.tzinfo).isoformat()
    where='ts>=? AND ts<=?';parameters=[context,end.isoformat()]
    if mac is not None:where+=' AND mac=?';parameters.append(mac)
    count=0;covered=0.0;last_end=a;previous=None;interval_sum=0.0;intervals=0;gaps=0
    for (text,) in db.execute('SELECT ts FROM '+table+' WHERE '+where+' ORDER BY ts,id',parameters):
        t=datetime.fromisoformat(text).timestamp()
        if t>=a:count+=1
        if previous is not None and t>=a:
            delta=t-previous
            if delta>0 and previous>=a:interval_sum+=delta;intervals+=1
            if delta>FRESHNESS_SECONDS:gaps+=1
        left=max(a,t);right=min(b,t+FRESHNESS_SECONDS)
        if right>left:
            covered+=max(0.0,right-max(left,last_end));last_end=max(last_end,right)
        previous=t
    expected=max(1,math.ceil(span/60))
    return {'sample_count':count,'expected_count':expected,
            'nominal_sample_percent':min(100,count/expected*100),
            'coverage_percent':min(100,max(0,covered/span*100)) if span>0 else 0,
            'covered_seconds':covered,'window_seconds':span,'freshness_seconds':FRESHNESS_SECONDS,
            'observed_interval_mean_seconds':interval_sum/intervals if intervals else None,
            'gaps_over_freshness':gaps,
            'coverage_semantics':'time_with_stored_observation_no_older_than_180_seconds',
            'expected_count_semantics':'nominal_60_second_target_not_used_as_time_coverage'}
