from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from marketbrief.video.pipeline import (
    CHANNEL_ID, KST, NotReady, PipelineError, Video, deliver_telegram,
    fetch_transcript, load_json, parse_feed, render, run, summarize, validate_summary,
    find_video_api,
)

DAY = date(2026, 10, 7)
NOW = datetime(2026, 10, 7, 20, 0, tzinfo=KST)
VIDEO = Video('YTU7rE9cEnQ', '개인은 3조 샀는데 외국인·기관은 팔았다? 7,000선에 또 막힌 코스피',
              '2026-10-07T10:00:00Z')
ROWS = [{'start': float(i * 5), 'duration': 5.0, 'text': '가상의 테스트용 한국어 자막 내용입니다. 실제 영상 내용이 아닙니다.'}
        for i in range(10)]
SUMMARY = {'headline': {'text': '테스트 시장 흐름', 'at': 0},
           'market': [{'text': '테스트 수급', 'at': 5}],
           'strong': [], 'weak': [], 'watch': [{'text': '테스트 체크포인트', 'at': 45}]}
META = {'language': 'ko', 'generated': True, 'segments': 10, 'characters': 400}


def feed(entries, channel=CHANNEL_ID):
    return (f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
            f'<yt:channelId>{channel}</yt:channelId>' + ''.join(
            f'<entry><yt:videoId>{vid}</yt:videoId><title>{title}</title><published>{when}</published></entry>'
            for vid, title, when in entries) + '</feed>')


def entry(title=None, when=None, vid='YTU7rE9cEnQ'):
    return vid, title or VIDEO.title, when or VIDEO.published_at


def test_date_strict_latest_kst_and_title_filter():
    xml = feed([entry(), entry(when='2026-10-06T10:00:00Z'),
                entry('[LIVE] 모닝브리핑 코스피', '2026-10-07T10:20:00Z', 'abcdefghijk'),
                entry('월간 강연 코스피', '2026-10-07T10:30:00Z', 'abcdefghijL'),
                entry('코스닥 장마감', '2026-10-07T10:40:00Z', 'abcdefghijM')])
    assert parse_feed(xml, DAY, NOW).video_id == 'abcdefghijM'


@pytest.mark.parametrize('when', ['2026-10-06T10:00:00Z', '2026-10-07T05:00:00Z', '2026-10-07T12:00:00Z'])
def test_previous_premarket_and_future_rejected(when):
    with pytest.raises(NotReady):
        parse_feed(feed([entry(when=when)]), DAY, NOW)


def test_wrong_channel_rejected():
    with pytest.raises(PipelineError):
        parse_feed(feed([entry()], channel='wrong'), DAY, NOW)


def test_feed_root_channel_id_without_uc_prefix():
    assert parse_feed(feed([entry()], channel=CHANNEL_ID[2:]), DAY, NOW).video_id == VIDEO.video_id


def test_entry_wrong_channel_rejected():
    xml = feed([entry()]).replace('<entry>', '<entry><yt:channelId>wrong</yt:channelId>')
    with pytest.raises(PipelineError):
        parse_feed(xml, DAY, NOW)


def test_explicit_id_still_date_checked():
    assert parse_feed(feed([entry('사용자 지정 영상')]), DAY, NOW, VIDEO.video_id).video_id == VIDEO.video_id
    with pytest.raises(NotReady):
        parse_feed(feed([entry(when='2026-10-06T10:00:00Z')]), DAY, NOW, VIDEO.video_id)


def api_session(items=None, status=200):
    responses = iter([
        {'items': [{'id': CHANNEL_ID, 'contentDetails': {'relatedPlaylists': {'uploads': 'uploads-id'}}}]},
        {'items': items if items is not None else [{'snippet': {'videoOwnerChannelId': CHANNEL_ID, 'title': VIDEO.title},
                      'contentDetails': {'videoId': VIDEO.video_id, 'videoPublishedAt': VIDEO.published_at}}]},
    ])
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        body = next(responses) if status == 200 else {'error': {'errors': [{'reason': 'accessNotConfigured'}], 'message': 'secret'}}
        return SimpleNamespace(status_code=status, json=lambda: body)
    return SimpleNamespace(get=get), calls


