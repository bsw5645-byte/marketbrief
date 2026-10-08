from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from marketbrief.video.gemini import analyze_video
from marketbrief.video.pipeline import NotReady, PipelineError, run
from test_video import VIDEO, SUMMARY, DAY, NOW


RESULT = {'accessible': True, 'duration_seconds': 600, 'summary': SUMMARY,
          'evidence': [{'text': '초반 시장 설명', 'at': 10}, {'text': '후반 다음 장 설명', 'at': 500}]}


def session(result=None, status=200, finish='STOP'):
    data = {'candidates': [{'finishReason': finish, 'content': {'parts': [
        {'text': json.dumps(RESULT if result is None else result)}]}}],
        'usageMetadata': {'promptTokenCount': 10000}}
    return SimpleNamespace(post=lambda *a, **k: SimpleNamespace(status_code=status, json=lambda: data))


def test_video_input_not_caption_fetch(monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
    calls = []
    stub = session()
    def post(url, **kw):
        calls.append((url, kw))
        return stub.post(url, **kw)
    analyze = lambda v: analyze_video(v, SimpleNamespace(post=post))
    state = run(DAY, NOW, tmp_path/'state', tmp_path/'reports', finder=lambda *a: VIDEO,
                fetcher=lambda *a: pytest.fail('caption request'), analyzer=analyze,
                session_check=lambda *a: True)
    assert state['summary'] == SUMMARY
    assert not (tmp_path/'state').exists()
    url, kw = calls[0]
    assert 'fake-key' not in url
    assert kw['json']['contents'][0]['parts'][0]['fileData']['fileUri'] == VIDEO.url
    assert '시각은 추정치' in state['message']


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500])
def test_api_errors_are_safe(monkeypatch, status):
    monkeypatch.setenv('GEMINI_API_KEY', 'secret-not-for-logs')
    with pytest.raises(PipelineError, match=f'HTTP {status}') as e:
        analyze_video(VIDEO, session(status=status))
    assert 'secret-not-for-logs' not in str(e.value)


@pytest.mark.parametrize('problem', ['no_access', 'bad_duration', 'bad_time', 'no_evidence', 'duplicate_evidence', 'incomplete'])
def test_unreliable_response_rejected(monkeypatch, problem):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    r = deepcopy(RESULT)
    if problem == 'no_access': r['accessible'] = False
    if problem == 'bad_duration': r['duration_seconds'] = 0
    if problem == 'bad_time': r['summary']['headline']['at'] = 600
    if problem == 'no_evidence': r['evidence'] = []
    if problem == 'duplicate_evidence': r['evidence'][1]['at'] = 10
    with pytest.raises(PipelineError):
        analyze_video(VIDEO, session(r, finish='MAX_TOKENS' if problem == 'incomplete' else 'STOP'))


def test_missing_key_never_calls_api(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(PipelineError, match='GEMINI_API_KEY'):
        analyze_video(VIDEO, SimpleNamespace(post=lambda *a, **k: pytest.fail('network')))


def test_integer_valued_json_numbers_normalized(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    r = deepcopy(RESULT)
    r['duration_seconds'] = 600.0
    r['summary']['headline']['at'] = 0.0
    summary, meta = analyze_video(VIDEO, session(r))
    assert type(summary['headline']['at']) is int
    assert type(meta['duration_seconds']) is int
