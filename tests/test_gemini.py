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
    data = {'status': 'completed' if finish == 'STOP' else 'incomplete',
            'steps': [{'type': 'model_output', 'content': [
                {'type': 'text', 'text': json.dumps(RESULT if result is None else result)}]}],
            'usage': {'total_input_tokens': 10000}}
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
    assert url.endswith('/v1beta/interactions')
    assert kw['json']['input'][0] == {'type': 'video', 'uri': VIDEO.url}
    assert kw['json']['store'] is False
    assert kw['json']['response_format'][0]['mime_type'] == 'application/json'
    assert '시각은 추정치' in state['message']
    assert len(calls) == 2
    assert '검토 대상 초안' in calls[1][1]['json']['input'][1]['text']


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


def test_review_corrects_draft(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    wrong = deepcopy(RESULT)
    wrong['summary']['market'][0]['text'] = '코스피 2,380 마감'
    responses = iter([session(wrong), session(RESULT)])
    summary, meta = analyze_video(VIDEO, SimpleNamespace(post=lambda *a, **k: next(responses).post(*a, **k)))
    assert summary == SUMMARY
    assert meta['reviewed'] and meta['review_changed_summary']


def test_invalid_draft_timestamp_can_be_corrected_by_review(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    wrong = deepcopy(RESULT)
    wrong['summary']['market'][0]['at'] = 709
    responses = iter([session(wrong), session(RESULT)])
    summary, _ = analyze_video(VIDEO, SimpleNamespace(post=lambda *a, **k: next(responses).post(*a, **k)))
    assert summary == SUMMARY


def test_review_failure_blocks_delivery(monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    responses = iter([session(), session(status=429)])
    analyzer = lambda v: analyze_video(v, SimpleNamespace(post=lambda *a, **k: next(responses).post(*a, **k)))
    with pytest.raises(PipelineError, match='HTTP 429'):
        run(DAY, NOW, tmp_path/'state', tmp_path/'reports', finder=lambda *a: VIDEO,
            analyzer=analyzer, send=True, sender=lambda *a: pytest.fail('Telegram'), session_check=lambda *a: True)


def test_one_model_fallback_on_503_then_review_same_model(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    responses = iter([session(status=503), session(), session()])
    models = []
    def post(url, **kw):
        models.append(kw['json']['model'])
        return next(responses).post(url, **kw)
    _, meta = analyze_video(VIDEO, SimpleNamespace(post=post))
    assert models == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.7-flash']
    assert meta['model'] == 'gemini-3.7-flash'


@pytest.mark.parametrize('status', ['in_progress', 'requires_action', 'failed', 'cancelled', 'incomplete'])
def test_interaction_must_be_completed(monkeypatch, status):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    data = session().post().json()
    data['status'] = status
    stub = SimpleNamespace(post=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: data))
    with pytest.raises(PipelineError, match='응답 미완성'):
        analyze_video(VIDEO, stub)


def test_only_one_model_output_is_accepted(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake')
    data = session().post().json()
    data['steps'].append(deepcopy(data['steps'][0]))
    stub = SimpleNamespace(post=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: data))
    with pytest.raises(PipelineError, match='응답 미완성'):
        analyze_video(VIDEO, stub)