def test_official_api_fallback_uses_key_and_original_publish_time(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'secret')
    stub, calls = api_session()
    assert find_video_api(DAY, NOW, session=stub) == VIDEO
    assert len(calls) == 2
    assert all('secret' not in url and kw['params']['key'] == 'secret' for url, kw in calls)
    assert calls[1][1]['params']['playlistId'] == 'uploads-id'


@pytest.mark.parametrize('owner,when,error', [('other', VIDEO.published_at, PipelineError),
                                           (CHANNEL_ID, '2026-10-06T10:00:00Z', NotReady)])
def test_api_wrong_channel_or_previous_day_rejected(monkeypatch, owner, when, error):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'secret')
    items = [{'snippet': {'videoOwnerChannelId': owner, 'title': VIDEO.title},
              'contentDetails': {'videoId': VIDEO.video_id, 'videoPublishedAt': when}}]
    stub, _ = api_session(items)
    with pytest.raises(error):
        find_video_api(DAY, NOW, session=stub)


def test_api_disabled_error_safe_and_actionable(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'secret')
    stub, _ = api_session(status=403)
    with pytest.raises(PipelineError, match='YouTube Data API v3 활성화 필요') as error:
        find_video_api(DAY, NOW, session=stub)
    assert 'secret' not in str(error.value)


def test_complete_transcript_and_language():
    seen = []
    transcript = SimpleNamespace(to_raw_data=lambda: ROWS, language_code='ko', is_generated=True)
    api = SimpleNamespace(fetch=lambda video, languages: seen.append((video, languages)) or transcript)
    rows, meta = fetch_transcript(VIDEO.video_id, api)
    assert rows == ROWS and meta['segments'] == 10
    assert seen == [(VIDEO.video_id, ['ko', 'ko-KR'])]


def test_short_transcript_not_summarized():
    transcript = SimpleNamespace(to_raw_data=lambda: ROWS[:2])
    with pytest.raises(NotReady):
        fetch_transcript(VIDEO.video_id, SimpleNamespace(fetch=lambda *a, **k: transcript))


def test_cloud_block_not_bypassed():
    def fail(*args, **kwargs):
        raise type('RequestBlocked', (Exception,), {})('private diagnostic')
    with pytest.raises(PipelineError, match='우회하지') as error:
        fetch_transcript(VIDEO.video_id, SimpleNamespace(fetch=fail))
    assert 'private diagnostic' not in str(error.value)


@pytest.mark.parametrize('change', ['wrong_at', 'long_text', 'extra', 'invalid_at_type', 'too_many'])
def test_summary_validation(change):
    s = deepcopy(SUMMARY)
    if change == 'wrong_at': s['headline']['at'] = 1234
    elif change == 'long_text': s['headline']['text'] = '가' * 161
    elif change == 'extra': s['invented'] = []
    elif change == 'invalid_at_type': s['headline']['at'] = True
    elif change == 'too_many': s['market'] *= 4
    with pytest.raises(PipelineError): validate_summary(s, ROWS)


def response(payload, status=200):
    return SimpleNamespace(status_code=status, json=lambda: payload,
                           raise_for_status=lambda: None)


