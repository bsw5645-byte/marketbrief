"""Plain-language mobile report. Calculation details remain in the JSON file."""


def render(report):
    themes = report['themes']
    valid = [t for t in themes if t['score'] is not None]
    rising = [t for t in valid if t['status'] in ('강세', '상승 확산')]
    resilient = [t for t in valid if t['status'] == '하락 속 선방']
    weak = sorted((t for t in valid if t['status'] in ('약세', '동반 약세', '거래 급증 속 하락')),
                  key=lambda t: t['change'])
    mixed = [t for t in valid if t['status'] == '혼조']
    if not valid:
        headline = '업종 흐름 판단에 필요한 데이터가 부족합니다.'
    elif rising:
        headline = ' · '.join(t['name'] for t in rising[:2]) + ' 중심으로 상승 확산'
    elif all(t['change'] < 0 for t in valid):
        headline = '관찰 업종 전반 약세' + (' — 일부 종목만 개별 상승' if report['leaders'] else '')
    else:
        headline = '업종별 흐름 엇갈림 — 뚜렷한 동반 강세 부족'
    lines = ['📊 BONG | 오늘 장마감', report['date'], '━━━━━━━━━━━━━━',
             '📌 ' + headline, '',
             f"코스피 {report['indices']['KOSPI']:+.2f}%  ·  코스닥 {report['indices']['KOSDAQ']:+.2f}%",
             '', '🔥 강한 업종']

    def examples(t, falling):
        members = sorted(t['members'], key=lambda s: s['change'], reverse=not falling)
        return ' · '.join(f"{s['name']} {s['change']:+.1f}%" for s in members[:2])

    for t in rising[:3]:
        label = t.get('transition') or ('거래 증가와 함께 상승' if t['status'] == '강세' else '여러 종목 동반 상승')
        lines.extend([f"• {t['name']} | {label}",
                      f"  관찰 {t['member_count']}개 중 {t['up_count']}개 상승",
                      '  ' + examples(t, False)])
    if not rising:
        lines.append('• 관찰 업종에서 뚜렷한 동반 상승 없음' if valid else '• 데이터 확인 중')
    elif len(rising) > 3:
        lines.append('• 함께 상승: ' + ' · '.join(t['name'] for t in rising[3:]))
    if resilient:
        lines.extend(['', '🛡 하락장에서 상대적으로 버틴 업종'])
        for t in resilient:
            lines.extend([f"• {t['name']} | 시장보다 덜 하락",
                          f"  관찰 {t['member_count']}개 중 {t['down_count']}개 하락"])
    if weak:
        lines.extend(['', '🔻 크게 밀린 업종' if any(t['change'] <= -2 for t in weak) else '🔻 약해진 업종'])
        for t in weak[:3]:
            detail = (f"거래대금은 최근 평균의 {t['ratio']:.1f}배인데 주가는 하락"
                      if t['status'] == '거래 급증 속 하락'
                      else '시장보다 낙폭이 큼' if t['status'] == '동반 약세' else '여러 종목 동반 하락')
            lines.extend([f"• {t['name']} | {detail}",
                          f"  관찰 {t['member_count']}개 중 {t['down_count']}개 하락",
                          '  ' + examples(t, True)])
        if len(weak) > 3:
            lines.append('• 함께 약세: ' + ' · '.join(t['name'] for t in weak[3:]))
    if mixed:
        lines.extend(['', '↔ 흐름 엇갈림: ' + ' · '.join(t['name'] for t in mixed)])
    transitions = []
    for t in valid:
        if t.get('transition') == '강세 이탈':
            reason = '오늘은 여러 종목 하락' if t['change'] < 0 else '오늘은 강세 조건 미충족'
            transitions.append(f"• {t['name']}: 전일 강세 → {reason}")
        elif t.get('transition') == '신규 강세':
            transitions.append(f"• {t['name']}: 새롭게 강세 조건 충족")
    if transitions:
        lines.extend(['', '🔄 전일과 달라진 흐름', *transitions[:3]])
    lines.extend(['', '👀 눈에 띈 상승 종목 TOP 5', '거래대금순 · 업종 전체의 상승을 뜻하지 않음'])
    for i, s in enumerate(report['leaders'][:5], 1):
        lines.append(f"{i}. {s['name']} {s['change']:+.2f}%  |  거래 {s['turnover']/1e8:,.0f}억원")
    if not report['leaders']:
        lines.append('• 조건에 맞는 상승 종목 없음')
    unavailable = [t['name'] for t in themes if t['score'] is None]
    if unavailable:
        lines.extend(['', '확인 보류: ' + ' · '.join(unavailable)])
    lines.extend(['', '━━━━━━━━━━━━━━',
                  f"업종 판단은 지정한 {len(themes)}개 종목 묶음 기준입니다.",
                  '종목 옆 %는 당일 주가 등락률입니다.',
                  f"거래 비교: 직전 {report['baseline_days']}거래일 평균 · KRX/pykrx",
                  '거래 증가만으로 자금 유입이나 상승 이유를 단정하지 않습니다.'])
    return '\n'.join(lines)
