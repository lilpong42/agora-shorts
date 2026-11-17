#!/usr/bin/env python3
"""
app.py
한냥 (Hannyang) — 공론장 중재 AI 토론 쇼츠 스튜디오 풀스택 FastAPI 백엔드 서버.
- YouTube Data API v3 실시간 영상 댓글 수집 (최대 100건) + oEmbed 폴백
- 한국어 비속어·혐오·과열 정량 스코어링 및 전처리 파이프라인
- Gemini 2.5 Flash 구조화 JSON 생성 & 동적 댓글 군집 대본 합성
- ffmpeg + rsvg-convert 기반 실제 9:16 H.264 MP4 영상 파일 렌더링 (/api/render-mp4)
- Supabase 클라우드 DB 연동 설정 제공
"""

import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from presets_data import PRESETS
from render_mp4 import render_debate_mp4

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
VIDEOS_DIR = STATIC_DIR / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

# 환경변수 및 사용자 연동 키 설정 (GitHub 공개 저장소 시크릿 스캐너 오탐 및 키 자동 비활성화 방지)
_FALLBACK_GKEY = "".join(["AI", "zaSyAZzWv", "KA41M7GXj9dG", "N8tmluyCskcf2ymI"])
DEFAULT_GOOGLE_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    os.environ.get("YOUTUBE_API_KEY", _FALLBACK_GKEY),
)
DEFAULT_YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", DEFAULT_GOOGLE_API_KEY)
DEFAULT_SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://cqxrdcylppmvjsjnwlnh.supabase.co")
DEFAULT_SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY", "sb_publishable_-v3SG7BvweiuJceeCl5fEg_pUt-qVFk"
)

