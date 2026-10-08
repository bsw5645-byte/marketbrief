# 이세무사TV 장마감 영상 요약

기존 KRX/아침 브리핑과 별도로 실행합니다. YouTube 공개 영상 URL을
Gemini API의 fileData 입력으로 전달하며, GitHub에서 자막을 요청하지 않습니다.

## 설정

- GitHub Secret GEMINI_API_KEY (Google AI Studio 발급).
- 기존 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 재사용.
- GEMINI_MODEL repository variable로 변경 가능. 기본 gemini-3.8-flash.
- YouTube 영상 입력은 Google의 미리보기 기능이므로 변경/실패 가능.

## 실행

평일 한국시간 15:40, 16:00부터 20:30까지 30분 간격, 21:00에 확인합니다.
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
