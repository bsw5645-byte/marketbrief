from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import pytest
from marketbrief.closing.engine import DataNotReady, analyze, compare, render, validate
from marketbrief.closing.delivery import chunks, deliver
from marketbrief.closing.provider import KRXProvider, is_after_close, session_dates
from marketbrief.closing.__main__ import main


CONFIG = {'min_turnover_krw': 30e9, 'themes': {'테스트 반도체': ['000010', '000020', '000030']}}


def snapshot(day, strong=False):
    stocks = [dict(code=f'{i:05}0', name=f'가상종목{i}', market='KOSPI' if i <= 3 else 'KOSDAQ',
                   close=10000, turnover=100e9 if strong and i <= 3 else 30e9,
                   change=6 if strong and i <= 3 else 0) for i in range(1, 11)]
    return dict(schema=1, date=day, stocks=stocks, indices={'KOSPI': 0.5, 'KOSDAQ': -0.5})


def history():
    return [snapshot(f'2026-09-{d:02}') for d in (21, 22, 23, 24, 25, 28)]


def test_emergence_and_market_relative_strength():
    old = history()
    r = analyze(snapshot('2026-09-29', True), old, CONFIG)
    compare(r, analyze(old[-1], old[:-1], CONFIG))
    t = r['themes'][0]
    assert t['status'] == '강세' and t['transition'] == '신규 강세'
    assert t['relative'] == 5.5 and t['ratio'] == pytest.approx(10 / 3)
    assert all(s['new'] for s in r['leaders'])
    assert '순유입 자금이 아닙니다' in render(r)


def test_future_and_same_day_excluded():
    current = snapshot('2026-09-29', True)
    expected = analyze(current, history(), CONFIG)
    assert analyze(current, history() + [current, snapshot('2099-01-01', True)], CONFIG) == expected


def test_no_history_is_not_new_strength():
    r = analyze(snapshot('2026-09-29', True), [], CONFIG)
    compare(r, None)
    assert r['themes'][0]['score'] is None
    assert r['themes'][0]['transition'] is None
    assert not any(s['new'] for s in r['leaders'])


def test_missing_member_is_not_weakness():
    s = snapshot('2026-09-29', True)
    s['stocks'].pop(0)
    t = analyze(s, history(), CONFIG)['themes'][0]
    assert t['score'] is None and t['status'] == '구성종목 데이터 부족'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1])
def test_invalid_turnover_rejected(value):
    s = snapshot('2026-09-29')
    s['stocks'][0]['turnover'] = value
    with pytest.raises(DataNotReady):
        validate(s)


def test_weakening_and_leader_change():
    old = history()
    old[-1] = snapshot(old[-1]['date'], True)
    current = snapshot('2026-09-29')
    for s in current['stocks'][:3]:
        s['change'] = -4
    current['stocks'][0]['turnover'] = 31e9
    r = compare(analyze(current, old, CONFIG), analyze(old[-1], old[:-1], CONFIG))
    assert r['themes'][0]['transition'] == '강세 이탈'
    assert r['themes'][0]['status'] == '약화'
    assert r['themes'][0]['leader'] != r['themes'][0]['previous_leader']


def test_holiday_and_close_guard():
    assert session_dates('2026-10-09') == []
    assert session_dates('2026-10-07', 2) == ['2026-10-06', '2026-10-07']
    assert len(session_dates('2026-10-07')) == 21
    assert not is_after_close(datetime(2026, 10, 7, 15, 39, tzinfo=ZoneInfo('Asia/Seoul')))
    assert is_after_close(datetime(2026, 10, 7, 15, 40, tzinfo=ZoneInfo('Asia/Seoul')))


def test_missing_credentials_fail_before_network(monkeypatch):
    monkeypatch.delenv('KRX_ID', raising=False)
    monkeypatch.delenv('KRX_PW', raising=False)
    with pytest.raises(DataNotReady, match='KRX_ID'):
        KRXProvider()


def test_provider_rejects_stale_index():
    import pandas as pd
    class Stock:
        @staticmethod
        def get_index_ohlcv_by_date(*args, **kwargs):
            return pd.DataFrame({'종가': [100]}, index=pd.to_datetime(['2026-10-06']))
    provider = object.__new__(KRXProvider)
    provider.stock = Stock()
    provider.call = lambda f, *a, **kw: f(*a, **kw)
    with pytest.raises(DataNotReady, match='요청일 지수 미제공'):
        provider.collect('2026-10-07')


def test_provider_rejects_partial_market():
    import pandas as pd
    class Stock:
        @staticmethod
        def get_index_ohlcv_by_date(*args, **kwargs):
            return pd.DataFrame({'종가': [100, 101]}, index=pd.to_datetime(['2026-10-06', '2026-10-07']))
        @staticmethod
        def get_market_ohlcv_by_ticker(*args, **kwargs):
            assert kwargs['alternative'] is False
            return pd.DataFrame({'종가': [100], '거래대금': [1000], '등락률': [1]})
    provider = object.__new__(KRXProvider)
    provider.stock = Stock()
    provider.call = lambda f, *a, **kw: f(*a, **kw)
    with pytest.raises(DataNotReady, match='전체 시세 부족'):
        provider.collect('2026-10-07')


def test_telegram_unicode_split_roundtrip():
    text = '📊한글' * 4000
    parts = list(chunks(text))
    assert ''.join(parts) == text
    assert all(len(p.encode('utf-16-le')) // 2 <= 3500 for p in parts)


class Response:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class Session:
    def __init__(self, fail_telegram=False):
        self.calls = []
        self.fail_telegram = fail_telegram
    def post(self, url, **kwargs):
        self.calls.append(url)
        if 'telegram.org' in url:
            if self.fail_telegram:
                raise RuntimeError('secret-containing-url-must-not-leak')
            return Response({'ok': True})
        if 'kauth' in url:
            return Response({'access_token': 'test-access'})
        return Response({'result_code': 0})


def credentials(monkeypatch):
    for k in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'KAKAO_REST_API_KEY', 'KAKAO_REFRESH_TOKEN'):
        monkeypatch.setenv(k, 'test')


def test_channel_failure_isolated_and_retry_deduplicated(monkeypatch):
    credentials(monkeypatch)
    receipt = {}
    saved = []
    s = Session(fail_telegram=True)
    errors = deliver('hello', receipt, lambda r: saved.append(deepcopy(r)), s)
    assert len(errors) == 1 and 'secret' not in errors[0]
    assert receipt == {'kakao': True}
    s = Session()
    assert deliver('hello', receipt, lambda r: None, s) == []
    assert len(s.calls) == 1 and 'telegram' in s.calls[0]
    assert deliver('hello', receipt, lambda r: None, s) == []
    assert len(s.calls) == 1


def test_fixture_cannot_send(monkeypatch):
    monkeypatch.setattr('sys.argv', ['radar', '--fixture', 'anything', '--send'])
    assert main() == 1


def test_end_to_end_fixture(tmp_path, monkeypatch):
    f = tmp_path / 'fixture.json'
    f.write_text(json.dumps({'current': snapshot('2026-09-29', True), 'history': history()}))
    c = tmp_path / 'config.json'
    c.write_text(json.dumps(CONFIG))
    out = tmp_path / 'out'
    monkeypatch.setattr('sys.argv', ['radar', '--fixture', str(f), '--config', str(c), '--output', str(out)])
    assert main() == 0
    text = (out / 'closing-report.txt').read_text()
    assert '실제 시세 아님' in text and '신규 강세' in text
    assert json.loads((out / 'closing-report.json').read_text())['baseline_days'] == 6
