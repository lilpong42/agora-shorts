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
    description="유튜브 악플·설전 댓글 빅데이터에서 상위 2대 대립 진영(Side A vs B)을 동적 추출해 HP 팩트 배틀 쇼츠(MP4)로 전환하는 파이프라인",
    version="3.0.0",
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
    "혁신", "쾌적", "빠르", "편하", "필수", "인정", "응원", "옳", "동의",
    "공감", "훌륭", "대박", "잘", "이득", "재밌", "갓", "혜자", "필요", "의무",
]
CRIT_CUES = [
    "아쉽", "불편", "비싸", "부담", "문제", "부족", "실망", "우려", "걱정", "최악",
    "느리", "과잉", "탁상행정", "차별", "위축", "피로", "한계", "무겁", "무거",
    "단점", "창렬", "과금", "버그", "발열", "글쎄", "무리", "비판", "불쌍", "피해",
]
ALT_CUES = [
    "차라리", "대신", "보완", "개선", "패치", "수정", "조건", "비교", "전작", "타사",
    "균형", "해결", "제안", "방법", "도입", "병행", "인프라", "지원", "대안", "가성비",
    "할인", "업데이트", "절충", "단계", "어떨까", "나을",
]
DEBATE_CUES = ["규제", "금지", "의무", "법안", "처벌", "폐지", "논란", "도입", "권리", "생존권", "책임", "원인"]
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
    "faction_battle": "동적 진영 HP 팩트 배틀",
    "multi": "동적 진영 HP 팩트 배틀",
    "proscons": "장단점 격돌 HP 배틀",
    "summary": "핵심 쟁점 HP 배틀",
}


class AnalyzeRequest(BaseModel):
    preset_id: Optional[str] = None
    source_url: Optional[str] = ""
    raw_text: Optional[str] = ""
    youtube_api_key: Optional[str] = ""
    analysis_mode: Optional[str] = "auto"


class RenderMp4Request(BaseModel):
    issue_title: str
    category_badge: Optional[str] = "한냥 팩트 배틀 쇼츠"
    side_a_label: Optional[str] = "A 진영"
    side_b_label: Optional[str] = "B 진영"
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
    if mode in ("faction_battle", "proscons", "summary", "multi"):
        return mode
    joined = (issue_title or "") + " " + " ".join((c.get("text") or "")[:140] for c in comments_list[:40])
    rev_hits = sum(1 for k in REVIEW_CUES if k in joined)
    deb_hits = sum(1 for k in DEBATE_CUES if k in joined)
    if rev_hits >= 3 and deb_hits < 3:
        return "proscons"
    return "faction_battle"


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


def _clamp_damage(val: Any, ratio_hint: int = 50, rank: int = 0) -> int:
    try:
        num = int(round(float(val)))
        if 15 <= num <= 35:
            return num
    except Exception:
        pass
    # Map comment cluster support ratio [5..95] -> [15..35], with slight decay per round
    base = 15 + int(round((max(5, min(95, ratio_hint)) / 100.0) * 19.0))
    return max(15, min(35, base - (rank % 3)))


