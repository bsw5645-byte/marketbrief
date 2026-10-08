# 이세무사TV 장마감 영상 요약

기존 15:40 KRX 브리핑과 별도의 워크플로우입니다. 당일 장마감 이후
게시된 대상 채널 영상의 한국어 자막 전체를 메모리에서 읽고 GPT가 재서술한
짧은 요약만 Telegram으로 보냅니다. 원문 자막은 저장소나 Actions artifact에
올리지 않습니다. 자동자막 오인식과 발언자의 전망은 확정 사실과 다릅니다.

## 최초 설정

- 기존 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` Secrets를 재사용합니다.
- 새 Secret `OPENAI_API_KEY`가 필요합니다. 채팅에 키를 붙이지 마세요.
  ChatGPT 이용권과 API 과금은 별도입니다. API 계정의 예산도 설정하세요.
- 모델은 기본 `gpt-5-mini`. Repository variable `OPENAI_MODEL`로 변경 가능.
  해당 API 계정에서 사용 가능한 Responses 모델이어야 합니다.
- 채널 ID `UCowHl0BGalL433P6bCBgeKA`: 슈퍼개미 이세무사TV.

## 동작 및 테스트

한국시간 평일 15:40, 16:00~20:30 반시간 간격, 21:00에 확인합니다.
GitHub schedule은 정확한 실행 시각을 보장하지 않습니다.
XKRX 휴장일/장마감 전에는 실행하지 않으며, 전날 영상을 오늘 영상으로
사용하지 않습니다. 제목에 시장 관련 문구가 있고 장전/LIVE/강의가 아닌
당일 15:40 이후 최신 영상만 선택합니다. 채널 제목 형식이 변하면
`INCLUDE`/`EXCLUDE`를 갱신해야 합니다.

Actions → BONG YouTube Close Summary → Run workflow:

1. 먼저 `fetch_only=true`, `send=false`로 자막 수집을 검증합니다.
2. 요약 미리보기: `fetch_only=false`, `send=false` (API 비용 발생).
3. 당일 영상 실제 발송: `fetch_only=false`, `send=true`.

10월 7일 테스트는 `target_date=2026-10-07`,
`video_id=YTU7rE9cEnQ`, `send=false`로만 수행합니다.

영상 미게시/자막 미제공/요약 실패에는 미완성 내용을 발송하지 않고
실패 상태를 artifact와 Actions에 남깁니다. 다음 scheduled 실행에서 다시
확인하되 YouTube IP 차단을 프록시/계정 쿠키로 우회하지 않습니다.
클라우드 자막 수집은 사이트 정책에 따라 차단될 수 있으므로 실제
GitHub 테스트 성공 전에는 작동한다고 단정하지 마세요.

요약을 저장한 후 Telegram 파트별 발송 결과를 저장합니다. 재실행 시
같은 내용을 재요약하거나 이미 성공한 파트를 재전송하지 않습니다.
네트워크 타임아웃으로 수신 여부가 불명확한 파트는 `pending`으로 남겨
자동 재전송을 멈춥니다. Telegram에서 실제 수신 여부를 확인한 뒤 상태를
수정해야 합니다. 정상 artifact 복원 실패/상태 손상에도 발송을 중단합니다.

## 완료 기준

유닛 테스트 통과, GitHub 실제 자막 수집 성공, OPENAI_API_KEY 설정,
요약 미리보기 검토, 당일 영상 Telegram API 수신 성공을 각각 확인해야
완료입니다. 코드 배포만으로 전체 연결 성공을 뜻하지 않습니다.
