# 이세무사TV 장마감 영상 요약

기존 KRX/아침 브리핑과 별도로 실행합니다. YouTube 공개 영상 URL을
Gemini Interactions API의 video 입력으로 전달하며, GitHub에서 자막을 요청하지 않습니다.
store=false로 호출하고 completed 상태의 단일 최종 출력만 사용합니다.

## 설정

- GitHub Secret GEMINI_API_KEY (Google AI Studio 발급).
- RSS 오류 시 YouTube Data API v3로 업로드 목록을 확인합니다. 같은 Google
  프로젝트에서 이 API가 활성화되어 있어야 합니다. 필요하면 별도 Secret
  YOUTUBE_API_KEY를 등록하며, 없으면 GEMINI_API_KEY를 사용합니다.
- 기존 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 재사용.
- GEMINI_MODEL repository variable로 변경 가능. 기본 gemini-3.8-flash.
- 기본 모델의 일시적인 HTTP 503만 gemini-3.7-flash로 한 번 대체합니다.
- YouTube 영상 입력은 Google의 미리보기 기능이므로 변경/실패 가능.

## 실행

평일 한국시간 18:00에 한 번 확인합니다.
GitHub 예약 실행은 지연될 수 있습니다. KRX 휴장일과 장마감 전에는 생략합니다.
대상 채널 UCowHl0BGalL433P6bCBgeKA의 당일 15:40 이후 시장 관련 영상만
선택하며 전날 영상을 오늘 영상으로 보내지 않습니다.

Actions → BONG YouTube Close Summary → Run workflow:
- 미리보기: send=false.
- 당일 발송: send=true.
- 과거 테스트: target_date=2026-10-07, video_id=YTU7rE9cEnQ, send=false.

영상 내용을 읽지 못했거나 API 오류/응답 미완성/요약 구조 오류이면 발송하지
않습니다. 다음 실행에서 재확인합니다. 근거 시각은 Gemini 추정치이며
실제 자막 행과 대조해 검증된 시각이 아닙니다. 형식 검증은 내용 정확성을
보장하지 않으므로 초기 실제 영상 검토가 필요합니다.
기본값은 하루 최초 요약에 영상 입력 1회만 사용합니다(무료 등급 사용량 절약).
같은 모델의 두 번째 재검토는 정확도를 보장하지 못해 기본으로 끕니다.
필요하면 환경 변수 GEMINI_REVIEW=1로 켤 수 있습니다(워크플로 env에 추가 필요). 이때 영상 입력이 2회 필요합니다.
긴 영상은 우선 백그라운드 실행으로 제출하고 완료 상태를 최대 12분간 확인합니다.
공개 YouTube URL과 백그라운드 요청이 거절되면 공식 generateContent 영상 URL 방식으로 한 번 전환합니다.
Gemini가 일시적으로 혼잡(HTTP 503)하면 대체 모델 1회, 30초 후 1회만 다시 시도합니다.
한도 초과(HTTP 429)는 다시 시도하지 않습니다. 영상 길이를 넘는 시각이 붙은
항목은 추적할 수 없으므로 빼고 발송하며, 핵심 한 줄의 시각이 틀리면 발송하지 않습니다.

영상 발언과 전망만 재서술합니다. 상승 산업이 없으면 빈 항목으로 표시하고,
거래대금을 순유입으로 표현하지 않습니다. 원문 대본은 저장/재배포하지 않습니다.
미리보기 artifact에 요약, 영상 정보, 짧게 재서술한 검토용 근거와 토큰 사용량만
저장합니다. API 오류 본문과 키는 출력하지 않습니다.

완료된 발송과 부분 발송은 artifact receipt에 기록합니다. 재실행은 저장된
요약을 재사용하고 성공한 부분은 재전송하지 않습니다. 수신 결과가 불명확한
타임아웃은 자동 재전송하지 않습니다. 상태 복원 실패도 발송을 멈춥니다.

## 검증

유닛 테스트와 실제 GitHub Gemini 영상 미리보기 결과를 확인한 뒤 활성화합니다.
몽클라우드 설치 경로는 사용하지 않습니다. 이전 자막/GPT 코드는 테스트 및
명시적 --provider captions 용도로만 남아 있으며 기본 실행은 gemini입니다.