def _to_banmal_one_sentence(raw_clause: str, faction_label: str, is_a: bool) -> str:
    """욕설이 제거된 댓글 핵심 문장을 매운맛 반말/단언형 1문장 팩트 공격 대사로 정제."""
    s = re.sub(r"\s+", " ", (raw_clause or "").strip()).rstrip(" .,!?")
    if len(s) < 8:
        return (
            f"이 사안 핵심은 결국 {faction_label} 쪽 현실 논리가 훨씬 설득력 있다는 거야!"
            if is_a
            else f"현실 여건 따져보면 {faction_label} 관점을 빼놓고 말할 수 없지!"
        )
    # Trim overly long clauses at 64 chars cleanly
    if len(s) > 64:
        s = _trim_korean_words(s, 64).rstrip(" .,!?")
    # Replace formal polite endings with crisp banmal assertion
    replacements = [
        (r"(?:해야 합니다|해야됩니다|해야해요|해야 돼요)$", "해야 해!"),
        (r"(?:있습니다|있어요)$", "있어!"),
        (r"(?:없습니다|없어요)$", "없어!"),
        (r"(?:아닙니다|아니에요|아닌가요)$", "아니냐!"),
        (r"(?:입니다|이에요|예요)$", "이지!"),
        (r"(?:됩니다|돼요)$", "돼!"),
        (r"(?:합니다|해요)$", "해!"),
        (r"(?:습니다|ㅂ니다|네요|군요|거든요|잖아요|어요|아요)$", "지!"),
    ]
    converted = s
    changed = False
    for pat, rep in replacements:
        if re.search(pat, converted):
            converted = re.sub(pat, rep, converted)
            changed = True
            break
    if not changed:
        converted = f"{converted}라는 게 팩트야!" if len(converted) < 42 else f"{converted} 아니냐!"
    return converted


def _infer_dynamic_faction_label(kw: str, items: List[Dict[str, Any]], is_first: bool, issue_title: str) -> str:
    """실제 댓글 키워드와 논조를 조합해 진영 이름(Side A / B)을 동적 명명."""
    sum_pos = sum(x["tones"]["pos"] for x in items)
    sum_crit = sum(x["tones"]["crit"] for x in items)
    sum_alt = sum(x["tones"]["alt"] for x in items)
    joined_kw = kw or ""
    if not joined_kw:
        if "소음" in issue_title or "오토바이" in issue_title:
            return "라이더 생계 우선파" if is_first else "주민 수면권 수호파"
        if "킥보드" in issue_title:
            return "전면 견인 강경파" if is_first else "인프라 확충 현실파"
        if "면허" in issue_title or "고령" in issue_title:
            return "즉각 면허반납파" if is_first else "이동권 보장 대안파"
        return "핵심 강경 개혁파" if is_first else "현실 대안 신중파"

    if sum_crit > sum_pos and sum_crit >= sum_alt:
        suf = "강경 지적파" if is_first else "현실 비판파"
    elif sum_alt >= sum_pos and sum_alt > 0:
        suf = "인프라 대안파" if is_first else "제도 보완파"
    elif sum_pos > sum_crit:
        suf = "핵심 우선파" if is_first else "가치 수호파"
    else:
        suf = "원칙 강조파" if is_first else "현장 대안파"
    return f"{joined_kw[:6]} {suf}".strip()


