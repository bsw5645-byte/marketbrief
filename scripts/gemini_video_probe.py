"""Historical URL-only preview: never sends or touches live delivery receipts."""
from datetime import date
from pathlib import Path
import os
from marketbrief.video.gemini import analyze_video
from marketbrief.video.pipeline import PipelineError, Video, render, save_json


def main():
    directory = Path('reports/youtube')
    # This ID and metadata were independently resolved during the earlier caption test.
    video = Video('YTU7rE9cEnQ', '개인은 3조 샀는데 외국인·기관은 팔았다? 7,000선에 또 막힌 코스피',
                  '2026-10-07T10:00:00Z')
    try:
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
    except PipelineError as error:
        save_json(directory/'status.json', {'status': 'failed', 'reason': str(error),
                    'gemini_key_present': bool(os.environ.get('GEMINI_API_KEY'))})
        print(str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
