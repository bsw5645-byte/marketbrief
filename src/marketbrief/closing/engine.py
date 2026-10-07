"""Deterministic signals. Turnover is activity, never net investor money flow."""
from statistics import mean, median
import math
from .presentation import render


class DataNotReady(ValueError):
    pass


def validate(snapshot):
    if snapshot.get('schema') != 1:
        raise DataNotReady('지원하지 않는 스냅샷 형식')
    if set(snapshot['indices']) != {'KOSPI', 'KOSDAQ'}:
        raise DataNotReady('시장 지수 누락')
    for value in snapshot['indices'].values():
        if not math.isfinite(value):
            raise DataNotReady('유효하지 않은 지수 등락률')
    seen = set()
    for s in snapshot['stocks']:
        if s['code'] in seen or s['market'] not in snapshot['indices']:
            raise DataNotReady('중복 종목 또는 시장 오류')
        seen.add(s['code'])
        if not all(math.isfinite(s[k]) for k in ('change', 'turnover', 'close')):
            raise DataNotReady('결측/무한대 시세')
        if s['turnover'] < 0 or s['close'] < 0:
            raise DataNotReady('음수 시세')
    for market in snapshot['indices']:
        if sum(s['turnover'] for s in snapshot['stocks'] if s['market'] == market) <= 0:
            raise DataNotReady('시장 거래대금 미제공')


def bounded(x, low, high):
    return min(high, max(low, x))


def theme_status(change, relative, breadth, ratio, score, delta):
    """Distinguish price direction from trading activity, including selloffs."""
    if score is None:
        return '기준 데이터 축적 중'
    if change <= -2 and relative <= -1 and breadth < .5:
        return '거래 급증 속 하락' if ratio >= 1.5 else '동반 약세'
    if change > 0 and score >= 60 and relative >= 1 and breadth >= .6 and ratio >= 1.3 and delta > 0:
        return '강세'
    if change > 0 and relative >= .5 and breadth >= .6:
        return '상승 확산'
    if change < 0 and relative >= .25:
        return '하락 속 선방'
    if change < 0 and breadth < .5:
        return '약세'
    return '혼조'


def analyze(current, history, config):
    validate(current)
    # Same day reruns and future snapshots must never enter the baseline.
    by_date = {s['date']: s for s in history if s['date'] < current['date']}
    history = [by_date[d] for d in sorted(by_date)][-20:]
    for h in history:
        validate(h)
    stocks = {s['code']: s for s in current['stocks']}
    old_maps = [{s['code']: s for s in h['stocks']} for h in history]
    total = sum(s['turnover'] for s in stocks.values())
    old_totals = [sum(s['turnover'] for s in h.values()) for h in old_maps]
    leaders = []
    for s in stocks.values():
        # Exclude suspended issues, preferred shares and SPACs from leader picks.
        if s['turnover'] < config['min_turnover_krw'] or s['close'] <= 0:
            continue
        if '스팩' in s['name'] or not s['code'].endswith('0'):
            continue
        previous = [h[s['code']]['turnover'] for h in old_maps if s['code'] in h]
        ratio = s['turnover'] / mean(previous) if len(previous) >= 5 and mean(previous) > 0 else None
        relative = s['change'] - current['indices'][s['market']]
        if s['change'] < 2 or relative < 1:
            continue
        leaders.append({**s, 'relative': relative, 'ratio': ratio,
                        'signal': '거래대금 동반' if ratio is not None and ratio >= 1.5 else '관찰'})
    leaders.sort(key=lambda s: (-s['turnover'], -s['relative'], s['code']))
    themes = []
    for name, codes in config['themes'].items():
        codes = sorted(set(codes))
        # Do not turn a missing member into an apparent outflow.
        if not set(codes).issubset(stocks) or len(codes) < 3:
            themes.append({'name': name, 'status': '구성종목 데이터 부족', 'score': None})
            continue
        members = [stocks[c] for c in codes]
        returns = [s['change'] for s in members]
        relative = median(s['change'] - current['indices'][s['market']] for s in members)
        breadth = sum(r > 0 for r in returns) / len(members)
        turnover = sum(s['turnover'] for s in members)
        share = 100 * turnover / total
        valid_history = [(h, t) for h, t in zip(old_maps, old_totals) if set(codes).issubset(h)]
        old_values = [sum(h[c]['turnover'] for c in codes) for h, _ in valid_history]
        shares = [100 * sum(h[c]['turnover'] for c in codes) / t for h, t in valid_history]
        ready = len(old_values) >= 5 and mean(old_values) > 0
        ratio = turnover / mean(old_values) if ready else None
        delta = share - mean(shares) if ready else None
        # A transparent heuristic, not a calibrated probability or buy signal.
        change = median(returns)
        activity_bonus = (20 * bounded((delta or 0) / 1, 0, 1)
                          + 15 * bounded(((ratio or 1) - 1) / 1, 0, 1)) if change > 0 else 0
        score = (40 * bounded(relative / 5, 0, 1) + 25 * breadth + activity_bonus) if ready else None
        leader = max(members, key=lambda s: (s['turnover'], s['code']))
        previous_leader = None
        if old_maps and set(codes).issubset(old_maps[-1]):
            previous_leader = max((old_maps[-1][c] for c in codes), key=lambda s: (s['turnover'], s['code']))['code']
        status = theme_status(change, relative, breadth, ratio, score, delta)
        themes.append(dict(name=name, status=status, score=score, change=change,
                           relative=relative, breadth=breadth, turnover=turnover, share=share,
                           share_delta=delta, ratio=ratio, leader=leader['code'],
                           leader_name=leader['name'], previous_leader=previous_leader,
                           members=[dict(code=s['code'], name=s['name'], change=s['change']) for s in members],
                           up_count=sum(r > 0 for r in returns), down_count=sum(r < 0 for r in returns),
                           member_count=len(members),
                           baseline_days=len(old_values)))
    order = {'강세': 0, '상승 확산': 1, '하락 속 선방': 2, '혼조': 3, '약세': 4,
             '동반 약세': 5, '거래 급증 속 하락': 6}
    themes.sort(key=lambda t: (order.get(t['status'], 7), -t.get('relative', 0), t['name']))
    return {'date': current['date'], 'indices': current['indices'], 'themes': themes,
            'leaders': leaders[:10], 'baseline_days': len(history),
            'stock_count': len(stocks), 'total_turnover': total}


def compare(report, previous):
    old = {t['name']: t for t in previous['themes']} if previous else {}
    for t in report['themes']:
        before = old.get(t['name'])
        t['transition'] = None
        if before and before['score'] is not None and t['score'] is not None:
            if t['status'] == '강세':
                t['transition'] = '강세 지속' if before['status'] == '강세' else '신규 강세'
            elif before['status'] == '강세':
                t['transition'] = '강세 이탈'
    old_codes = {s['code'] for s in previous['leaders']} if previous else None
    for s in report['leaders']:
        s['new'] = old_codes is not None and s['code'] not in old_codes
    return report
