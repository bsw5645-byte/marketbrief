"""One read-only caption check: no account login, GPT call, or Telegram send."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

VIDEO_ID = 'YTU7rE9cEnQ'


def probe():
    import requests
    from youtube_transcript_api import YouTubeTranscriptApi

    class BoundedSession(requests.Session):
        def request(self, *args, **kwargs):
            kwargs.setdefault('timeout', (10, 30))
            return super().request(*args, **kwargs)

    try:
        transcript = YouTubeTranscriptApi(http_client=BoundedSession()).fetch(VIDEO_ID, languages=['ko', 'ko-KR'])
        rows = transcript.to_raw_data()
        count = len(rows)
        size = sum(len(str(row.get('text', '')).strip()) for row in rows)
        if count < 8 or size < 300:
            return {'status': 'NOT_READY', 'message': '자막이 너무 짧아 수집 성공으로 처리하지 않습니다.'}
        return {'status': 'PASS', 'message': '이 PC에서 한국어 자막 수집 성공',
                'segments': count, 'characters': size, 'language': transcript.language_code}
    except Exception as error:
        kind = type(error).__name__
        if kind in {'RequestBlocked', 'IpBlocked'}:
            return {'status': 'BLOCKED', 'message': 'YouTube가 이 PC의 자막 요청도 차단했습니다. 여기서 중단합니다.'}
        if kind in {'NoTranscriptFound', 'TranscriptsDisabled', 'VideoUnavailable'}:
            return {'status': 'NOT_READY', 'message': '이 영상의 한국어 자막을 지금 가져올 수 없습니다.'}
        return {'status': 'ERROR', 'message': '통신 또는 실행 오류', 'error_type': kind}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        result = probe()
    except Exception as error:
        result = {'status': 'SETUP_ERROR', 'message': '프로그램 준비 실패', 'error_type': type(error).__name__}
    result.update(video_id=VIDEO_ID, checked_at=datetime.now(timezone.utc).isoformat())
    directory = Path(__file__).resolve().parent
    (directory / 'BONG-test-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    text = '\n'.join(['BONG 자막 수집 테스트', f"결과: {result['status']}", result['message'],
                      f"자막 구간: {result.get('segments', 0)} / 글자 수: {result.get('characters', 0)}",
                      '영상: 2026-10-07 이세무사TV 장마감',
                      f"오류 종류: {result.get('error_type', '없음')}",
                      '계정 로그인, GPT 요약, Telegram 발송은 실행하지 않았습니다.'])
    (directory / 'BONG-test-result.txt').write_text(text, encoding='utf-8-sig')
    print(text)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
