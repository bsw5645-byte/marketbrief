"""Historical URL-only preview: never sends or touches live delivery receipts."""
from datetime import date, datetime
from pathlib import Path
import os
from marketbrief.video.gemini import analyze_video
from marketbrief.video.pipeline import KST, PipelineError, Video, find_video, render, save_json
from marketbrief.video.pipeline import BoundedSession


def text_connection_status():
    """Minimal connection check; never prints input keys or API response bodies."""
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        return 'missing_key'
    try:
        response = BoundedSession().post('https://generativelanguage.googleapis.com/v1beta/interactions',
            headers={'x-goog-api-key': key}, timeout=(10, 45),
            json={'model': os.environ.get('GEMINI_MODEL') or 'gemini-3.8-flash', 'store': False,
                  'input': 'Reply OK.', 'generation_config': {'max_output_tokens': 32}})
        return response.status_code
    except Exception:
        return 'connection_failed'


def main():
    directory = Path('reports/youtube')
    # This ID and metadata were independently resolved during the earlier caption test.
    video = Video('YTU7rE9cEnQ', '개인은 3조 샀는데 외국인·기관은 팔았다? 7,000선에 또 막힌 코스피',
                  '2026-10-07T10:00:00Z')
    try:
        discovery_error = None
        try:
            found = find_video(date(2026, 10, 7), datetime.now(KST), video.video_id)
            print('채널 검색 성공:', found.video_id, found.title, found.published_at, flush=True)
        except PipelineError as error:
            discovery_error = error
            print('채널 검색 검증 실패:', str(error), flush=True)
        summary, metadata = analyze_video(video)
        message = render(video, summary, date(2026, 10, 7)).replace(
            '자동자막 오인식 가능', 'Gemini 영상 분석 · 시각은 추정치')
        directory.mkdir(parents=True, exist_ok=True)
        save_json(directory/'analysis.json', {'summary': summary, 'analysis': metadata})
        (directory/'2026-10-07.txt').write_text(message, encoding='utf-8')
        save_json(directory/'status.json', {'status': 'ok', 'mode': 'historical_preview'})
        print(message)
        print('검토용 근거:', metadata['evidence'])
        print('사용량:', metadata['usage'])
        print('원본 재검토:', metadata['reviewed'], '초안 수정:', metadata['review_changed_summary'])
        if discovery_error:
            raise discovery_error
    except PipelineError as error:
        health = None
        if str(error).startswith(('Gemini HTTP', 'Gemini 연결 실패')):
            health = text_connection_status()
            print('Gemini 텍스트 연결 확인:', health)
        save_json(directory/'status.json', {'status': 'failed', 'reason': str(error),
                    'gemini_key_present': bool(os.environ.get('GEMINI_API_KEY')),
                    'youtube_key_present': bool(os.environ.get('YOUTUBE_API_KEY')),
                    'gemini_text_http': health})
        print(str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()

