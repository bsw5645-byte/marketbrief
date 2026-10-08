import argparse
from datetime import date, datetime
import os
from pathlib import Path
from .pipeline import KST, PipelineError, VIDEO_ID, run, save_json


def main():
    parser = argparse.ArgumentParser(description='이세무사 장마감 영상 자막 요약')
    parser.add_argument('--date', type=date.fromisoformat)
    parser.add_argument('--video-id')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--fetch-only', action='store_true', help='자막 수집만: GPT 비용 및 발송 없음')
    parser.add_argument('--provider', choices=['gemini', 'captions'], default='gemini')
    args = parser.parse_args()
    if args.video_id and not VIDEO_ID.fullmatch(args.video_id):
        parser.error('영상 ID는 11자의 영문/숫자/-/_만 허용')
    now = datetime.now(KST)
    day = args.date or now.date()
    if day > now.date():
        parser.error('미래 날짜는 조회할 수 없습니다.')
    # Historical testing cannot pollute live receipts or send yesterday as today.
    if args.send and day != now.date():
        parser.error('과거 날짜 테스트는 --send 없이 실행하세요.')
    directory = Path('reports/youtube')
    try:
        from .gemini import analyze_video
        run(day, now, Path('data/youtube'), directory, args.send, args.video_id, args.fetch_only,
            analyzer=analyze_video if args.provider == 'gemini' else None)
        save_json(directory / 'status.json', {'status': 'ok', 'date': str(day)})
    except PipelineError as error:
        save_json(directory / 'status.json', {'status': 'pending_or_failed', 'date': str(day),
                                             'reason': str(error),
                                             'gemini_key_present': bool(os.environ.get('GEMINI_API_KEY'))})
        print(str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
