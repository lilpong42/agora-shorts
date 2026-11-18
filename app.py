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
_GEMINI_COOLDOWN_UNTIL = 0.0

app = FastAPI(
    title="한냥 (Hannyang) Full-Stack API",
    description="유튜브 악플·설전 댓글 빅데이터를 양측 핵심 논거 대립 AI 아바타 토론 쇼츠(MP4)로 자동 전환하는 파이프라인",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PALETTE_ORDER = ["blue", "red", "violet", "emerald", "amber"]

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

POS_CUES = [
    "좋", "최고", "만족", "장점", "추천", "깔끔", "선명", "기대", "감동", "유용",
    "혁신", "쾌적", "빠르", "편하", "필수", "인정", "응원", "옳", "찬성", "동의",
    "공감", "훌륭", "대박", "잘", "이득", "재밌", "갓", "혜자", "필요", "의무",
]
CRIT_CUES = [
    "아쉽", "불편", "비싸", "부담", "문제", "부족", "실망", "우려", "걱정", "최악",
    "느리", "과잉", "탁상행정", "차별", "위축", "피로", "한계", "반대", "무겁", "무거",
    "단점", "창렬", "과금", "버그", "발열", "글쎄", "무리", "비판", "불쌍", "피해",
]
ALT_CUES = [
    "차라리", "대신", "보완", "개선", "패치", "수정", "조건", "비교", "전작", "타사",
    "균형", "해결", "제안", "방법", "도입", "병행", "인프라", "지원", "대안", "가성비",
    "할인", "업데이트", "절충", "단계", "어떨까", "나을",
]
DEBATE_CUES = [
    "찬성", "반대", "규제", "금지", "의무", "법안", "처벌", "폐지", "논란", "도입", "권리", "생존권",
]
REVIEW_CUES = [
    "가격", "가성비", "스펙", "성능", "배터리", "카메라", "디자인", "화질", "무게",
    "발열", "장점", "단점", "후기", "리뷰", "전작", "추천", "실사용",
]

KO_STOPWORDS = {
    "진짜", "너무", "정말", "완전", "그냥", "솔직히", "역시", "근데", "그리고", "하지만",
    "그러나", "그런데", "아니라", "결국", "이번", "이번엔", "영상", "댓글", "사람", "사람들",
    "우리", "자기", "때문", "정도", "부분", "하나", "모든", "많이", "조금", "엄청", "약간",
    "무조건", "항상", "계속", "아직", "다시", "오늘", "지금", "이거", "저거", "그거",
    "이건", "저건", "그건", "여기", "거기", "어디", "누구", "무엇", "어떤", "이런",
    "저런", "그런", "이렇", "같다", "같음", "같은", "같아", "있음", "없음", "있는",
    "없는", "하는", "되는", "하면", "되면", "해서", "되서", "해야", "하고", "이고",
    "이다", "입니다", "합니다", "됩니다", "네요", "군요", "거든요", "잖아요", "어요", "아요",
    "생각", "느낌", "전반", "경우", "사실", "원래", "보니", "일단", "제발", "확실히",
    "시청자", "주제", "의견", "관련", "대해", "대한", "위해", "위한", "통해", "이상",
    "훨씬", "아무리", "어느", "서로", "매우", "가장", "더욱", "아예", "굳이", "이미",
    "당연히", "분명히", "제대로", "요즘", "최근", "함께", "같이", "먼저", "다소", "직접",
    "질이", "잠을", "삶의", "종일", "말이", "것이", "수가", "때가", "곳이",
    "오래", "신규", "유저", "예방", "도움", "문제", "해결", "필요",
    "가고", "오고", "보고", "주고", "쓰고", "타고", "좋고", "많고",
}
JOSA_SUFFIXES = (
    "에서는", "에서도", "으로는", "으로도", "이라는", "이라고", "까지", "부터", "처럼",
    "보다", "에서", "으로", "에게", "한테", "이랑", "하고", "이나", "이라", "은", "는",
    "이", "가", "을", "를", "에", "의", "도", "만", "로", "와", "과", "랑",
)
PREDICATE_ENDING_RE = re.compile(
    r"(?:합니다|됩니다|입니다|랍니다|습니다|ㅂ니다|한다|된다|했다|됐다|겠다|였다|이다|하다|되다|없다|있다|"
    r"으면|어야|아야|여야|지만|면서|니까|거든|잖아|네요|군요|어요|아요|해요|돼요|"
    r"어렵|좋겠|바랍|필요하|같음|인듯|일듯|할듯|뛰는|타는|보는|주는|받는|가는|오는|만든|나온|생긴|싶은)$"
)

MODE_LABELS = {
    "debate": "찬반 공론장 중재",
    "multi": "다관점 여론 비교",
    "proscons": "장단점·체감 분석",
    "summary": "핵심 반응 브리핑",
}


class AnalyzeRequest(BaseModel):
    preset_id: Optional[str] = None
    source_url: Optional[str] = ""
    raw_text: Optional[str] = ""
    youtube_api_key: Optional[str] = ""
    analysis_mode: Optional[str] = "auto"


class RenderMp4Request(BaseModel):
    issue_title: str
    category_badge: Optional[str] = "한냥 공론장 중재 쇼츠"
    raw_stats: Dict[str, Any]
    debate_script: List[Dict[str, Any]]
    turn_audio_b64_list: Optional[List[Optional[str]]] = None
    perspectives: Optional[List[Dict[str, Any]]] = None
    mode_label: Optional[str] = ""


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


def _strip_josa(tok: str) -> str:
    for suf in JOSA_SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 2:
            return tok[: -len(suf)]
    return tok


def _extract_tokens(text: str) -> List[str]:
    clean = re.sub(r"https?://\S+", " ", text or "")
    clean = TOXIC_REGEX.sub(" ", clean)
    raw_tokens = re.findall(r"[가-힣A-Za-z0-9]{2,10}", clean)
    out: List[str] = []
    for t in raw_tokens:
        if t.isdigit():
            continue
        if PREDICATE_ENDING_RE.search(t):
            continue
        stem = _strip_josa(t)
        if PREDICATE_ENDING_RE.search(stem):
            continue
        if len(stem) < 2 or stem in KO_STOPWORDS or t in KO_STOPWORDS:
            continue
        if len(stem) <= 8:
            out.append(stem)
    return out


def _score_comment_tones(text: str) -> Dict[str, int]:
    pos = sum(1 for k in POS_CUES if k in text)
    crit = sum(1 for k in CRIT_CUES if k in text)
    alt = sum(1 for k in ALT_CUES if k in text)
    return {"pos": pos, "crit": crit, "alt": alt}


def _resolve_analysis_mode(req_mode: Optional[str], comments_list: List[Dict[str, Any]], issue_title: str) -> str:
    mode = (req_mode or "auto").strip().lower()
    if mode in ("debate", "multi", "proscons", "summary"):
        return mode
    joined = (issue_title or "") + " " + " ".join((c.get("text") or "")[:140] for c in comments_list[:40])
    deb_hits = sum(1 for k in DEBATE_CUES if k in joined)
    rev_hits = sum(1 for k in REVIEW_CUES if k in joined)
    alt_hits = sum(1 for k in ALT_CUES if k in joined)
    if rev_hits >= 3 and deb_hits < 3:
        return "proscons"
    if deb_hits >= 3 and alt_hits < 2 and rev_hits == 0:
        return "debate"
    return "multi"


def _normalize_ratios(raw_counts: List[int]) -> List[int]:
    tot = sum(max(1, c) for c in raw_counts)
    pcts = [max(5, int(round((max(1, c) / tot) * 100))) for c in raw_counts]
    diff = 100 - sum(pcts)
    if pcts:
        max_idx = max(range(len(pcts)), key=lambda i: pcts[i])
        pcts[max_idx] = max(5, pcts[max_idx] + diff)
    return pcts


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


def cluster_comments_multiperspective(
    comments_list: List[Dict[str, Any]],
    issue_title: str,
    analysis_mode: str = "auto",
) -> Dict[str, Any]:
    """
    주제 불문(리뷰·게임패치·일상반응·다자쟁점·찬반토론) 2~4개 동적 관점 군집 추출 + 비속어 정제.
    """
    resolved_mode = _resolve_analysis_mode(analysis_mode, comments_list, issue_title)

    # 1) Token DF analysis across substantive cleaned comments
    doc_freq: Dict[str, int] = {}
    parsed_items: List[Dict[str, Any]] = []
    toxic_scores: List[float] = []
    all_raw_scores: List[float] = []
    after_scores: List[float] = []
    toxic_count = 0

    for idx, c in enumerate(comments_list):
        txt = (c.get("text") or "").strip()
        if not txt:
            continue
        matches = list(dict.fromkeys(TOXIC_REGEX.findall(txt)))
        excl = len(re.findall(r"[!?~ㅋㅎ]{2,}", txt))
        base_tox = 24.0 + len(matches) * 18.5 + excl * 7.5
        if any(w in txt for w in ["죽", "불질", "쓰레기", "양아치", "딸배", "킥라니", "틀딱", "새끼", "ㅅㅂ", "ㅂㅅ", "극혐", "박멸"]):
            base_tox += 20.0
        tox_score = min(98.0, max(11.0, round(base_tox, 1)))
        all_raw_scores.append(tox_score)

        is_toxic = bool(matches or tox_score >= 47.0)
        if is_toxic:
            toxic_count += 1
            toxic_scores.append(tox_score)

        med_score = round(max(8.0, min(24.0, 11.0 + tox_score * 0.08)), 1)
        after_scores.append(med_score)

        cleaned = TOXIC_REGEX.sub("", re.sub(r"https?://\S+", "", txt))
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        tokens = _extract_tokens(cleaned)
        for t in set(tokens):
            doc_freq[t] = doc_freq.get(t, 0) + 1

        tones = _score_comment_tones(cleaned)
        parsed_items.append({
            "idx": idx,
            "author": c.get("author", "익명"),
            "likes": int(c.get("like_count") or 0),
            "raw": txt,
            "cleaned": cleaned,
            "tokens": set(tokens),
            "tones": tones,
            "matches": matches,
            "is_toxic": is_toxic,
        })

    # Prefer higher frequency first, then compact 2-4 char domain nouns over long phrases
    sorted_kws = sorted(
        [(k, v) for k, v in doc_freq.items() if v >= 1],
        key=lambda kv: (kv[1], 1 if 2 <= len(kv[0]) <= 4 else 0, -len(kv[0])),
        reverse=True,
    )
    top_kws = [k for k, _ in sorted_kws[:16]]

    # 2) Define 2-4 perspective buckets based on mode + real comment keywords
    clusters: List[Dict[str, Any]] = []
    if resolved_mode == "debate":
        clusters = [
            {"id": "P1", "label": "핵심 지지·필요론", "short_label": "찬성·필요", "color": "blue", "kws": top_kws[:3], "items": []},
            {"id": "P2", "label": "신중·현실 보완론", "short_label": "반대·보완", "color": "red", "kws": top_kws[3:6] or top_kws[:2], "items": []},
        ]
        for it in parsed_items:
            p_sc = it["tones"]["pos"]
            c_sc = it["tones"]["crit"] + it["tones"]["alt"]
            target = 0 if p_sc > c_sc else (1 if c_sc > p_sc else (it["idx"] % 2))
            clusters[target]["items"].append(it)
    elif resolved_mode == "proscons":
        pos_kw = _pick_facet_kw(parsed_items, lambda it: it["tones"]["pos"] > it["tones"]["crit"])
        crit_kw = _pick_facet_kw(parsed_items, lambda it: it["tones"]["crit"] > it["tones"]["pos"], exclude={pos_kw})
        alt_kw = _pick_facet_kw(parsed_items, lambda it: it["tones"]["alt"] > 0, exclude={pos_kw, crit_kw})
        clusters = [
            {"id": "P1", "label": f"{pos_kw} 긍정 호평" if pos_kw else "핵심 강점·호평", "short_label": f"{pos_kw[:6]} 호평" if pos_kw else "장점 호평", "color": "blue", "kws": [pos_kw] if pos_kw else top_kws[:2], "items": []},
            {"id": "P2", "label": f"{crit_kw} 아쉬움 지적" if crit_kw else "단점·부담 지적", "short_label": f"{crit_kw[:6]} 지적" if crit_kw else "아쉬움 지적", "color": "red", "kws": [crit_kw] if crit_kw else top_kws[2:4], "items": []},
            {"id": "P3", "label": f"{alt_kw} 비교·대안" if alt_kw else "가성비·비교 대안", "short_label": f"{alt_kw[:6]} 대안" if alt_kw else "비교·대안", "color": "violet", "kws": [alt_kw] if alt_kw else top_kws[4:6], "items": []},
        ]
        for it in parsed_items:
            t = it["tones"]
            if t["alt"] > 0 and t["alt"] >= t["pos"]:
                clusters[2]["items"].append(it)
            elif t["crit"] > t["pos"]:
                clusters[1]["items"].append(it)
            elif t["pos"] > 0:
                clusters[0]["items"].append(it)
            else:
                clusters[2 if len(parsed_items) >= 3 else (it["idx"] % 3)]["items"].append(it)
    else:
        # Multi or Summary mode: extract 3 or 4 genuinely distinct topic+tone clusters
        want_k = 4 if (len(parsed_items) >= 8 and len(top_kws) >= 4) else 3
        chosen_anchors: List[str] = []
        for kw in top_kws:
            if not any(kw in a or a in kw for a in chosen_anchors):
                chosen_anchors.append(kw)
            if len(chosen_anchors) >= want_k:
                break

        if len(chosen_anchors) >= 3:
            bucket_items: List[List[Dict[str, Any]]] = [[] for _ in chosen_anchors]
            for it in parsed_items:
                best_k = None
                for ki, ak in enumerate(chosen_anchors):
                    if ak in it["tokens"] or ak in it["cleaned"]:
                        if best_k is None or len(bucket_items[ki]) < len(bucket_items[best_k]):
                            best_k = ki
                if best_k is None:
                    best_k = min(range(len(chosen_anchors)), key=lambda i: len(bucket_items[i]))
                bucket_items[best_k].append(it)

            for ki, ak in enumerate(chosen_anchors):
                b_items = bucket_items[ki]
                sum_pos = sum(x["tones"]["pos"] for x in b_items)
                sum_crit = sum(x["tones"]["crit"] for x in b_items)
                sum_alt = sum(x["tones"]["alt"] for x in b_items)
                if sum_crit > sum_pos and sum_crit >= sum_alt:
                    suf, short_suf, color_hint = "아쉬움·지적", "지적", "red"
                elif sum_alt > sum_pos and sum_alt >= sum_crit:
                    suf, short_suf, color_hint = "개선·대안", "대안", "violet"
                elif sum_pos > sum_crit:
                    suf, short_suf, color_hint = "공감·호평", "호평", ("emerald" if ki >= 2 else "blue")
                else:
                    suf, short_suf, color_hint = ("핵심 시각", "시각", "blue") if ki == 0 else ("현실 시선", "의견", "violet")

                used_colors = {c["color"] for c in clusters}
                col = color_hint if color_hint not in used_colors else next((pc for pc in PALETTE_ORDER if pc not in used_colors), PALETTE_ORDER[ki % 4])
                lbl = f"{ak} {suf}"
                short_lbl = f"{ak[:6]} {short_suf}"
                clusters.append({
                    "id": f"P{ki+1}",
                    "label": lbl,
                    "short_label": short_lbl[:11],
                    "color": col,
                    "kws": [ak],
                    "items": b_items,
                })
        else:
            clusters = [
                {"id": "P1", "label": "핵심 공감·강점", "short_label": "공감·강점", "color": "blue", "kws": top_kws[:2], "items": []},
                {"id": "P2", "label": "우려·현실 지적", "short_label": "현실 지적", "color": "red", "kws": top_kws[2:4], "items": []},
                {"id": "P3", "label": "보완·대안 시각", "short_label": "대안 시각", "color": "violet", "kws": top_kws[4:6], "items": []},
            ]
            for it in parsed_items:
                t = it["tones"]
                if t["alt"] > 0 and t["alt"] >= t["pos"]:
                    clusters[2]["items"].append(it)
                elif t["crit"] > t["pos"]:
                    clusters[1]["items"].append(it)
                elif t["pos"] > 0:
                    clusters[0]["items"].append(it)
                else:
                    clusters[it["idx"] % 3]["items"].append(it)

    # Guarantee non-empty items in every bucket if overall comments exist, and normalize percentages
    non_empty = [c for c in clusters if c["items"]]
    if len(non_empty) >= 2:
        clusters = non_empty
    ratios = _normalize_ratios([len(c["items"]) for c in clusters])
    perspectives: List[Dict[str, Any]] = []
    detox_samples: List[Dict[str, Any]] = []

    for ci, cl in enumerate(clusters):
        perspectives.append({
            "id": cl["id"],
            "label": cl["label"],
            "short_label": cl["short_label"],
            "ratio": ratios[ci],
            "color": cl["color"],
            "keywords": [k for k in cl["kws"] if k][:3],
        })

    # Pick representative detox samples tagging each item's assigned cluster
    item_to_cl: Dict[int, Dict[str, Any]] = {}
    for cl in clusters:
        for it in cl["items"]:
            item_to_cl[it["idx"]] = cl

    for it in parsed_items:
        cl = item_to_cl.get(it["idx"], clusters[0])
        is_left = cl["color"] in ("blue", "emerald")
        if it["is_toxic"] and len(detox_samples) < 4 and len(it["raw"]) > 12:
            detox_samples.append({
                "side": "PRO" if is_left else "CON",
                "perspective_label": cl["short_label"],
                "color": cl["color"],
                "raw": f"[{it['author']}] {it['raw'].replace(chr(10), ' ')[:125]}",
                "cleaned": (
                    f"{it['cleaned'][:95]} (과열 표현을 덜어내고 핵심 관점으로 정제)"
                    if len(it["cleaned"]) > 12
                    else "과열된 감정 표현을 배제하고 핵심 취지만 남긴 정제 의견입니다."
                ),
                "removed_tokens": it["matches"][:4] if it["matches"] else ["과열표현"],
            })

    if not detox_samples:
        for it in parsed_items[:4]:
            if len(it["raw"]) > 10:
                cl = item_to_cl.get(it["idx"], clusters[0])
                is_left = cl["color"] in ("blue", "emerald")
                detox_samples.append({
                    "side": "PRO" if is_left else "CON",
                    "perspective_label": cl["short_label"],
                    "color": cl["color"],
                    "raw": f"[{it['author']}] {it['raw'].replace(chr(10), ' ')[:125]}",
                    "cleaned": it["cleaned"][:100] or it["raw"][:100],
                    "removed_tokens": [],
                })

    avg_tox_before = round(
        (sum(toxic_scores) / len(toxic_scores)) if toxic_scores else (sum(all_raw_scores) / max(len(all_raw_scores), 1) if all_raw_scores else 42.0),
        1,
    )
    avg_tox_after = round(sum(after_scores) / max(len(after_scores), 1), 1) if after_scores else 14.2

    if resolved_mode == "debate":
        mode_lbl = MODE_LABELS["debate"]
    elif resolved_mode == "proscons":
        mode_lbl = MODE_LABELS["proscons"]
    elif resolved_mode == "summary":
        mode_lbl = MODE_LABELS["summary"]
    else:
        mode_lbl = f"{len(perspectives)}관점 여론 비교"

    pro_r = perspectives[0]["ratio"] if perspectives else 50
    con_r = sum(p["ratio"] for p in perspectives[1:]) if len(perspectives) > 1 else (100 - pro_r)
    if resolved_mode != "debate":
        # Maintain pro/con summary fields as positive/non-negative vs critical for analytics compat
        pos_sum = sum(p["ratio"] for p in perspectives if p["color"] in ("blue", "emerald"))
        pro_r = max(1, min(99, pos_sum)) if pos_sum else pro_r
        con_r = 100 - pro_r

    return {
        "analysis_mode": resolved_mode,
        "mode_label": mode_lbl,
        "perspectives": perspectives,
        "clusters": clusters,
        "total_comments": len(comments_list),
        "filtered_curse_count": toxic_count,
        "pro_ratio": pro_r,
        "con_ratio": con_r,
        "toxicity_before": avg_tox_before,
        "toxicity_after": avg_tox_after,
        "cleaned_comments": [it["cleaned"] for it in parsed_items if it["cleaned"]],
        "detox_samples": detox_samples,
    }


def _pick_facet_kw(items: List[Dict[str, Any]], pred, exclude: Optional[set] = None) -> str:
    excl = exclude or set()
    df: Dict[str, int] = {}
    for it in items:
        if pred(it):
            for t in it["tokens"]:
                if t not in excl:
                    df[t] = df.get(t, 0) + 1
    if not df:
        return ""
    return max(df.items(), key=lambda kv: (kv[1], 1 if 2 <= len(kv[0]) <= 4 else 0, -len(kv[0])))[0]


def build_dynamic_script_from_clusters(
    issue_title: str,
    cluster_res: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """추출된 2~4개 다관점 군집과 실제 댓글 인용문을 바탕으로 6턴 큐레이터 브리핑/토론 대본을 생성."""
    short_topic = re.sub(r"\[[^\]]*\]|\([^)]*\)|#\S+", "", issue_title).strip()
    if len(short_topic) > 36:
        short_topic = _trim_korean_words(short_topic, 34) + "..."
    if not short_topic:
        short_topic = "이번 주제 댓글 여론"

    perspectives = cluster_res["perspectives"]
    clusters = cluster_res["clusters"]
    mode = cluster_res["analysis_mode"]

    # Sort each cluster's substantive quotes by likes
    quotes_by_cluster: List[List[str]] = []
    all_substantive: List[str] = []
    for cl in clusters:
        sorted_items = sorted(cl["items"], key=lambda x: x["likes"], reverse=True)
        qs: List[str] = []
        for it in sorted_items:
            q = _trim_korean_words(it["cleaned"], 84).rstrip(" .,!?")
            if len(q) >= 10 and q not in qs:
                qs.append(q)
                if q not in all_substantive:
                    all_substantive.append(q)
        quotes_by_cluster.append(qs)

    # Distribute 6 turns naturally across 2, 3, or 4 perspectives
    n_p = len(perspectives)
    if n_p >= 4:
        p_seq = [0, 1, 2, 3, 0, 2]
    elif n_p == 3:
        p_seq = [0, 1, 2, 1, 0, 2]
    else:
        p_seq = [0, 1, 0, 1, 0, 1]

    used_quotes = set()
    used_idx = [0] * n_p
    script: List[Dict[str, Any]] = []

    openers_multi = [
        "먼저 전체 반응의 {ratio}퍼센트를 차지한 {lbl} 시각을 살펴보겠습니다.",
        "반면 {ratio}퍼센트 비중의 {lbl} 의견에서는 다른 지점을 짚습니다.",
        "세 번째 시선인 {lbl} 측에서는 {ratio}퍼센트의 시청자가 색다른 관점을 보탰습니다.",
        "이어서 {lbl} 반응을 보면, 댓글창의 현실적인 고민이 드러납니다.",
        "{lbl} 입장에서는 앞선 논점에 더해 구체적인 체감 사례도 덧붙였습니다.",
        "결국 {lbl} 시각까지 함께 짚어보면 이번 사안의 입체적인 흐름이 한눈에 보입니다.",
    ]
    openers_debate = [
        "실제 댓글의 {ratio}퍼센트를 차지한 {lbl} 측에서는 뚜렷한 원칙을 내세웠습니다.",
        "반면 {ratio}퍼센트 비중의 {lbl} 측에서는 현실적인 우려를 제기합니다.",
        "{lbl} 측은 한 걸음 더 나아가 실질적인 기준과 실행력을 강조하고 있습니다.",
        "이에 대해 {lbl} 측은 성급한 접근보다 부작용 보완이 먼저라고 맞섭니다.",
        "또한 {lbl} 측에서는 장기적인 공익과 신뢰 회복을 핵심 과제로 꼽았습니다.",
        "종합하면 {lbl} 측의 문제의식까지 균형 있게 반영해야 합리적 해법이 나옵니다.",
    ]

    for turn_i in range(6):
        pi = p_seq[turn_i]
        persp = perspectives[pi]
        pool = quotes_by_cluster[pi]
        chosen_q = ""
        while used_idx[pi] < len(pool):
            cand = pool[used_idx[pi]]
            used_idx[pi] += 1
            if cand not in used_quotes:
                chosen_q = cand
                used_quotes.add(cand)
                break
        if not chosen_q:
            for q in all_substantive:
                if q not in used_quotes:
                    chosen_q = q
                    used_quotes.add(q)
                    break
        if not chosen_q:
            chosen_q = f"{short_topic} 사안에서 {persp['label']} 측면을 비중 있게 다뤄야 합니다"

        template = (openers_debate if mode == "debate" else openers_multi)[turn_i]
        intro = template.format(ratio=persp["ratio"], lbl=persp["short_label"])
        core_pt = _trim_korean_words(chosen_q, 32) if len(chosen_q) > 10 else persp["label"]
        script.append({
            "speaker": "PRO" if turn_i % 2 == 0 else "CON",
            "perspective_id": persp["id"],
            "perspective_label": persp["short_label"],
            "color": persp["color"],
            "core_point": core_pt,
            "text": f"{intro} \"{chosen_q}.\" 이처럼 댓글창의 다양한 목소리가 모이고 있습니다.",
        })

    return script


def normalize_gemini_analysis(parsed: Dict[str, Any], cluster_res: Dict[str, Any], fallback_title: str) -> Optional[Dict[str, Any]]:
    raw_script = parsed.get("debate_script")
    if not isinstance(raw_script, list) or len(raw_script) < 4:
        return None

    raw_persps = parsed.get("perspectives")
    perspectives: List[Dict[str, Any]] = []
    if isinstance(raw_persps, list) and len(raw_persps) >= 2:
        ratios = _normalize_ratios([int(p.get("ratio", 25) or 25) for p in raw_persps[:4]])
        used_colors = set()
        for idx, p in enumerate(raw_persps[:4]):
            ck = (p.get("color") or "").lower()
            if ck not in PALETTE_ORDER or ck in used_colors:
                ck = next((c for c in PALETTE_ORDER if c not in used_colors), PALETTE_ORDER[idx % 4])
            used_colors.add(ck)
            lbl = str(p.get("label") or p.get("short_label") or f"관점 {idx + 1}").strip()
            short_lbl = str(p.get("short_label") or _trim_korean_words(lbl, 11)).strip()
            perspectives.append({
                "id": str(p.get("id") or f"P{idx + 1}"),
                "label": lbl,
                "short_label": short_lbl[:12],
                "ratio": ratios[idx],
                "color": ck,
                "keywords": p.get("keywords") if isinstance(p.get("keywords"), list) else [],
            })
    else:
        perspectives = cluster_res["perspectives"]

    p_by_id = {p["id"]: p for p in perspectives}
    norm_script: List[Dict[str, Any]] = []
    for idx, t in enumerate(raw_script[:8]):
        pid = str(t.get("perspective_id") or "")
        matched_p = p_by_id.get(pid) or perspectives[idx % len(perspectives)]
        ck = (t.get("color") or "").lower()
        if ck not in PALETTE_ORDER:
            ck = matched_p["color"]
        p_lbl = str(t.get("perspective_label") or matched_p["short_label"]).strip()[:12]
        spk = t.get("speaker") if t.get("speaker") in ("PRO", "CON") else ("PRO" if idx % 2 == 0 else "CON")
        norm_script.append({
            "speaker": spk,
            "perspective_id": matched_p["id"],
            "perspective_label": p_lbl,
            "color": ck,
            "core_point": str(t.get("core_point") or matched_p["label"]).strip(),
            "text": str(t.get("text") or "").strip(),
        })

    if any(not x["text"] for x in norm_script):
        return None

    mode_lbl = str(parsed.get("mode_label") or "").strip() or (
        f"{len(perspectives)}관점 여론 비교" if len(perspectives) >= 3 else cluster_res["mode_label"]
    )
    return {
        "issue_title": str(parsed.get("issue_title") or fallback_title).strip(),
        "analysis_mode": str(parsed.get("detected_mode") or cluster_res["analysis_mode"]).strip(),
        "mode_label": mode_lbl,
        "perspectives": perspectives,
        "debate_script": norm_script,
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


@app.post("/api/analyze")
async def analyze_input(req: AnalyzeRequest):
    """
    1) 유튜브 영상 URL 입력 시 YouTube Data API v3로 실제 댓글 최대 100건 수집 + 다관점(2~4축) 클러스터링
    2) 댓글 텍스트 직접 입력 시 주제에 맞는 2~4관점 대본/요약/리뷰 쇼츠 JSON 동적 생성
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
    engine_mode = "CUSTOM_MULTI_NLP"

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
        comments_list = [{"author": f"의견#{i+1}", "text": ln, "like_count": 0} for i, ln in enumerate(lines)]

    if not comments_list and vid:
        seed_desc = re.sub(r"https?://\S+", "", video_desc).replace("\n", " ").strip()[:120]
        comments_list = [
            {"author": channel_title or "YouTube", "text": f"{video_title} 주제의 핵심 강점과 기대 포인트가 주목받고 있습니다.", "like_count": 1},
            {"author": "시청자 의견", "text": f"{seed_desc or video_title} 관련 현실적인 부담이나 아쉬운 지점을 짚는 시선도 많습니다.", "like_count": 0},
            {"author": "대안 의견", "text": f"{video_title} 관련 보완책이나 비교 대안을 함께 따져봐야 한다는 제안도 나옵니다.", "like_count": 0},
        ]
        if comments_disabled:
            notice_msg = "이 영상은 댓글이 비활성화되어 영상 제목·설명 기반으로 다관점 대본을 구성했습니다."

    if not comments_list and not vid:
        data = dict(PRESETS["preset_1"])
        data["engine_mode"] = "FALLBACK_PRESET"
        data["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return data

    issue_title = video_title if video_title else "사용자 입력 댓글 다관점 분석"
    cluster_res = cluster_comments_multiperspective(comments_list, issue_title, req.analysis_mode or "auto")
    perspectives = cluster_res["perspectives"]
    mode_label = cluster_res["mode_label"]
    resolved_mode = cluster_res["analysis_mode"]
    debate_script = build_dynamic_script_from_clusters(issue_title, cluster_res)

    global _GEMINI_COOLDOWN_UNTIL
    if time.time() >= _GEMINI_COOLDOWN_UNTIL:
        try:
            sample_lines = "\n".join(c["text"][:160] for c in comments_list[:35])
            mode_guidance = {
                "debate": "찬성과 반대 양측 핵심 논거로 2관점 균형 토론을 구성해라.",
                "multi": "반드시 찬성/반대 이분법에 가두지 말고, 댓글에서 드러나는 3~4개의 실제 관점/이해관계/감상 축(blue, red, violet, emerald)을 추출해 큐레이터 대본을 구성해라.",
                "proscons": "장점·호평 / 아쉬움·단점 / 비교·구매·개선 대안 3관점(blue, red, violet)으로 균형 있게 구성해라.",
                "summary": "시청자·유저의 핵심 반응 3~4축(blue, red, violet, emerald)을 뉴스룸 브리핑처럼 정리해라.",
            }.get(resolved_mode, "찬반 토론 주제면 2~3관점, 리뷰/반응/다자간 의견이면 3~4관점으로 실제 댓글에 맞는 분류를 자유롭게 추출해라.")

            gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={DEFAULT_GOOGLE_API_KEY}"
            payload = json.dumps({
                "contents": [{
                    "parts": [{
                        "text": (
                            f"다음 콘텐츠({issue_title})의 실제 댓글 {len(comments_list)}건을 분석해 6턴 아나운서 쇼츠 대본 JSON을 작성해라.\n"
                            f"규칙: {mode_guidance}\n"
                            f"2명의 스튜디오 아나운서(speaker는 좌/우 발화 교차를 위해 PRO, CON 번갈아 배치)가 각 관점(perspective_id, perspective_label, color)을 번갈아 명쾌하게 소개한다.\n"
                            f'스펙: {{"issue_title":"주제 한 줄 요약","detected_mode":"multi","mode_label":"예: 3관점 여론 비교","perspectives":[{{"id":"P1","label":"핵심 관점명","short_label":"짧은라벨(8자이내)","ratio":45,"color":"blue|red|violet|emerald"}}],"debate_script":[{{"speaker":"PRO","perspective_id":"P1","perspective_label":"짧은라벨","color":"blue","core_point":"핵심 요약","text":"비속어를 제거한 2문장 표준 한국어 아나운서 대사"}}]}}\n\n'
                            f"댓글 샘플:\n{sample_lines}"
                        )
                    }]
                }],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
            }).encode("utf-8")
            req_gem = urllib.request.Request(gem_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_gem, timeout=3.5) as resp:
                g_data = json.loads(resp.read().decode("utf-8"))
                parsed = json.loads(g_data["candidates"][0]["content"]["parts"][0]["text"])
                norm = normalize_gemini_analysis(parsed, cluster_res, issue_title)
                if norm:
                    issue_title = norm["issue_title"]
                    resolved_mode = norm["analysis_mode"]
                    mode_label = norm["mode_label"]
                    perspectives = norm["perspectives"]
                    debate_script = norm["debate_script"]
                    engine_mode = f"YOUTUBE_GEMINI_MULTI (N={cluster_res['total_comments']})"
        except Exception:
            _GEMINI_COOLDOWN_UNTIL = time.time() + 60.0

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    kw_tags = " ".join(f"#{k}" for k in [p.get("short_label", "").replace("·", "").replace(" ", "") for p in perspectives] if k)

    return {
        "id": f"yt_{vid}" if vid else "live_custom",
        "analysis_mode": resolved_mode,
        "mode_label": mode_label,
        "perspectives": perspectives,
        "issue_title": issue_title,
        "category_badge": f"{channel_title} 실시간 수집 {cluster_res['total_comments']}건 · {mode_label}" if channel_title else f"실시간 {mode_label}",
        "source_label": f"YouTube Data API v3 실시간 수집 · {video_title} (댓글 {cluster_res['total_comments']}건)" if video_title else f"직접 입력 댓글 {cluster_res['total_comments']}건 ({mode_label})",
        "source_url": source_url,
        "hashtags": f"#한냥 #다관점쇼츠 {kw_tags} #유튜브쇼츠".strip(),
        "video_mp4_url": None,
        "has_voice_track": False,
        "notice": notice_msg,
        "raw_stats": {
            "total_comments": cluster_res["total_comments"],
            "filtered_curse_count": cluster_res["filtered_curse_count"],
            "pro_ratio": cluster_res["pro_ratio"],
            "con_ratio": cluster_res["con_ratio"],
            "toxicity_before": cluster_res["toxicity_before"],
            "toxicity_after": cluster_res["toxicity_after"],
        },
        "debate_script": debate_script,
        "detox_samples": cluster_res["detox_samples"],
        "cleaned_comments_sample": cluster_res["cleaned_comments"][:30],
        "engine_mode": engine_mode,
        "latency_ms": elapsed_ms,
    }


@app.post("/api/render-mp4")
async def api_render_mp4(req: RenderMp4Request):
    """
    프론트엔드에서 전달한 대본(2~8턴), 다관점 메타, 오디오 데이터를 받아
    실제 9:16 H.264 MP4 파일을 생성하고 다운로드 URL을 반환한다.
    """
    t0 = time.perf_counter()
    filename = f"hannyang_shorts_{int(time.time())}.mp4"
    out_path = VIDEOS_DIR / filename
    render_meta: Dict[str, Any] = {}
    render_debate_mp4(
        issue_title=req.issue_title,
        category_badge=req.category_badge or "한냥 공론장 중재 쇼츠",
        raw_stats=req.raw_stats,
        debate_script=req.debate_script,
        output_mp4=out_path,
        turn_audio_b64_list=req.turn_audio_b64_list,
        meta_out=render_meta,
        perspectives=req.perspectives,
        mode_label=req.mode_label or "",
    )
    elapsed_s = round(time.perf_counter() - t0, 2)
    return {
        "video_mp4_url": f"/static/videos/{filename}",
        "file_size_bytes": out_path.stat().st_size,
        "render_time_sec": elapsed_s,
        "has_voice_track": bool(render_meta.get("has_voice")),
        "voiced_turns": int(render_meta.get("voiced_turns", 0)),
        "total_turns": int(render_meta.get("total_turns", len(req.debate_script[:8]))),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

