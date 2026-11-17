# 한냥 (Hannyang) — 다관점 여론·공론장 AI 쇼츠 스튜디오

> **제1회 동양AI빅데이터융합 아이디어 공모전 출품작 (AI융합콘텐츠분야)**  
> **팀명:** 호날두의 아이들 (동양대학교 AI빅데이터융합학과 1학년 김성원, 강휘, 손기윤)

유튜브 댓글창의 감정적 욕설과 혐오 표현을 정량적으로 필터링하고, 찬반 이분법을 넘어 **리뷰·게임패치·일상논쟁·다자쟁점 등 2~4개의 핵심 관점(Perspectives)**과 근거 인용문을 추출해 **한국어 뉴럴 아나운서 톤의 9:16 FHD(1080×1920) 쇼츠(MP4)**로 자동 전환하는 공론장·여론 큐레이션 파이프라인입니다.

---

## 📊 1. 실제 유튜브 댓글 빅데이터 수집 및 실증 분석 (`N = 527`)

단순 시뮬레이션이나 가상 데이터가 아닌 **YouTube Data API v3 (`commentThreads.list`)**를 통해 실제 방송 뉴스 영상 12개에서 수집한 **총 527건의 실측 댓글(`data/real_youtube_comments.json`)**을 분석했습니다.

| 프리셋 주제 | 수집 방송 뉴스 영상 (Video ID) | 수집 댓글 수 | 과열·비속어 필터링 | 실측 관점 분포 | 과열 표본 정화 전·후 과열도 | 쇼츠 구성 |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| **프리셋 1: 심야 배달 오토바이 소음 규제** | YTN(`vNIXiWyXs90`), MBC(`lt7knjTuuOM`), 연합뉴스TV(`Cs_A2EcMsto`) | **200건** | 58건 (29.0%) | 규제 강화 **88%** : 신중·보완 **12%** | 64.2점 → **14.5점** | 2관점 6턴 (자연 호흡) |
| **프리셋 2: 공유 전동킥보드 견인·금지** | MBC(`Xt8TRqMuZRc`), SBS(`aI0awk0NBfc`), TBS(`D2hNIe74HEQ`) | **180건** | 32건 (17.8%) | 견인·규제 **87%** : 인프라·공존 **13%** | 61.5점 → **14.2점** | 2관점 6턴 (자연 호흡) |
| **프리셋 3: 고령 운전자 조건부 면허·대안** | MBC(`NKIvNrtdiGA`), KBS(`x3J5hpBci98`), YTN(`yfAshZpECCo`) 외 3건 | **147건** | 36건 (24.5%) | 안전 검증 **47%** · 이동권 보장 **33%** · 기술 대안 **20%** | 62.4점 → **14.5점** | 3관점 6턴 (다관점 비교) |
| **합계 / 평균** | **총 12개 주요 언론사 뉴스 리포트** | **527건** | **126건 (23.9%)** | **다수 쏠림 속 소수·대안 시각 복원** | **62.8점 → 14.4점 (-48.4pt↓)** | **2~8턴 유연 편집 지원** |

* **핵심 데이터 발견 (Data Insight):** 실제 뉴스 댓글창은 규제·처벌을 요구하는 강경 여론이 평균 **84.3%**로 과대 대표되어 있으며, 생계형 노동자 생존권·농어촌 이동권·안전기술 대안 등 **소수 및 제3의 대안 시각은 욕설과 조롱 속에 묻히는 침묵의 나선(Spiral of Silence)** 현상이 확인되었습니다. **한냥(Hannyang)**은 찬반 구도뿐 아니라 2~4개 다관점 클러스터를 균형 있게 조명하여 입체적인 공론장을 복원합니다.

---

## 🛠️ 2. 시스템 아키텍처 및 기술 스택