def test_full_transcript_passed_to_gpt_and_no_storage(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-key')
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response({'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(SUMMARY)}]}]})
    assert summarize(VIDEO, ROWS, SimpleNamespace(post=post)) == SUMMARY
    payload = calls[0][1]['json']
    assert payload['store'] is False
    assert '[45초] ' + ROWS[-1]['text'] in payload['input']
    assert all(r['text'] in payload['input'] for r in ROWS)
    assert payload['text']['format']['strict'] is True


def test_missing_key_no_network(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(PipelineError, match='OPENAI_API_KEY'):
        summarize(VIDEO, ROWS, SimpleNamespace(post=lambda *a, **k: pytest.fail('network')))


def test_incomplete_gpt_response_is_not_used(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-key')
    with pytest.raises(PipelineError):
        summarize(VIDEO, ROWS, SimpleNamespace(post=lambda *a, **k: response({'status': 'incomplete'})))


def test_render_clear_labels_and_source():
    text = render(VIDEO, SUMMARY, DAY)
    assert '한눈에 보는 오늘' in text and '강한 산업' in text
    assert VIDEO.url in text and '(0:45)' in text
    assert '명확히 언급되지 않음' in text and '매매 신호 아님' in text


def test_receipts_skip_completed_parts(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'fake-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'fake-chat')
    calls = []
    session = SimpleNamespace(post=lambda *a, **k: calls.append(k) or response({'ok': True}))
    receipt = {}
    saved = []
    save = lambda r: saved.append(deepcopy(r))
    deliver_telegram('한글🙂' * 1800, receipt, save, session)
    count = len(calls)
    assert count > 1 and saved[0]['0'] == 'pending' and receipt['complete']
    deliver_telegram('한글🙂' * 1800, receipt, save, session)
    assert len(calls) == count


def test_timeout_not_automatically_retried(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'fake-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'fake-chat')
    calls = []
    def post(*a, **k):
        calls.append(1)
        raise TimeoutError()
    receipt = {}
    for _ in range(2):
        with pytest.raises(PipelineError):
            deliver_telegram('테스트', receipt, lambda r: None, SimpleNamespace(post=post))
    assert len(calls) == 1 and receipt['0'] == 'pending'


def test_explicit_api_rejection_can_retry(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'fake-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'fake-chat')
    receipt = {}
    with pytest.raises(PipelineError):
        deliver_telegram('테스트', receipt, lambda r: None,
                         SimpleNamespace(post=lambda *a, **k: response({'ok': False}, 429)))
    assert '0' not in receipt


def deps():
    return dict(finder=lambda *a: VIDEO, fetcher=lambda *a: (ROWS, META),
                summarizer=lambda *a: SUMMARY, session_check=lambda *a: True)


def test_preview_does_not_create_delivery_state(tmp_path):
    run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', **deps())
    assert not (tmp_path / 'state').exists()
    assert (tmp_path / 'reports' / '2026-10-07.txt').exists()


def test_probe_no_gpt_or_raw_transcript(tmp_path):
    options = deps()
    options['summarizer'] = lambda *a: pytest.fail('GPT called')
    run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', fetch_only=True, **options)
    data = (tmp_path / 'reports' / 'probe.json').read_text()
    assert ROWS[0]['text'] not in data and not (tmp_path / 'state').exists()


def test_no_video_no_gpt_no_send(tmp_path):
    options = deps()
    def unavailable(*a): raise NotReady('waiting')
    options.update(finder=unavailable, summarizer=lambda *a: pytest.fail('GPT called'),
                   sender=lambda *a: pytest.fail('sent'))
    with pytest.raises(NotReady): run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', send=True, **options)


def test_holiday_no_network(tmp_path):
    options = deps()
    options.update(session_check=lambda *a: False, finder=lambda *a: pytest.fail('network'))
    assert run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', **options) is None


def test_completed_day_skips_all_network(tmp_path):
    def sender(message, receipt, save):
        receipt['complete'] = True
        save(receipt)
    options = deps()
    run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', send=True, sender=sender, **options)
    options['finder'] = lambda *a: pytest.fail('network')
    state = run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', send=True, **options)
    assert state['complete']


def test_partial_delivery_keeps_cached_message_and_no_new_gpt(tmp_path):
    def fail(message, receipt, save):
        raise PipelineError('test failure')
    options = deps()
    with pytest.raises(PipelineError):
        run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', send=True, sender=fail, **options)
    options.update(finder=lambda *a: pytest.fail('discovery'), fetcher=lambda *a: pytest.fail('captions'),
                   summarizer=lambda *a: pytest.fail('GPT'))
    sent = []
    run(DAY, NOW, tmp_path / 'state', tmp_path / 'reports', send=True,
        sender=lambda message, receipt, save: sent.append(message), **options)
    assert sent == [render(VIDEO, SUMMARY, DAY)]


def test_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / '2026-10-07.json'
    path.write_text('[]')
    with pytest.raises(PipelineError): load_json(path)


def test_cli_historical_send_rejected(monkeypatch):
    from marketbrief.video.__main__ import main
    monkeypatch.setattr('sys.argv', ['video', '--date', '2020-01-01', '--send'])
    with pytest.raises(SystemExit) as error: main()
    assert error.value.code == 2
