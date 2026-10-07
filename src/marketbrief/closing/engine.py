"""Deterministic signals. Turnover is activity, never net investor money flow."""
from statistics import mean, median
import math


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
        score = (40 * bounded(relative / 5, 0, 1) + 25 * breadth
                 + 20 * bounded((delta or 0) / 1, 0, 1)
                 + 15 * bounded(((ratio or 1) - 1) / 1, 0, 1)) if ready else None
        leader = max(members, key=lambda s: (s['turnover'], s['code']))
        previous_leader = None
        if old_maps and set(codes).issubset(old_maps[-1]):
            previous_leader = max((old_maps[-1][c] for c in codes), key=lambda s: (s['turnover'], s['code']))['code']
        if not ready:
            status = '기준 데이터 축적 중'
        elif score >= 60 and relative >= 1 and breadth >= .6 and ratio >= 1.3 and delta > 0:
            status = '강세'
        elif relative < 0 and delta < 0 and breadth < .5:
            status = '약화'
        else:
            status = '중립'
        themes.append(dict(name=name, status=status, score=score, change=median(returns),
                           relative=relative, breadth=breadth, turnover=turnover, share=share,
                           share_delta=delta, ratio=ratio, leader=leader['code'],
                           leader_name=leader['name'], previous_leader=previous_leader,
                           baseline_days=len(old_values)))
    themes.sort(key=lambda t: (-(t['score'] if t['score'] is not None else -1), t['name']))
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


def render(report):
    lines = ['📊 BONG MARKET BRIEF | 장마감', report['date'] + ' KRX 일별 조회 기준',
             '※ 15:40 수집 목표 · 제공처 지연 시 재시도 · 확정 수급 아님', '',
             '시장: ' + ' / '.join(f'{k} {v:+.2f}%' for k, v in report['indices'].items()),
             f"분석 {report['stock_count']:,}종목 · 거래대금 {report['total_turnover']/1e12:.2f}조원", '',
             '테마 변화 (사용자 지정 바스켓)']
    for t in report['themes']:
        if t['score'] is None:
            lines.append(f"• {t['name']}: {t['status']}")
            continue
        lines.append(f"• {t['name']} [{t['transition'] or t['status']}] {t['score']:.0f}점\n"
                     f"  중앙등락 {t['change']:+.1f}% / 시장대비 {t['relative']:+.1f}%p / 상승 {t['breadth']:.0%}\n"
                     f"  거래대금 {t['ratio']:.2f}배 / 점유율 변화 {t['share_delta']:+.2f}%p")
        if t['previous_leader'] and t['previous_leader'] != t['leader']:
            lines.append(f"  거래대금 1위 교체: {t['previous_leader']} → {t['leader_name']}")
    lines.extend(['', '주도주 후보 (거래대금순 · 등락 +2%, 시장대비 +1%p 이상)'])
    for s in report['leaders']:
        multiple = f"{s['ratio']:.2f}배" if s['ratio'] is not None else '비교자료 부족'
        lines.append(f"• {'[신규] ' if s['new'] else ''}{s['name']}({s['code']}) {s['change']:+.2f}%\n"
                     f"  {s['turnover']/1e8:,.0f}억원 / {multiple} / {s['signal']}")
    if not report['leaders']:
        lines.append('• 조건 충족 종목 없음')
    lines.extend(['', f"기준: 직전 {report['baseline_days']}거래일(최대 20일), 당일 제외.",
                  '거래대금 점유율은 거래 집중도이며 순유입 자금이 아닙니다.',
                  '테마 중복 편입 가능 · 자동 매수 신호 아님 · 출처: KRX/pykrx'])
    return '\n'.join(lines)