* **Backend:** Python 3.11 + FastAPI (`app.py`, `presets_data.py`, `render_mp4.py`)
* **Data Collection:** YouTube Data API v3 실시간 댓글 수집 + oEmbed 폴백 + 직접 댓글 텍스트 입력 지원
* **AI & NLP Engine:**
  * **다관점 클러스터링 & 정제 (`cluster_comments_multiperspective`):** 분석 모드(`auto` / `multi` / `proscons` / `debate` / `summary`)에 따라 한국어 명사 토크나이징 및 호평·지적·대안 2~4관점 추출
  * **Google Gemini 2.5 Flash (`gemini-2.5-flash`):** 구조화 JSON 다관점 대본 생성
  * **Multi-Tier Korean TTS + 20ms RMS 자막 동기화:** Cloud Neural2(`ko-KR-Neural2-C/A`) / Edge Neural(`InJoonNeural/SunHiNeural`) / 브라우저 한국어 음성 폴백 + WAV RIFF·20ms RMS 무음 계곡 검출 기반 문구·어절 단위 정밀 하이라이트
* **9:16 FHD Video Engine:**
  * 서버 사이드: Pillow + `ffmpeg` (`libx264`, `yuv420p`, `1080x1920`, 30fps, AAC 24kHz) 기반 2~8턴 동적 9:16 `.mp4` 생성 (`static/videos/preset_1~3.mp4`)
  * 클라이언트 사이드: HTML5 `<canvas>` (1080×1920) + `MediaRecorder` + Web Audio API 실시간 방송형 영상 녹화 다운로드
* **Cloud Database:** Supabase PostgreSQL (`public.hannyang_debates` 테이블 + Row Level Security 정책, `supabase_schema.sql`)
* **Data Visualization:** Python `generate_charts.py` & R `analysis.R` (제안서 서식 4 삽입용 300 DPI 통계 차트 2종 `static/charts/`)

---

## 🚀 3. 실행 방법 (Quick Start)

```bash
# 1. 통계 차트(300 DPI PNG 2종) 및 9:16 FHD MP4 영상(3종) 생성
python3 generate_charts.py
python3 render_mp4.py

# 2. FastAPI 로컬 서버 실행
python3 app.py
```

---

## 📁 4. 주요 디렉터리 구조

```text
hannyang-shorts/
├── app.py                          # FastAPI 백엔드 서버 (YouTube 수집, 다관점 분석, MP4 렌더링 API)
├── presets_data.py                 # 실측 유튜브 댓글(N=527) 기반 3대 프리셋 데이터셋
├── render_mp4.py                   # 1080x1920 (9:16) 30fps H.264 MP4 다관점 쇼츠 비디오 렌더러
├── generate_charts.py              # 제안서 서식 4 삽입용 300 DPI 고해상도 통계 차트 2종 생성기
├── analysis.R                      # R (ggplot2) 기반 동일 통계 시각화 스크립트
├── supabase_schema.sql             # Supabase PostgreSQL 테이블 및 RLS 정책 생성 SQL
├── data/
│   ├── real_youtube_comments.json  # YouTube Data API v3 실측 댓글 원본 527건
│   └── empirical_analysis.json     # N=527 실증 통계 요약 데이터
├── index.html                      # GitHub Pages 정적 웹 스튜디오 (static/index.html과 동일)
└── static/
    ├── index.html                  # 한냥 통합 인터랙티브 웹 스튜디오
    ├── assets/                     # 스튜디오 배경·데스크·양측 아바타 에셋
    ├── charts/
    │   ├── chart1_sentiment_shift.png
    │   └── chart2_topic_clusters.png
    └── videos/
        ├── preset_1.mp4            # 프리셋 1: 심야 배달 오토바이 소음 규제 (1080p 9:16 MP4)
        ├── preset_2.mp4            # 프리셋 2: 공유 전동킥보드 견인·금지 (1080p 9:16 MP4)
        └── preset_3.mp4            # 프리셋 3: 고령 운전자 실기·이동권·기술 대안 3관점 (1080p 9:16 MP4)
```