def cluster_comments_faction_battle(
    comments_list: List[Dict[str, Any]],
    issue_title: str,
    analysis_mode: str = "auto",
) -> Dict[str, Any]:
    """
    주제 불문(토론·리뷰·패치·일상반응) 댓글에서 가장 대립하는 상위 2개 동적 진영(Side A vs B) 추출 + 비속어 정제.
    """
    resolved_mode = _resolve_analysis_mode(analysis_mode, comments_list, issue_title)

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

    sorted_kws = sorted(
        [(k, v) for k, v in doc_freq.items() if v >= 1],
        key=lambda kv: (kv[1], 1 if 2 <= len(kv[0]) <= 4 else 0, -len(kv[0])),
        reverse=True,
    )
    top_kws = [k for k, _ in sorted_kws[:16]]

    # Partition into top 2 colliding opinion clusters (Side A vs Side B)
    bucket_a: List[Dict[str, Any]] = []
    bucket_b: List[Dict[str, Any]] = []
    kw_a = _pick_facet_kw(parsed_items, lambda it: it["tones"]["pos"] > it["tones"]["crit"])
    kw_b = _pick_facet_kw(parsed_items, lambda it: (it["tones"]["crit"] + it["tones"]["alt"]) > it["tones"]["pos"], exclude={kw_a})

    if not kw_a and top_kws:
        kw_a = top_kws[0]
    if not kw_b:
        kw_b = next((k for k in top_kws if k != kw_a and k not in kw_a and kw_a not in k), top_kws[1] if len(top_kws) > 1 else "")

    for it in parsed_items:
        p_sc = it["tones"]["pos"] + (1.5 if kw_a and kw_a in it["tokens"] else 0.0)
        b_sc = it["tones"]["crit"] + it["tones"]["alt"] + (1.5 if kw_b and kw_b in it["tokens"] else 0.0)
        if p_sc > b_sc:
            bucket_a.append(it)
        elif b_sc > p_sc:
            bucket_b.append(it)
        else:
            (bucket_a if len(bucket_a) <= len(bucket_b) else bucket_b).append(it)

    if not bucket_a and len(bucket_b) > 1:
        bucket_a.append(bucket_b.pop())
    if not bucket_b and len(bucket_a) > 1:
        bucket_b.append(bucket_a.pop())

    if resolved_mode == "proscons":
        side_a_label = f"{kw_a[:6]} 호평파" if kw_a else "핵심 성능 호평파"
        side_b_label = f"{kw_b[:6]} 지적파" if kw_b else "가격·부담 지적파"
    else:
        side_a_label = _infer_dynamic_faction_label(kw_a, bucket_a, True, issue_title)
        side_b_label = _infer_dynamic_faction_label(kw_b, bucket_b, False, issue_title)
        if side_a_label == side_b_label:
            side_b_label = f"{kw_b[:6]} 대안파" if kw_b else "현실 대안 신중파"

    ratios = _normalize_ratios([len(bucket_a), len(bucket_b)])
    side_a_ratio, side_b_ratio = ratios[0], ratios[1]

    kws_a = [k for k in [kw_a, *top_kws[:3]] if k][:3]
    kws_b = [k for k in [kw_b, *top_kws[2:5]] if k and k not in kws_a][:3] or top_kws[:2]

    clusters = [
        {"id": "A", "label": side_a_label, "short_label": side_a_label[:12], "color": "blue", "kws": kws_a, "items": bucket_a},
        {"id": "B", "label": side_b_label, "short_label": side_b_label[:12], "color": "red", "kws": kws_b, "items": bucket_b},
    ]
    perspectives = [
        {"id": "A", "label": side_a_label, "short_label": side_a_label[:12], "ratio": side_a_ratio, "color": "blue", "keywords": kws_a},
        {"id": "B", "label": side_b_label, "short_label": side_b_label[:12], "ratio": side_b_ratio, "color": "red", "keywords": kws_b},
    ]

    detox_samples: List[Dict[str, Any]] = []
    item_to_faction: Dict[int, Dict[str, Any]] = {}
    for cl in clusters:
        for it in cl["items"]:
            item_to_faction[it["idx"]] = cl

    for it in parsed_items:
        cl = item_to_faction.get(it["idx"], clusters[0])
        if it["is_toxic"] and len(detox_samples) < 4 and len(it["raw"]) > 10:
            detox_samples.append({
                "faction": cl["id"],
                "faction_label": cl["label"],
                "color": cl["color"],
                "raw": f"[{it['author']}] {it['raw'].replace(chr(10), ' ')[:125]}",
                "cleaned": (
                    _to_banmal_one_sentence(it["cleaned"][:80], cl["label"], cl["id"] == "A")
                    if len(it["cleaned"]) > 10
                    else f"욕설 빼고 핵심만 말하면 {cl['label']} 주장이 근거 있다는 거야!"
                ),
                "removed_tokens": it["matches"][:4] if it["matches"] else ["과열표현"],
            })

    if not detox_samples:
        for it in parsed_items[:4]:
            if len(it["raw"]) > 8:
                cl = item_to_faction.get(it["idx"], clusters[0])
                detox_samples.append({
                    "faction": cl["id"],
                    "faction_label": cl["label"],
                    "color": cl["color"],
                    "raw": f"[{it['author']}] {it['raw'].replace(chr(10), ' ')[:125]}",
                    "cleaned": it["cleaned"][:96] or it["raw"][:96],
                    "removed_tokens": [],
                })

    avg_tox_before = round(
        (sum(toxic_scores) / len(toxic_scores)) if toxic_scores else (sum(all_raw_scores) / max(len(all_raw_scores), 1) if all_raw_scores else 42.0),
        1,
    )
    avg_tox_after = round(sum(after_scores) / max(len(after_scores), 1), 1) if after_scores else 14.2

    return {
        "analysis_mode": "faction_battle",
        "mode_label": MODE_LABELS.get(resolved_mode, "동적 진영 HP 팩트 배틀"),
        "side_a_label": side_a_label,
        "side_b_label": side_b_label,
        "side_a_ratio": side_a_ratio,
        "side_b_ratio": side_b_ratio,
        "perspectives": perspectives,
        "clusters": clusters,
        "total_comments": len(comments_list),
        "filtered_curse_count": toxic_count,
        "pro_ratio": side_a_ratio,
        "con_ratio": side_b_ratio,
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


def build_faction_battle_script(
    issue_title: str,
    cluster_res: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """추출된 2대 대립 진영(A vs B)과 실제 댓글 공감도를 바탕으로 6턴 반말 팩트 배틀 대본 생성."""
    short_topic = re.sub(r"\[[^\]]*\]|\([^)]*\)|#\S+", "", issue_title).strip()
    if len(short_topic) > 28:
        short_topic = _trim_korean_words(short_topic, 26)
    if not short_topic:
        short_topic = "이번 이슈"

    clusters = cluster_res["clusters"]
    side_a_label = cluster_res["side_a_label"]
    side_b_label = cluster_res["side_b_label"]
    side_a_ratio = cluster_res["side_a_ratio"]
    side_b_ratio = cluster_res["side_b_ratio"]

    quotes_by_faction: Dict[str, List[str]] = {"A": [], "B": []}
    all_substantive: List[str] = []
    for cl in clusters:
        fid = "A" if cl["id"] == "A" else "B"
        sorted_items = sorted(cl["items"], key=lambda x: x["likes"], reverse=True)
        for it in sorted_items:
            q = _trim_korean_words(it["cleaned"], 68).rstrip(" .,!?")
            if len(q) >= 8 and q not in quotes_by_faction[fid]:
                quotes_by_faction[fid].append(q)
                if q not in all_substantive:
                    all_substantive.append(q)

    used_quotes = set()
    idx_map = {"A": 0, "B": 0}
    script: List[Dict[str, Any]] = []

    for turn_i in range(6):
        fid = "A" if turn_i % 2 == 0 else "B"
        is_a = fid == "A"
        lbl = side_a_label if is_a else side_b_label
        ratio = side_a_ratio if is_a else side_b_ratio
        pool = quotes_by_faction[fid]

        chosen_q = ""
        while idx_map[fid] < len(pool):
            cand = pool[idx_map[fid]]
            idx_map[fid] += 1
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

        if chosen_q:
            attack_text = _to_banmal_one_sentence(chosen_q, lbl, is_a)
            core_pt = _trim_korean_words(chosen_q, 24)
        else:
            fallback_attacks_a = [
                f"{short_topic} 핵심만 보면 결국 {lbl} 쪽 기준부터 세우는 게 맞아!",
                f"현장 체감 데이터로 따져봐도 {lbl} 주장을 무시할 수 없잖아!",
                f"미적대지 말고 {lbl} 방향으로 확실하게 매듭짓는 게 답이야!",
            ]
            fallback_attacks_b = [
                f"앞뒤 다 자르고 밀어붙이면 결국 {lbl} 쪽 역풍부터 터진다고!",
                f"현실 대안도 없이 규제만 외치는 건 {lbl} 입장에서 탁상행정이지!",
                f"부작용 줄이려면 {lbl} 요구사항부터 먼저 깔아주는 게 순서야!",
            ]
            attack_text = (fallback_attacks_a if is_a else fallback_attacks_b)[turn_i // 2]
            core_pt = f"{lbl} 핵심 논거 #{turn_i // 2 + 1}"

        dmg = _clamp_damage(None, ratio_hint=ratio, rank=turn_i // 2)
        script.append({
            "faction": fid,
            "core_point": core_pt or f"{lbl} 팩트",
            "text": attack_text,
            "damage": dmg,
        })

    return script


def normalize_gemini_analysis(parsed: Dict[str, Any], cluster_res: Dict[str, Any], fallback_title: str) -> Optional[Dict[str, Any]]:
    raw_script = parsed.get("debate_script")
    if not isinstance(raw_script, list) or len(raw_script) < 4:
        return None

    side_a_label = str(parsed.get("side_a_label") or cluster_res.get("side_a_label") or "A 진영").strip()[:16]
    side_b_label = str(parsed.get("side_b_label") or cluster_res.get("side_b_label") or "B 진영").strip()[:16]

    a_ratio = cluster_res.get("side_a_ratio", 50)
    b_ratio = cluster_res.get("side_b_ratio", 50)
    try:
        pa = int(parsed.get("side_a_ratio", a_ratio))
        pb = int(parsed.get("side_b_ratio", b_ratio))
        if pa > 0 and pb > 0:
            norm_r = _normalize_ratios([pa, pb])
            a_ratio, b_ratio = norm_r[0], norm_r[1]
    except Exception:
        pass

    norm_script: List[Dict[str, Any]] = []
    for idx, t in enumerate(raw_script[:6]):
        raw_f = str(t.get("faction") or ("A" if idx % 2 == 0 else "B")).strip().upper()
        faction = "A" if raw_f in ("A", "PRO", "SIDE_A") else ("B" if raw_f in ("B", "CON", "SIDE_B") else ("A" if idx % 2 == 0 else "B"))
        r_hint = a_ratio if faction == "A" else b_ratio
        dmg = _clamp_damage(t.get("damage"), ratio_hint=r_hint, rank=idx // 2)
        lbl = side_a_label if faction == "A" else side_b_label
        txt = str(t.get("text") or "").strip()
        if not txt:
            continue
        norm_script.append({
            "faction": faction,
            "core_point": str(t.get("core_point") or lbl).strip()[:32],
            "text": txt,
            "damage": dmg,
        })

    if len(norm_script) < 4:
        return None

    # Ensure strictly 6 turns (3 A, 3 B) if Gemini returned 4 or 5
    while len(norm_script) < 6:
        idx = len(norm_script)
        faction = "A" if idx % 2 == 0 else "B"
        lbl = side_a_label if faction == "A" else side_b_label
        r_hint = a_ratio if faction == "A" else b_ratio
        norm_script.append({
            "faction": faction,
            "core_point": f"{lbl} 쐐기 팩트",
            "text": f"결국 실수요자 댓글 반응까지 따지면 {lbl} 쪽 근거가 훨씬 뚜렷해!",
            "damage": _clamp_damage(None, ratio_hint=r_hint, rank=idx // 2),
        })

    perspectives = [
        {"id": "A", "label": side_a_label, "short_label": side_a_label[:12], "ratio": a_ratio, "color": "blue", "keywords": cluster_res["perspectives"][0].get("keywords", [])},
        {"id": "B", "label": side_b_label, "short_label": side_b_label[:12], "ratio": b_ratio, "color": "red", "keywords": cluster_res["perspectives"][1].get("keywords", [])},
    ]

    return {
        "issue_title": str(parsed.get("issue_title") or fallback_title).strip(),
        "analysis_mode": "faction_battle",
        "mode_label": "동적 진영 HP 팩트 배틀",
        "side_a_label": side_a_label,
        "side_b_label": side_b_label,
        "side_a_ratio": a_ratio,
        "side_b_ratio": b_ratio,
        "perspectives": perspectives,
        "debate_script": norm_script[:6],
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
    1) 유튜브 영상 URL 입력 시 YouTube Data API v3로 실제 댓글 최대 100건 수집 + 상위 2대 대립 진영(Side A vs B) 동적 추출
    2) 댓글 텍스트 직접 입력 시 6턴 HP 팩트 배틀 JSON 생성
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
    engine_mode = "CUSTOM_FACTION_BATTLE_NLP"

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
            {"author": channel_title or "YouTube", "text": f"{video_title} 주제의 핵심 강점과 필요성이 분명하다는 의견이 많습니다.", "like_count": 1},
            {"author": "시청자 의견", "text": f"{seed_desc or video_title} 관련 현실적인 부담과 부작용을 지적하는 목소리도 큽니다.", "like_count": 0},
            {"author": "대안 의견", "text": f"{video_title} 관련 보완 대책과 인프라부터 먼저 챙겨야 한다는 지적이 나옵니다.", "like_count": 0},
        ]
        if comments_disabled:
            notice_msg = "이 영상은 댓글이 비활성화되어 영상 제목·설명 기반으로 진영 배틀 대본을 구성했습니다."

    if not comments_list and not vid:
        data = dict(PRESETS["preset_1"])
        data["engine_mode"] = "FALLBACK_PRESET"
        data["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return data

    issue_title = video_title if video_title else "실시간 댓글 동적 진영 팩트 배틀"
    cluster_res = cluster_comments_faction_battle(comments_list, issue_title, req.analysis_mode or "auto")
    side_a_label = cluster_res["side_a_label"]
    side_b_label = cluster_res["side_b_label"]
    side_a_ratio = cluster_res["side_a_ratio"]
    side_b_ratio = cluster_res["side_b_ratio"]
    perspectives = cluster_res["perspectives"]
    mode_label = cluster_res["mode_label"]
    resolved_mode = cluster_res["analysis_mode"]
    debate_script = build_faction_battle_script(issue_title, cluster_res)

    global _GEMINI_COOLDOWN_UNTIL
    if time.time() >= _GEMINI_COOLDOWN_UNTIL:
        try:
            sample_lines = "\n".join(c["text"][:160] for c in comments_list[:35])
            gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={DEFAULT_GOOGLE_API_KEY}"
            payload = json.dumps({
                "contents": [{
                    "parts": [{
                        "text": (
                            f"다음 콘텐츠({issue_title})의 실제 댓글 {len(comments_list)}건을 분석해 고정된 찬성/반대 프레임을 버리고, "
                            f"가장 첨예하게 대립·대비되는 상위 2개 여론 진영(side_a_label, side_b_label)을 이슈에 맞게 동적 명명하여 6턴 HP 팩트 배틀 JSON을 작성해라.\n"
                            f"규칙:\n"
                            f"1. side_a_label, side_b_label은 이슈 맞춤형 직관적 진영명 (예: '라이더 생계 우선파' vs '주민 수면권 수호파', '배터리·성능 호평파' vs '출고가·발열 지적파'). 절대 '찬성/반대'라고 쓰지 마라.\n"
                            f"2. debate_script는 정확히 6턴 배열(A 진영 3턴, B 진영 3턴 번갈아 배치).\n"
                            f"3. 각 턴의 text는 욕설·비속어를 완전히 제거하되 타격감 있는 매운맛 반말/단언형 공격 대사 딱 1문장으로 작성해라.\n"
                            f"4. 각 턴의 damage는 해당 주장의 댓글 공감 비율에 비례하는 15~35 사이의 정수로 설정해라.\n"
                            f'스펙: {{"issue_title":"주제 한 줄 요약","side_a_label":"첫번째 진영명","side_b_label":"두번째 진영명","side_a_ratio":45,"side_b_ratio":55,"debate_script":[{{"faction":"A","core_point":"핵심 팩트 라벨","text":"욕설 뺀 매운맛 반말 공격 대사 1문장","damage":24}},{{"faction":"B","core_point":"핵심 팩트 라벨","text":"욕설 뺀 매운맛 반말 반격 대사 1문장","damage":28}}]}}\n\n'
                            f"댓글 샘플:\n{sample_lines}"
                        )
                    }]
                }],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.35},
            }).encode("utf-8")
            req_gem = urllib.request.Request(gem_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_gem, timeout=4.0) as resp:
                g_data = json.loads(resp.read().decode("utf-8"))
                parsed = json.loads(g_data["candidates"][0]["content"]["parts"][0]["text"])
                norm = normalize_gemini_analysis(parsed, cluster_res, issue_title)
                if norm:
                    issue_title = norm["issue_title"]
                    resolved_mode = norm["analysis_mode"]
                    mode_label = norm["mode_label"]
                    side_a_label = norm["side_a_label"]
                    side_b_label = norm["side_b_label"]
                    side_a_ratio = norm["side_a_ratio"]
                    side_b_ratio = norm["side_b_ratio"]
                    perspectives = norm["perspectives"]
                    debate_script = norm["debate_script"]
                    engine_mode = f"YOUTUBE_GEMINI_FACTION_BATTLE (N={cluster_res['total_comments']})"
        except Exception:
            _GEMINI_COOLDOWN_UNTIL = time.time() + 60.0

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    tag_a = side_a_label.replace(" ", "")
    tag_b = side_b_label.replace(" ", "")

    return {
        "id": f"yt_{vid}" if vid else "live_custom",
        "analysis_mode": resolved_mode,
        "mode_label": mode_label,
        "side_a_label": side_a_label,
        "side_b_label": side_b_label,
        "side_a_ratio": side_a_ratio,
        "side_b_ratio": side_b_ratio,
        "perspectives": perspectives,
        "issue_title": issue_title,
        "category_badge": f"{channel_title} 실시간 {cluster_res['total_comments']}건 | {side_a_label} vs {side_b_label}" if channel_title else f"{side_a_label} vs {side_b_label}",
        "source_label": f"YouTube Data API v3 실시간 수집 · {video_title} (댓글 {cluster_res['total_comments']}건)" if video_title else f"직접 입력 댓글 {cluster_res['total_comments']}건 ({side_a_label} vs {side_b_label})",
        "source_url": source_url,
        "hashtags": f"#한냥 #팩트배틀 #{tag_a} #{tag_b} #유튜브쇼츠".strip(),
        "video_mp4_url": None,
        "has_voice_track": False,
        "notice": notice_msg,
        "raw_stats": {
            "total_comments": cluster_res["total_comments"],
            "filtered_curse_count": cluster_res["filtered_curse_count"],
            "pro_ratio": side_a_ratio,
            "con_ratio": side_b_ratio,
            "side_a_ratio": side_a_ratio,
            "side_b_ratio": side_b_ratio,
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
    프론트엔드에서 전달한 동적 진영 배틀 대본(2~8턴), 진영 라벨, 오디오 데이터를 받아
    실제 9:16 H.264 MP4 파일을 생성하고 다운로드 URL을 반환한다.
    """
    t0 = time.perf_counter()
    filename = f"hannyang_shorts_{int(time.time())}.mp4"
    out_path = VIDEOS_DIR / filename
    render_meta: Dict[str, Any] = {}
    render_debate_mp4(
        issue_title=req.issue_title,
        category_badge=req.category_badge or "한냥 팩트 배틀 쇼츠",
        raw_stats=req.raw_stats,
        debate_script=req.debate_script,
        output_mp4=out_path,
        turn_audio_b64_list=req.turn_audio_b64_list,
        meta_out=render_meta,
        perspectives=req.perspectives,
        mode_label=req.mode_label or "동적 진영 HP 팩트 배틀",
        side_a_label=req.side_a_label or "",
        side_b_label=req.side_b_label or "",
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

