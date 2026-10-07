"""Date-strict KRX adapter. No fallback to the preceding business day."""
from datetime import datetime, timedelta
from time import sleep
from zoneinfo import ZoneInfo
import os
import requests
from .engine import DataNotReady, validate

KST = ZoneInfo('Asia/Seoul')


def calendar():
    import exchange_calendars
    return exchange_calendars.get_calendar('XKRX')


def session_dates(day, count=21):
    c = calendar()
    if not c.is_session(day):
        return []
    return [s.date().isoformat() for s in c.sessions_window(day, -count)]


def is_after_close(now):
    c = calendar()
    day = now.date().isoformat()
    return c.is_session(day) and now >= c.session_close(day).to_pydatetime() + timedelta(minutes=10)


class KRXProvider:
    def __init__(self):
        if not os.environ.get('KRX_ID') or not os.environ.get('KRX_PW'):
            raise DataNotReady('GitHub Secrets에 KRX_ID와 KRX_PW를 등록하세요.')
        # pykrx creates its authenticated session on import. Bound every request
        # before import, including login; HTTP exceptions are never logged verbatim.
        original = requests.sessions.Session.request
        def bounded_request(session, method, url, **kwargs):
            kwargs.setdefault('timeout', (10, 30))
            return original(session, method, url, **kwargs)
        requests.sessions.Session.request = bounded_request
        from pykrx import stock
        self.stock = stock
        self.names = {}

    def call(self, function, *args, **kwargs):
        sleep(1)  # respect upstream rate guidance
        return function(*args, **kwargs)

    def collect(self, day):
        dates = session_dates(day, 2)
        if not dates:
            raise DataNotReady('휴장일')
        start, end = (d.replace('-', '') for d in dates)
        indices = {}
        records = []
        for market, ticker in [('KOSPI', '1001'), ('KOSDAQ', '2001')]:
            index = self.call(self.stock.get_index_ohlcv_by_date, start, end, ticker, name_display=False)
            if index.empty or [d.date().isoformat() for d in index.index] != dates:
                raise DataNotReady(f'{market} 요청일 지수 미제공')
            closes = index['종가'].tolist()
            if min(closes) <= 0:
                raise DataNotReady(f'{market} 지수 오류')
            indices[market] = (float(closes[1]) / float(closes[0]) - 1) * 100
            frame = self.call(self.stock.get_market_ohlcv_by_ticker, end, market=market, alternative=False)
            if len(frame) < 500 or not {'종가', '거래대금', '등락률'}.issubset(frame.columns):
                raise DataNotReady(f'{market} 전체 시세 부족')
            for code, row in frame.iterrows():
                code = str(code).zfill(6)
                if code not in self.names:
                    self.names[code] = self.stock.get_market_ticker_name(code) or code
                records.append(dict(code=code, name=self.names[code], market=market,
                                    close=float(row['종가']), turnover=float(row['거래대금']),
                                    change=float(row['등락률'])))
        snapshot = dict(schema=1, date=day, collected_at=datetime.now(KST).isoformat(),
                        source='KRX via pykrx 1.2.9', indices=indices, stocks=records)
        validate(snapshot)
        return snapshot
