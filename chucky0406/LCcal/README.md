---
title: Lung Recurrence Calculator
emoji: 🫁
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# 폐암 재발 위험 계산기 (Lung Cancer Recurrence Calculator)

SNUH 흉부외과 폐암 수술 코호트 기반, 수술 후 개인별 재발 위험을 추정하는 웹 계산기입니다.

- 전체 재발 확률 및 시간별 hazard
- 부위별(폐·림프절·뇌·뼈·복부) 재발 위험과 발생 시기
- 병리 리포트 사진 OCR 자동입력 (서버가 API 키를 보관·대행 → 접속자는 키 불필요)
- PDF 인쇄/저장

환자 데이터는 서버에 저장되지 않고 브라우저 내에서 처리됩니다. 모델은 집계 계수만 포함하며 환자 개별정보는 포함하지 않습니다.

> 연구·교육용. 임상 의사결정의 단독 근거로 사용하지 마십시오.

## 배포 (Hugging Face Spaces, Docker)
1. 이 저장소 파일(`Dockerfile`, `server.py`, `deploy/`)을 Space에 업로드
2. Space **Settings → Secrets** 에 `ANTHROPIC_API_KEY` 추가 (OCR용; 없으면 OCR만 비활성)
3. 자동 빌드 후 공개 URL에서 사용