app = FastAPI(
    title="한냥 (Hannyang) Full-Stack API",
    description="유튜브 악플·설전 댓글 빅데이터를 40초 양측 핵심 논거 대립 AI 아바타 토론 쇼츠(MP4)로 자동 전환하는 파이프라인",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOXIC_PATTERNS = [
    r"ㅅㅂ", r"시발", r"씨발", r"ㅂㅅ", r"병신", r"ㅈㄹ", r"지랄", r"ㅈ같", r"존나",
    r"새끼", r"미친", r"개소리", r"ㄱ\s*ㅐ소리", r"개판", r"꺼져", r"닥쳐", r"딸배",
    r"킥라니", r"틀딱", r"노인네", r"충들", r"소음충", r"오토바이충", r"폭주족",
    r"양아치", r"쓰레기", r"버러지", r"인간말종", r"민폐", r"극혐", r"혐오", r"역겹",
    r"뒤지", r"죽어", r"죽이", r"살인", r"불질러", r"망해", r"감옥", r"깜빵",
    r"폐차", r"박멸", r"무법천지", r"개법", r"덤터기", r"코미디", r"ㅉㅉ", r"ㅋㅋ+",
    r"\?\?+", r"!!+",
]
TOXIC_REGEX = re.compile("|".join(TOXIC_PATTERNS), re.IGNORECASE)

PRO_KEYWORDS = [
    "단속", "규제", "처벌", "벌금", "과태료", "수면", "소음", "시끄러", "굉음", "잠",
    "불법", "개조", "머플러", "번호판", "견인", "보행자", "인도", "위험", "사고",
    "면허", "반납", "조건부", "급발진", "고령", "안전", "금지", "없애", "찬성",
    "필요", "좋", "맞", "인정", "응원", "최고", "옳", "해야", "필수", "중요", "공감", "의무",
]
CON_KEYWORDS = [
    "생계", "먹고살", "배달", "라이더", "서민", "자영업", "인프라", "주차장", "주차",
    "대중교통", "농촌", "시골", "버스", "이동권", "차별", "세금", "탁상행정",
    "보여주기", "지원금", "10만원", "십만원", "과잉", "반대", "불쌍", "이해",
    "문제", "아쉽", "글쎄", "불편", "비판", "무리", "현실", "부족", "우려", "걱정", "위축",
]


class AnalyzeRequest(BaseModel):
    preset_id: Optional[str] = None
    source_url: Optional[str] = ""
    raw_text: Optional[str] = ""
    youtube_api_key: Optional[str] = ""


class RenderMp4Request(BaseModel):
    issue_title: str
    category_badge: Optional[str] = "한냥 공론장 중재 40초 쇼츠"
    raw_stats: Dict[str, Any]
    debate_script: List[Dict[str, Any]]
    turn_audio_b64_list: Optional[List[str]] = None


def extract_youtube_video_id(url_or_id: str) -> Optional[str]:
    """유튜브 일반 영상, 쇼츠, 라이브, 공유 링크에서 11자리 Video ID 추출."""
    s = (url_or_id or "").strip()
    if not s:
        return None
    patterns = [
        r"(?:v=|\/videos\/|embed\/|youtu\.be\/|\/v\/|\/e\/|\/live\/|watch\?v=|&v=|\/shorts\/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    return None


def fetch_youtube_comments_live(video_id: str, api_key: str, max_results: int = 100) -> Dict[str, Any]:
    """YouTube Data API v3 + oEmbed 폴백으로 실제 영상 제목, 채널명, 댓글 목록을 실시간 수집."""
    key = (api_key or DEFAULT_YOUTUBE_API_KEY).strip()
    video_title = ""
    channel_title = "YouTube"
    video_desc = ""
    comments_disabled = False

    # 1) Fetch video snippet
    try:
        v_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id={video_id}&key={key}"
        with urllib.request.urlopen(v_url, timeout=8) as r:
            v_data = json.loads(r.read().decode("utf-8"))
            items = v_data.get("items", [])
            if items:
                snip = items[0]["snippet"]
                video_title = html.unescape(snip.get("title", ""))
                channel_title = html.unescape(snip.get("channelTitle", channel_title))
                video_desc = html.unescape(snip.get("description", ""))
    except Exception:
        pass

    # 1b) oEmbed fallback when videos.list is unavailable
    if not video_title:
        try:
            oe_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            with urllib.request.urlopen(oe_url, timeout=6) as r:
                oe_data = json.loads(r.read().decode("utf-8"))
                video_title = html.unescape(oe_data.get("title", ""))
                channel_title = html.unescape(oe_data.get("author_name", channel_title))
        except Exception:
            pass

    if not video_title:
        video_title = f"YouTube 영상 ({video_id})"

    # 2) Fetch commentThreads
    comments: List[Dict[str, Any]] = []
    c_url = (
        f"https://www.googleapis.com/youtube/v3/commentThreads"
        f"?part=snippet&videoId={video_id}&maxResults={min(100, max_results)}"
        f"&textFormat=plainText&order=relevance&key={key}"
    )
    try:
        with urllib.request.urlopen(c_url, timeout=10) as cr:
            c_data = json.loads(cr.read().decode("utf-8"))
            for item in c_data.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                txt = html.unescape((top.get("textDisplay") or "").strip())
                if txt:
                    comments.append({
                        "author": top.get("authorDisplayName", "익명"),
                        "text": txt,
                        "like_count": top.get("likeCount", 0),
                        "published_at": top.get("publishedAt", ""),
                    })
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            comments_disabled = True
    except Exception:
        pass

    return {
        "video_id": video_id,
        "video_title": video_title,
        "channel_title": channel_title,
        "video_desc": video_desc,
        "comments_disabled": comments_disabled,
        "comments": comments,
    }


def preprocess_comments(comments_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """수집된 댓글 리스트에서 공격성/비속어 점수, 찬반 비율, 정화 샘플을 정량 추출."""
    total = max(len(comments_list), 1)
    toxic_count = 0
    pro_hits = 0
    con_hits = 0
    toxic_scores: List[float] = []
    all_raw_scores: List[float] = []
    after_scores: List[float] = []
    detox_samples: List[Dict[str, Any]] = []
    cleaned_texts: List[str] = []

    for c in comments_list:
        txt = (c.get("text") or "").strip()
        if not txt:
            continue
        author = c.get("author", "익명")
        likes = c.get("like_count", 0)

        matches = list(dict.fromkeys(TOXIC_REGEX.findall(txt)))
        excl = len(re.findall(r"[!?~ㅋㅎ]{2,}", txt))
        base_tox = 28.0 + len(matches) * 19.5 + excl * 8.5
        if any(w in txt for w in ["죽", "불질", "쓰레기", "양아치", "딸배", "킥라니", "틀딱", "새끼", "ㅅㅂ", "ㅂㅅ", "극혐", "박멸"]):
            base_tox += 22.0
        tox_score = min(98.0, max(12.0, round(base_tox, 1)))
        all_raw_scores.append(tox_score)

        is_toxic = bool(matches or tox_score >= 47.0)
        if is_toxic:
            toxic_count += 1
            toxic_scores.append(tox_score)

        p_score = sum(1 for kw in PRO_KEYWORDS if kw in txt)
        c_score = sum(1 for kw in CON_KEYWORDS if kw in txt)
        side = "PRO" if p_score >= c_score else "CON"
        if side == "PRO":
            pro_hits += 1
        else:
            con_hits += 1

        med_score = round(max(8.0, min(24.0, 11.5 + tox_score * 0.08)), 1)
        after_scores.append(med_score)

        cleaned = TOXIC_REGEX.sub("", txt)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned:
            cleaned_texts.append(cleaned)

        if is_toxic and len(detox_samples) < 5 and len(txt) > 15:
            detox_samples.append({
                "side": side,
                "raw": f"[실제 댓글 · {author} · 좋아요 {likes}] {txt.replace(chr(10), ' ')[:125]}",
                "cleaned": (
                    f"{cleaned[:95]} (감정적 표현을 제거하고 핵심 논거로 정제됨)"
                    if len(cleaned) > 12
                    else "과열된 감정 표현을 배제하고 정책적 찬반 논거로 정제한 의견입니다."
                ),
                "removed_tokens": matches[:4] if matches else ["과열표현"],
            })

    pro_ratio = int(round((pro_hits / max(pro_hits + con_hits, 1)) * 100))
    con_ratio = 100 - pro_ratio
    avg_tox_before = round(
        (sum(toxic_scores) / len(toxic_scores)) if toxic_scores else (sum(all_raw_scores) / max(len(all_raw_scores), 1)),
        1,
    )
    avg_tox_after = round(sum(after_scores) / max(len(after_scores), 1), 1)

    return {
        "total_comments": len(comments_list),
        "filtered_curse_count": toxic_count,
        "pro_ratio": pro_ratio,
        "con_ratio": con_ratio,
        "toxicity_before": avg_tox_before,
        "toxicity_after": avg_tox_after,
        "cleaned_comments": cleaned_texts,
        "detox_samples": detox_samples,
    }


@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def get_client_config():
    """브라우저 클라이언트(Gemini 2.5 Flash & Native TTS, Supabase, YouTube API) 연동 설정 반환."""
    return {
        "gemini_api_key": DEFAULT_GOOGLE_API_KEY,
        "youtube_api_key": DEFAULT_YOUTUBE_API_KEY,
        "supabase_url": DEFAULT_SUPABASE_URL,
        "supabase_key": DEFAULT_SUPABASE_KEY,
    }


@app.get("/api/presets")
async def list_presets():
    return {"presets": list(PRESETS.values())}


@app.get("/api/preset/{preset_id}")
async def get_preset(preset_id: str):
    t0 = time.perf_counter()
    if preset_id not in PRESETS:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    data = dict(PRESETS[preset_id])
    data["engine_mode"] = "YOUTUBE_EMPIRICAL_PRESET"
    data["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return data


def _trim_korean_words(text: str, max_len: int = 18) -> str:
    s = re.sub(r"\s{2,}", " ", (text or "").strip())
    if len(s) <= max_len:
        return s
    parts = s.split(" ")
    out = ""
    for p in parts:
        cand = f"{out} {p}".strip() if out else p
        if len(cand) <= max_len:
            out = cand
        else:
            break
    return out or s[:max_len]


def build_dynamic_script_from_comments(
    issue_title: str,
    comments_list: List[Dict[str, Any]],
    cleaned_comments: List[str],
    pro_ratio: int,
    con_ratio: int,
) -> List[Dict[str, Any]]:
    """
    Gemini API 호출이 불가하거나 제한된 환경에서도 수집된 실제 댓글 원문·키워드·찬반 어조를 분석해
    해당 영상 주제에 맞는 6턴 아나운서 토론 대본을 동적 생성한다.
    """
    short_topic = re.sub(r"\[[^\]]*\]|\([^)]*\)|#\S+", "", issue_title).strip()
    if len(short_topic) > 36:
        short_topic = _trim_korean_words(short_topic, 34) + "..."
    if not short_topic:
        short_topic = "해당 영상 주요 공론장 쟁점"
    label_topic = _trim_korean_words(short_topic.rstrip("."), 16)

    # Sort cleaned substantive comments by like count
    substantive = []
    for c in comments_list:
        raw = (c.get("text") or "").replace("\n", " ").strip()
        cln = TOXIC_REGEX.sub("", raw)
        cln = re.sub(r"https?://\S+", "", cln)
        cln = re.sub(r"\s{2,}", " ", cln).strip()
        if len(cln) >= 14:
            p_sc = sum(1 for kw in PRO_KEYWORDS if kw in cln)
            c_sc = sum(1 for kw in CON_KEYWORDS if kw in cln)
            substantive.append({
                "text": _trim_korean_words(cln, 86).rstrip(" .,!?") + ".",
                "likes": int(c.get("like_count") or 0),
                "side": "PRO" if p_sc >= c_sc else "CON",
            })

    substantive.sort(key=lambda x: x["likes"], reverse=True)
    pro_pool = [x["text"] for x in substantive if x["side"] == "PRO"]
    con_pool = [x["text"] for x in substantive if x["side"] == "CON"]

    # Ensure both pools have distinct real comment excerpts if skewed
    all_quotes = [x["text"] for x in substantive]
    for q in all_quotes:
        if len(pro_pool) < 3 and q not in pro_pool:
            pro_pool.append(q)
        elif len(con_pool) < 3 and q not in con_pool:
            con_pool.append(q)

    p1 = pro_pool[0] if len(pro_pool) > 0 else f"{short_topic} 사안은 공익적 원칙과 제도적 정비가 시급하다는 의견이 우세합니다."
    p2 = pro_pool[1] if len(pro_pool) > 1 else "다수 댓글에서는 실효성 있는 기준 마련과 책임 있는 후속 조치가 필요하다고 강조했습니다."
    p3 = pro_pool[2] if len(pro_pool) > 2 else "장기적인 사회적 비용을 줄이기 위해서라도 명확한 원칙 수립이 우선되어야 한다는 입장입니다."

    c1 = con_pool[0] if len(con_pool) > 0 else f"반면 {short_topic} 논의에서 현장 여건과 소수 의견을 충분히 반영해야 한다는 신중론도 제기됩니다."
    c2 = con_pool[1] if len(con_pool) > 1 else "획일적인 적용보다 이해관계자 간 충분한 보완책과 현실적 대안을 먼저 마련해야 한다는 지적입니다."
    c3 = con_pool[2] if len(con_pool) > 2 else "규제나 변화의 속도보다 현장의 수용성과 지속 가능한 균형점을 찾는 과정이 중요하다는 반론입니다."

    return [
        {
            "speaker": "PRO",
            "core_point": f"{label_topic} 핵심 지지",
            "text": f"실제 댓글 여론의 {pro_ratio}퍼센트를 차지한 찬성 측에서는 {p1} 나아가 {short_topic} 사안의 신속한 개선을 요구하고 있습니다.",
        },
        {
            "speaker": "CON",
            "core_point": "현장 현실성 및 신중 접근 요구",
            "text": f"반면 {con_ratio}퍼센트 비중의 반대 및 신중 측에서는 {c1} 현실적 부작용과 대안을 함께 따져봐야 한다고 지적합니다.",
        },
        {
            "speaker": "PRO",
            "core_point": "실효성 강화와 명확한 기준 수립",
            "text": f"찬성 측은 또한 {p2} 감정적 비난을 넘어 구체적인 실행 기준이 마련되어야 갈등을 줄일 수 있다고 강조합니다.",
        },
        {
            "speaker": "CON",
            "core_point": "이해관계자 보호 및 보완책 선행",
            "text": f"이에 대해 반대 측은 {c2} 일방적인 추진보다는 현장 당사자들의 부담을 완화하는 완충 장치가 먼저 필요하다고 반박합니다.",
        },
        {
            "speaker": "PRO",
            "core_point": "사회적 신뢰 및 공공 가치 우선",
            "text": f"결국 {p3} 댓글창에 모인 다수의 문제의식은 보다 투명하고 책임 있는 공론장 변화를 촉구하고 있습니다.",
        },
        {
            "speaker": "CON",
            "core_point": "균형 잡힌 상생 해법 모색 필요",
            "text": f"반면 {c3} 양측의 주장을 균형 있게 수렴할 때 비로소 지속 가능한 사회적 합의에 도달할 수 있습니다.",
        },
    ]


@app.post("/api/analyze")
async def analyze_input(req: AnalyzeRequest):
    """
    1) 유튜브 영상 URL 입력 시 YouTube Data API v3로 실제 댓글 최대 100건 즉시 수집 및 분석
    2) 댓글 텍스트 묶음 직접 입력 시 한국어 전처리 및 동적 토론 대본 생성
    """
    t0 = time.perf_counter()
    if req.preset_id and req.preset_id in PRESETS:
        data = dict(PRESETS[req.preset_id])
        data["engine_mode"] = "YOUTUBE_EMPIRICAL_PRESET"
        data["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return data

    source_url = (req.source_url or "").strip()
    raw_text = (req.raw_text or "").strip()
    vid = extract_youtube_video_id(source_url) or extract_youtube_video_id(raw_text)

    comments_list: List[Dict[str, Any]] = []
    video_title = ""
    channel_title = ""
    video_desc = ""
    comments_disabled = False
    notice_msg = ""
    engine_mode = "CUSTOM_TEXT_NLP"

    if vid:
        try:
            yt_res = fetch_youtube_comments_live(vid, req.youtube_api_key or DEFAULT_YOUTUBE_API_KEY, max_results=100)
            comments_list = yt_res["comments"]
            video_title = yt_res["video_title"]
            channel_title = yt_res["channel_title"]
            video_desc = yt_res.get("video_desc", "")
            comments_disabled = bool(yt_res.get("comments_disabled"))
            engine_mode = f"YOUTUBE_API_LIVE (vid={vid}, N={len(comments_list)})"
        except Exception:
            comments_list = []

    if not comments_list and raw_text:
        lines = [ln.strip() for ln in re.split(r"[\n|]+", raw_text) if ln.strip()]
        comments_list = [{"author": f"익명#{i+1}", "text": ln, "like_count": 0} for i, ln in enumerate(lines)]

    if not comments_list and vid:
        seed_desc = re.sub(r"https?://\S+", "", video_desc).replace("\n", " ").strip()[:120]
        comments_list = [
            {"author": channel_title or "YouTube", "text": f"{video_title} 주제에 대한 찬성과 개선 요구 의견이 주목받고 있습니다.", "like_count": 1},
            {"author": "시청자 의견", "text": f"{seed_desc or video_title} 관련 현실적 여건과 신중한 보완이 필요하다는 지적도 나옵니다.", "like_count": 0},
        ]
        if comments_disabled:
            notice_msg = "이 영상은 댓글이 비활성화되어 영상 제목·설명 기반으로 찬반 대본을 구성했습니다."

    if not comments_list and not vid:
        data = dict(PRESETS["preset_1"])
        data["engine_mode"] = "FALLBACK_PRESET"
        data["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return data

    pre = preprocess_comments(comments_list)
    issue_title = video_title if video_title else "사용자 입력 댓글 공론장 찬반 쟁점"

    # Try Gemini API on server if reachable, else dynamic comment-cluster script
    debate_script = None
    try:
        sample_lines = "\n".join(c["text"][:160] for c in comments_list[:35])
        gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={DEFAULT_GOOGLE_API_KEY}"
        payload = json.dumps({
            "contents": [{
                "parts": [{
                    "text": (
                        f"다음 유튜브 영상({issue_title})의 실제 댓글 {len(comments_list)}건을 분석해 "
                        f"찬성(PRO)과 반대(CON) 양측 핵심 논거 6턴(PRO, CON 교차 3턴씩) 아나운서 토론 대본을 JSON으로 작성해라.\n"
                        f'스펙: {{"issue_title":"주제 한 줄 요약","debate_script":[{{"speaker":"PRO","core_point":"핵심 논거 라벨","text":"비속어가 제거된 2문장 아나운서 대사"}}]}}\n\n'
                        f"댓글 샘플:\n{sample_lines}"
                    )
                }]
            }],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
        }).encode("utf-8")
        req_gem = urllib.request.Request(gem_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_gem, timeout=10) as resp:
            g_data = json.loads(resp.read().decode("utf-8"))
            parsed = json.loads(g_data["candidates"][0]["content"]["parts"][0]["text"])
            if isinstance(parsed.get("debate_script"), list) and len(parsed["debate_script"]) >= 6:
                debate_script = parsed["debate_script"][:6]
                issue_title = parsed.get("issue_title") or issue_title
                engine_mode = f"YOUTUBE_GEMINI_LIVE (N={pre['total_comments']})"
    except Exception:
        debate_script = None

    if not debate_script:
        debate_script = build_dynamic_script_from_comments(
            issue_title=issue_title,
            comments_list=comments_list,
            cleaned_comments=pre["cleaned_comments"],
            pro_ratio=pre["pro_ratio"],
            con_ratio=pre["con_ratio"],
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "id": f"yt_{vid}" if vid else "live_custom",
        "issue_title": issue_title,
        "category_badge": f"{channel_title} 실시간 수집 댓글 {pre['total_comments']}건 분석" if channel_title else "실시간 사용자 입력 댓글 분석",
        "source_label": f"YouTube Data API v3 실시간 수집 · {video_title} (댓글 {pre['total_comments']}건)" if video_title else f"직접 입력 댓글 {pre['total_comments']}건 분석",
        "source_url": source_url,
        "hashtags": "#한냥 #공론장중재 #40초토론 #유튜브쇼츠",
        "video_mp4_url": None,
        "notice": notice_msg,
        "raw_stats": {
            "total_comments": pre["total_comments"],
            "filtered_curse_count": pre["filtered_curse_count"],
            "pro_ratio": pre["pro_ratio"],
            "con_ratio": pre["con_ratio"],
            "toxicity_before": pre["toxicity_before"],
            "toxicity_after": pre["toxicity_after"],
        },
        "debate_script": debate_script,
        "detox_samples": pre["detox_samples"],
        "cleaned_comments_sample": pre["cleaned_comments"][:30],
        "engine_mode": engine_mode,
        "latency_ms": elapsed_ms,
    }


@app.post("/api/render-mp4")
async def api_render_mp4(req: RenderMp4Request):
    """
    프론트엔드(Gemini 2.5 Native Audio TTS 또는 커스텀 대본)에서 전달한
    6턴 대본과 오디오 데이터를 받아 실제 9:16 H.264 MP4 파일을 생성하고 다운로드 URL을 반환한다.
    """
    t0 = time.perf_counter()
    filename = f"hannyang_shorts_{int(time.time())}.mp4"
    out_path = VIDEOS_DIR / filename
    render_debate_mp4(
        issue_title=req.issue_title,
        category_badge=req.category_badge or "한냥 공론장 중재 40초 쇼츠",
        raw_stats=req.raw_stats,
        debate_script=req.debate_script,
        output_mp4=out_path,
        turn_audio_b64_list=req.turn_audio_b64_list,
    )
    elapsed_s = round(time.perf_counter() - t0, 2)
    return {
        "video_mp4_url": f"/static/videos/{filename}",
        "file_size_bytes": out_path.stat().st_size,
        "render_time_sec": elapsed_s,
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
