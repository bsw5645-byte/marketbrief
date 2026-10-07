"""Channel-isolated delivery with per-day receipts; no tokens in log messages."""
import json
import os
import requests


def bold_entities(text):
    """Style plain-text headings using Telegram's UTF-16 entity offsets."""
    entities = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip('\r\n')
        start = 0
        selected = ''
        if stripped.startswith(('📊', '📌', '🔥', '🛡', '🔻', '↔', '🔄', '👀')):
            selected = stripped
        elif stripped.startswith('• ') and ' | ' in stripped:
            start = 2
            selected = stripped[2:].split(' | ', 1)[0]
        if selected:
            entities.append({'type': 'bold', 'offset': offset + len(stripped[:start].encode('utf-16-le')) // 2,
                             'length': len(selected.encode('utf-16-le')) // 2})
        offset += len(line.encode('utf-16-le')) // 2
    return entities


def chunks(text, limit=3500):
    # Count UTF-16 units to leave room for Telegram's Unicode length handling.
    part = ''
    for line in text.splitlines(keepends=True):
        for char in line:
            if len((part + char).encode('utf-16-le')) // 2 > limit:
                yield part
                part = ''
            part += char
    if part:
        yield part


def deliver(message, receipt, save_receipt, session=None):
    session = session or requests.Session()
    failures = []
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        failures.append('Telegram: 필수 Secret 누락')
    else:
        for i, part in enumerate(chunks(message)):
            key = f'telegram:{i}'
            if receipt.get(key):
                continue
            try:
                r = session.post(f'https://api.telegram.org/bot{token}/sendMessage',
                                 json={'chat_id': chat, 'text': part, 'entities': bold_entities(part)}, timeout=30)
                r.raise_for_status()
                if not r.json().get('ok'):
                    raise ValueError('API rejected')
                receipt[key] = True
                save_receipt(receipt)
            except Exception:
                failures.append('Telegram: 전송 실패(상태 확인 후 재실행)')
                break
    # Kakao is the established short-link notification, not a truncated report.
    kakao_id = os.environ.get('KAKAO_REST_API_KEY')
    refresh = os.environ.get('KAKAO_REFRESH_TOKEN')
    if not kakao_id or not refresh:
        failures.append('Kakao: 필수 Secret 누락')
    elif not receipt.get('kakao'):
        try:
            data = {'grant_type': 'refresh_token', 'client_id': kakao_id, 'refresh_token': refresh}
            if os.environ.get('KAKAO_CLIENT_SECRET'):
                data['client_secret'] = os.environ['KAKAO_CLIENT_SECRET']
            r = session.post('https://kauth.kakao.com/oauth/token', data=data, timeout=30)
            r.raise_for_status()
            payload = r.json()
            access = payload['access_token']
            if payload.get('refresh_token') and payload['refresh_token'] != refresh:
                # Never persist credentials in an Actions artifact.
                print('Kakao refresh token 재발급 감지: Secrets 갱신이 필요합니다.')
            url = 'https://t.me/Bong_moring_Brief_bot'
            template = {'object_type': 'text', 'text': '장마감 주도주·테마 브리핑입니다\n' + url,
                        'link': {'web_url': url, 'mobile_web_url': url}}
            r = session.post('https://kapi.kakao.com/v2/api/talk/memo/default/send',
                             headers={'Authorization': 'Bearer ' + access},
                             data={'template_object': json.dumps(template, ensure_ascii=False)}, timeout=30)
            r.raise_for_status()
            if r.json().get('result_code') != 0:
                raise ValueError('API rejected')
            receipt['kakao'] = True
            save_receipt(receipt)
        except Exception:
            failures.append('Kakao: 전송 실패(Secrets/토큰 만료 확인)')
    return failures
