# 🎙️ Agora-Shorts (공론장 중재 AI 쇼츠 자동 생성기)

> **제1회 동양AI빅데이터융합 아이디어 공모전 출품작 (AI융합콘텐츠분야)**  
> **팀명:** 호날두의 아이들 (동양대학교 AI빅데이터융합학과 1학년 김성원, 강휘, 손기윤)

온라인 뉴스·유튜브 댓글창의 감정적 욕설과 혐오 표현을 정량적으로 필터링하고, 그 안에 숨은 찬반 양측의 **핵심 논거(Core Arguments)**만 추출하여 **중립적인 아나운서 톤의 40초 양자 토론 9:16 쇼츠(MP4)**로 자동 전환하는 공론장 중재 콘텐츠 파이프라인입니다.

---

## 📊 1. 실제 유튜브 댓글 빅데이터 수집 및 실증 분석 (`N = 527`)

단순 시뮬레이션이나 가상 데이터가 아닌 **YouTube Data API v3 (`commentThreads.list`)**를 통해 실제 방송 뉴스 영상 12개에서 수집한 **총 527건의 실측 댓글(`data/real_youtube_comments.json`)**을 분석했습니다.

| 프리셋 주제 | 수집 방송 뉴스 영상 (Video ID) | 수집 댓글 수 | 과열·비속어 필터링 | 실제 댓글 여론 편향 (찬:반) | 과열 표본 정화 전·후 과열도 | 쇼츠 논거 배분 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **프리셋 1: 심야 배달 오토바이 소음 규제** | YTN(`vNIXiWyXs90`), MBC(`lt7knjTuuOM`), 연합뉴스TV(`Cs_A2EcMsto`) | **200건** | 58건 (29.0%) | **88% : 12%** | 64.2점 → **14.5점** | **50% : 50%** (각 3턴) |
| **프리셋 2: 공유 전동킥보드 견인·금지** | MBC(`Xt8TRqMuZRc`), SBS(`aI0awk0NBfc`), TBS(`D2hNIe74HEQ`) | **180건** | 32건 (17.8%) | **87% : 13%** | 61.5점 → **14.2점** | **50% : 50%** (각 3턴) |
| **프리셋 3: 고령 운전자 조건부 면허·반납** | MBC(`NKIvNrtdiGA`), KBS(`x3J5hpBci98`), YTN(`yfAshZpECCo`) 외 3건 | **147건** | 36건 (24.5%) | **78% : 22%** | 62.4점 → **14.5점** | **50% : 50%** (각 3턴) |
| **합계 / 평균** | **총 12개 주요 언론사 뉴스 리포트** | **527건** | **126건 (23.9%)** | **평균 84.3% : 15.7%** | **62.8점 → 14.4점 (-48.4pt↓)** | **양측 동등 대표성 보장** |

* **핵심 데이터 발견 (Data Insight):** 실제 뉴스 댓글창은 규제·처벌을 요구하는 분노 여론이 평균 **84.3%**로 과대 대표되어 있으며, 생계형 노동자 생존권·대중교통 사각지대 이동권·인프라 선행 확충 등 **소수 의견(평균 15.7%)은 욕설과 조롱 속에 묻히는 침묵의 나선(Spiral of Silence)** 현상이 확인되었습니다. Agora-Shorts는 이를 **50:50(찬성 3턴 : 반대 3턴)** 기계적 중립 구조로 재구성하여 민주적 숙의 공론장을 복원합니다.

---

## 🛠️ 2. 시스템 아키텍처 및 기술 스택

* **Backend:** Python 3.11 + FastAPI (`app.py`, `presets_data.py`, `render_mp4.py`)
* **Data Collection:** YouTube Data API v3 실시간 댓글 수집 (`fetch_youtube_comments_live`)
* **AI Engine:**
  * **Google Gemini 2.5 Flash (`gemini-2.5-flash`):** `responseSchema` 강제 구조화 JSON 출력 (`issue_title`, `raw_stats`, `debate_script`, `detox_samples`)
  * **Gemini 2.5 Flash Native Audio TTS (`gemini-2.5-flash-preview-tts`):** 찬성(`Kore` 보이스) / 반대(`Puck` 보이스) 듀얼 뉴럴 아나운서 음성 합성 + 브라우저 `Web Speech API` 실시간 폴백
* **9:16 Video Engine:**
  * 서버 사이드: `rsvg-convert` + `ffmpeg` (`libx264`, `yuv420p`, `720x1280`, 24fps, AAC 24kHz) 기반 40초 H.264 `.mp4` 파일 생성 (`static/videos/preset_1~3.mp4`)
  * 클라이언트 사이드: HTML5 `<canvas>` (720×1280) + `MediaRecorder` 실시간 WebM/MP4 녹화 다운로드
* **Cloud Database:** Supabase PostgreSQL (`public.agora_debates` 테이블 + Row Level Security 정책, `supabase_schema.sql`)
* **Data Visualization:** Python `generate_charts.py` & R `analysis.R` (제안서 서식 4 삽입용 300 DPI 통계 차트 2종 `static/charts/`)

---

## 🚀 3. 실행 방법 (Quick Start)

```bash
# 1. 통계 차트(300 DPI PNG 2종) 및 9:16 쇼츠 MP4 영상(3종) 생성
python3 generate_charts.py
python3 render_mp4.py

# 2. FastAPI 로컬 서버 실행 (http://localhost:8000)
python3 app.py
```

---

## 📁 4. 주요 디렉터리 구조

```text
agora-shorts/
├── app.py                          # FastAPI 백엔드 서버 (YouTube 수집, Gemini 분석, MP4 렌더링 API)
├── presets_data.py                 # 실측 유튜브 댓글(N=527) 기반 3대 프리셋 및 비속어 정량 필터링 엔진
├── render_mp4.py                   # 720x1280 (9:16) 40초 H.264 MP4 쇼츠 비디오 렌더러
├── generate_charts.py              # 제안서 서식 4 삽입용 300 DPI 고해상도 통계 차트 2종 생성기
├── analysis.R                      # R (ggplot2) 기반 동일 통계 시각화 스크립트
├── supabase_schema.sql             # Supabase PostgreSQL 테이블 및 RLS 정책 생성 SQL
├── data/
│   ├── real_youtube_comments.json  # YouTube Data API v3 실측 댓글 원본 527건
│   └── empirical_analysis.json     # N=527 실증 통계 요약 데이터
└── static/
    ├── index.html                  # Agora-Shorts 통합 인터랙티브 웹 스튜디오
    ├── charts/
    │   ├── chart1_sentiment_shift.png
    │   └── chart2_topic_clusters.png
    └── videos/
        ├── preset_1.mp4            # 프리셋 1: 심야 배달 오토바이 소음 규제 (40초 9:16 MP4)
        ├── preset_2.mp4            # 프리셋 2: 공유 전동킥보드 견인·금지 (40초 9:16 MP4)
        └── preset_3.mp4            # 프리셋 3: 고령 운전자 조건부 면허·반납 (40초 9:16 MP4)
```
