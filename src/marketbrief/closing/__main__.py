"""Run with PYTHONPATH=src python -m marketbrief.closing [--send]."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from .engine import DataNotReady, analyze, compare, render
from .provider import KST, KRXProvider, is_after_close, session_dates
from .delivery import deliver


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def run(args):
    now = datetime.now(KST)
    day = args.date or now.date().isoformat()
    if args.send and (args.fixture or day != now.date().isoformat()):
        raise DataNotReady('과거일/테스트 데이터는 발송할 수 없습니다.')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    state = Path(args.state)
    receipt_file = state / 'receipts' / f'{day}.json'
    receipt = json.loads(receipt_file.read_text()) if receipt_file.exists() else {}
    # Freeze the delivered text so retry chunk numbers never refer to new text.
    if args.send and receipt.get('message'):
        failures = deliver(receipt['message'], receipt, lambda r: write_json(receipt_file, r))
        if failures:
            raise DataNotReady('; '.join(failures))
        print('기존 브리핑 미발송 채널 처리 완료')
        return
    if args.fixture:
        fixture = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
        current, history = fixture['current'], fixture['history']
        day = current['date']
    else:
        dates = session_dates(day)
        if not dates:
            print(f'{day}: 휴장일, 발송 생략')
            return
        if day == now.date().isoformat() and not is_after_close(now):
            print('장마감 +10분 이전: 발송 생략(특별 개장일 포함)')
            return
        if day > now.date().isoformat():
            raise DataNotReady('미래일은 조회할 수 없습니다.')
        provider = KRXProvider()
        current = provider.collect(day)
        history = []
        for date in dates[:-1]:
            path = state / 'snapshots' / f'{date}.json'
            if path.exists():
                s = json.loads(path.read_text(encoding='utf-8'))
                if s['date'] != date:
                    raise DataNotReady('저장 데이터 날짜 불일치')
                history.append(s)
        # Bootstrap enough sessions for both today's and yesterday's signals.
        for date in dates[-7:-1]:
            if date not in {s['date'] for s in history}:
                s = provider.collect(date)
                write_json(state / 'snapshots' / f'{date}.json', s)
                history.append(s)
        history.sort(key=lambda s: s['date'])
        if len(history) < 6:
            raise DataNotReady('최소 6거래일 기준 데이터가 필요합니다.')
        for market in current['indices']:
            today_count = sum(s['market'] == market for s in current['stocks'])
            old_count = sum(s['market'] == market for s in history[-1]['stocks'])
            if today_count < old_count * .95:
                raise DataNotReady(f'{market} 전일 대비 수집 종목 수 급감')
        write_json(state / 'snapshots' / f'{day}.json', current)
    report = analyze(current, history, config)
    previous = analyze(history[-1], history[:-1], config) if history else None
    compare(report, previous)
    message = render(report)
    if args.fixture:
        message = '🧪 가상 데이터 테스트 — 실제 시세 아님\n' + message
    write_json(out / 'closing-report.json', report)
    (out / 'closing-report.txt').write_text(message, encoding='utf-8')
    print(message)
    if args.send:
        receipt['message'] = message
        write_json(receipt_file, receipt)
        failures = deliver(message, receipt, lambda r: write_json(receipt_file, r))
        if failures:
            raise DataNotReady('; '.join(failures))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='config/closing.json')
    p.add_argument('--state', default='data/closing')
    p.add_argument('--output', default='reports/closing')
    p.add_argument('--date', help='YYYY-MM-DD, 조회만 가능')
    p.add_argument('--fixture', help='가상 데이터 JSON; 발송 금지')
    p.add_argument('--send', action='store_true', help='기존 Telegram/Kakao 수신처에 발송')
    args = p.parse_args()
    try:
        run(args)
    except DataNotReady as exc:
        print(f'브리핑 보류: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        # Upstream exception URLs can contain bot tokens. Never print the value.
        print(f'브리핑 보류: 데이터/통신 오류 ({type(exc).__name__})', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
