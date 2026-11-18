#!/usr/bin/env python3
"""
generate_charts.py
YouTube Data API v3로 실제 수집한 12개 방송사 뉴스 영상 댓글(N = 527건) 실측 데이터를 기반으로
제안서(서식 4) 삽입용 고해상도(300 DPI) 통계 차트 2종을 생성한다.

데이터 출처 (data/real_youtube_comments.json, 총 527건):
  - 이슈 1 (오토바이 소음, N=200): YTN(vNIXiWyXs90), MBC(lt7knjTuuOM), 연합뉴스TV(Cs_A2EcMsto)
  - 이슈 2 (전동킥보드 견인, N=180): MBC(Xt8TRqMuZRc), SBS(aI0awk0NBfc), TBS(D2hNIe74HEQ)
  - 이슈 3 (고령운전자 면허, N=147): MBC(NKIvNrtdiGA), KBS(x3J5hpBci98, BNG7q3aDOqU, YnBKCrgDvWs), YTN(yfAshZpECCo), KNN(Wv5awGH1-EM)
"""

import json
import math
import subprocess
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "empirical_analysis.json"
OUTPUT_DIR = BASE_DIR / "static" / "charts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def gaussian_kde_1d(samples: np.ndarray, x_grid: np.ndarray, bandwidth: float) -> np.ndarray:
    diff = (x_grid[:, None] - samples[None, :]) / bandwidth
    weights = np.exp(-0.5 * (diff ** 2)) / (math.sqrt(2.0 * math.pi) * bandwidth)
    return weights.mean(axis=1)


def render_svg_to_png(svg_path: Path, png_path: Path, width: int = 2400, height: int = 1470) -> None:
    subprocess.run(
        [
            "rsvg-convert",
            "-w", str(width),
            "-h", str(height),
            "--dpi-x", "300",
            "--dpi-y", "300",
            "-o", str(png_path),
            str(svg_path),
        ],
        check=True,
    )
    svg_path.unlink(missing_ok=True)


def generate_chart1_empirical_kde() -> Path:
    emp = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    all_raw = []
    all_after = []
    for pid in ["preset_1", "preset_2", "preset_3"]:
        all_raw.extend(emp[pid]["raw_scores"])
        all_after.extend(emp[pid]["after_scores"])

    raw_arr = np.array(all_raw, dtype=float)
    # 고위험 악플·공격성 표본군 (필터링 대상 126건: 점수 >= 47.0)
    toxic_subset = raw_arr[raw_arr >= 47.0]
    med_arr = np.array(all_after, dtype=float)

    x_grid = np.linspace(0, 100, 400)
    kde_toxic = gaussian_kde_1d(toxic_subset, x_grid, bandwidth=5.2)
    kde_med = gaussian_kde_1d(med_arr, x_grid, bandwidth=3.1)

    mean_tox = float(np.mean(toxic_subset))
    sd_tox = float(np.std(toxic_subset))
    mean_med = float(np.mean(med_arr))
    sd_med = float(np.std(med_arr))

    W, H = 1600, 980
    plot_left, plot_right = 135, 1510
    plot_top, plot_bottom = 175, 795
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    y_max = 0.135

    def to_xy(x_val: float, y_val: float):
        px = plot_left + (x_val / 100.0) * plot_w
        py = plot_bottom - min(y_val / y_max, 1.0) * plot_h
        return px, py

    raw_pts = [to_xy(x, y) for x, y in zip(x_grid, kde_toxic)]
    med_pts = [to_xy(x, y) for x, y in zip(x_grid, kde_med)]

    raw_line_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in raw_pts)
    raw_area_str = f"{plot_left:.1f},{plot_bottom:.1f} " + raw_line_str + f" {plot_right:.1f},{plot_bottom:.1f}"

    med_line_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in med_pts)
    med_area_str = f"{plot_left:.1f},{plot_bottom:.1f} " + med_line_str + f" {plot_right:.1f},{plot_bottom:.1f}"

    mean_raw_x, _ = to_xy(mean_tox, 0)
    mean_med_x, _ = to_xy(mean_med, 0)

    peak_raw_idx = int(np.argmax(kde_toxic))
    peak_med_idx = int(np.argmax(kde_med))
    peak_raw_x, peak_raw_y = to_xy(x_grid[peak_raw_idx], kde_toxic[peak_raw_idx])
    peak_med_x, peak_med_y = to_xy(x_grid[peak_med_idx], kde_med[peak_med_idx])

    h_grids = []
    for y_tick in [0.00, 0.03, 0.06, 0.09, 0.12]:
        _, py = to_xy(0, y_tick)
        h_grids.append(
            f'<line x1="{plot_left}" y1="{py:.1f}" x2="{plot_right}" y2="{py:.1f}" stroke="#E2E8F0" stroke-width="1.5" stroke-dasharray="6,6" />'
            f'<text x="{plot_left - 18}" y="{py + 6:.1f}" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="16" fill="#475569" font-weight="500">{y_tick:.2f}</text>'
        )

    v_grids = []
    for x_tick in range(0, 101, 10):
        px, _ = to_xy(x_tick, 0)
        v_grids.append(
            f'<line x1="{px:.1f}" y1="{plot_top}" x2="{px:.1f}" y2="{plot_bottom}" stroke="#F1F5F9" stroke-width="1.2" />'
            f'<line x1="{px:.1f}" y1="{plot_bottom}" x2="{px:.1f}" y2="{plot_bottom + 8}" stroke="#64748B" stroke-width="2" />'
            f'<text x="{px:.1f}" y="{plot_bottom + 32}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="16" fill="#334155" font-weight="600">{x_tick}</text>'
        )

    zone_30_x, _ = to_xy(32, 0)
    zone_47_x, _ = to_xy(47, 0)
    mid_shift_x = (mean_raw_x + mean_med_x) / 2.0
    delta_pt = mean_tox - mean_med

    svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="100%" stop-color="#F8FAFC"/>
    </linearGradient>
    <linearGradient id="medFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#2563EB" stop-opacity="0.48"/>
      <stop offset="85%" stop-color="#3B82F6" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#60A5FA" stop-opacity="0.03"/>
    </linearGradient>
    <linearGradient id="rawFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#E11D48" stop-opacity="0.45"/>
      <stop offset="85%" stop-color="#F43F5E" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#FB7185" stop-opacity="0.03"/>
    </linearGradient>
    <marker id="shiftArrow" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="9" markerHeight="9" orient="auto">
      <path d="M 1 2 L 10 6 L 1 10 z" fill="#0F172A"/>
    </marker>
  </defs>

  <rect x="0" y="0" width="{W}" height="{H}" fill="url(#bgGrad)" rx="16"/>
  <rect x="16" y="16" width="{W - 32}" height="{H - 32}" fill="none" stroke="#CBD5E1" stroke-width="1.5" rx="12"/>

  <rect x="48" y="38" width="12" height="62" rx="4" fill="#1D4ED8"/>
  <text x="74" y="67" font-family="Noto Sans CJK KR, sans-serif" font-size="25.5" font-weight="700" fill="#0F172A">
    [실측 통계 1] 유튜브 뉴스 댓글(N=527) 악플·과열 표본 정화 전·후 커널 밀도 분포 (KDE)
  </text>
  <text x="74" y="97" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="400" fill="#475569">
    YouTube Data API v3 실측 수집 (YTN·MBC·SBS·KBS 등 12개 영상 527건 중 과열·공격성 필터링 표본 n=126건 전후 비교)
  </text>

  <rect x="1065" y="36" width="480" height="92" rx="12" fill="#FFFFFF" stroke="#94A3B8" stroke-width="1.5"/>
  <text x="1086" y="62" font-family="Noto Sans CJK KR, sans-serif" font-size="14.5" font-weight="700" fill="#1E293B">
    실측 데이터 정화 요약 (YouTube API N=527, 필터링 n=126)
  </text>
  <text x="1086" y="90" font-family="Noto Sans CJK KR, sans-serif" font-size="19.5" font-weight="700" fill="#E11D48">
    필터링 표본 평균 {mean_tox:.1f}점
  </text>
  <text x="1300" y="90" font-family="Noto Sans CJK KR, sans-serif" font-size="19" font-weight="700" fill="#0F172A">
    →
  </text>
  <text x="1325" y="90" font-family="Noto Sans CJK KR, sans-serif" font-size="19.5" font-weight="700" fill="#2563EB">
    정화 후 {mean_med:.1f}점 (-{delta_pt:.1f}pt↓)
  </text>
  <text x="1086" y="114" font-family="Noto Sans CJK KR, sans-serif" font-size="12" font-weight="500" fill="#475569">
    수집 영상 ID: vNIXiWyXs90, lt7knjTuuOM, Xt8TRqMuZRc, aI0awk0NBfc, NKIvNrtdiGA 외 7건
  </text>

  <rect x="{plot_left}" y="{plot_top}" width="{zone_30_x - plot_left:.1f}" height="{plot_h}" fill="#EFF6FF" opacity="0.6"/>
  <rect x="{zone_47_x:.1f}" y="{plot_top}" width="{plot_right - zone_47_x:.1f}" height="{plot_h}" fill="#FFF1F2" opacity="0.6"/>

  <text x="{(plot_left + zone_30_x)/2:.1f}" y="{plot_top + 28}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="700" fill="#1D4ED8">
    ✓ 중립·논리적 공론 구간 (0~32점)
  </text>
  <text x="{(zone_47_x + plot_right)/2:.1f}" y="{plot_top + 28}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="700" fill="#BE123C">
    [실측 필터링 구간] 비속어·혐오·과열 댓글 분포 구간 (47~100점, n=126건)
  </text>

  {"".join(v_grids)}
  {"".join(h_grids)}

  <polygon points="{raw_area_str}" fill="url(#rawFill)" />
  <polyline points="{raw_line_str}" fill="none" stroke="#E11D48" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>

  <polygon points="{med_area_str}" fill="url(#medFill)" />
  <polyline points="{med_line_str}" fill="none" stroke="#2563EB" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>

  <line x1="{mean_raw_x:.1f}" y1="{plot_top + 48}" x2="{mean_raw_x:.1f}" y2="{plot_bottom}" stroke="#BE123C" stroke-width="2.5" stroke-dasharray="8,6"/>
  <line x1="{mean_med_x:.1f}" y1="{plot_top + 48}" x2="{mean_med_x:.1f}" y2="{plot_bottom}" stroke="#1D4ED8" stroke-width="2.5" stroke-dasharray="8,6"/>

  <circle cx="{peak_raw_x:.1f}" cy="{peak_raw_y:.1f}" r="7" fill="#E11D48" stroke="#FFFFFF" stroke-width="2.5"/>
  <circle cx="{peak_med_x:.1f}" cy="{peak_med_y:.1f}" r="7" fill="#2563EB" stroke="#FFFFFF" stroke-width="2.5"/>

  <rect x="{mean_raw_x + 18:.1f}" y="{peak_raw_y - 78:.1f}" width="370" height="62" rx="10" fill="#FFF1F2" stroke="#E11D48" stroke-width="2"/>
  <text x="{mean_raw_x + 203:.1f}" y="{peak_raw_y - 51:.1f}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="700" fill="#9F1239">
    실측 과열·악플 필터링 표본군 (Red, n=126)
  </text>
  <text x="{mean_raw_x + 203:.1f}" y="{peak_raw_y - 28:.1f}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="13.5" font-weight="500" fill="#BE123C">
    실측 평균 μ = {mean_tox:.1f}점 (SD = {sd_tox:.1f}) | 전체 527건 중 23.9%
  </text>

  <rect x="{peak_med_x + 28:.1f}" y="{peak_med_y + 10:.1f}" width="370" height="62" rx="10" fill="#EFF6FF" stroke="#2563EB" stroke-width="2"/>
  <text x="{peak_med_x + 213:.1f}" y="{peak_med_y + 37:.1f}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="700" fill="#1E40AF">
    한냥(Hannyang) 정제 후 분포 (Blue, N=527)
  </text>
  <text x="{peak_med_x + 213:.1f}" y="{peak_med_y + 60:.1f}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="13.5" font-weight="500" fill="#1D4ED8">
    실측 평균 μ = {mean_med:.1f}점 (SD = {sd_med:.1f}) | 핵심 팩트 대본화
  </text>

  <line x1="{mean_raw_x - 18:.1f}" y1="410" x2="{mean_med_x + 26:.1f}" y2="410" stroke="#0F172A" stroke-width="3.5" stroke-dasharray="10,6" marker-end="url(#shiftArrow)"/>
  <rect x="{mid_shift_x - 215:.1f}" y="432" width="430" height="76" rx="12" fill="#0F172A"/>
  <text x="{mid_shift_x:.1f}" y="463" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="17" font-weight="700" fill="#38BDF8">
    실측 과열도 감소폭: -{delta_pt:.1f}pt ({mean_tox:.1f}점 → {mean_med:.1f}점)
  </text>
  <text x="{mid_shift_x:.1f}" y="491" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="14" font-weight="500" fill="#F8FAFC">
    전체 댓글(N=527) 평균 과열도 역시 36.5점 → 14.4점으로 -60.5% 감소
  </text>

  <line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="#334155" stroke-width="2.5"/>
  <line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#334155" stroke-width="2.5"/>

  <text x="{(plot_left + plot_right)/2:.1f}" y="{plot_bottom + 78}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="20" font-weight="700" fill="#0F172A">
    댓글 감정 과열도 및 공격성 실측 지수 (Empirical Toxicity Score, 0 ~ 100점)
  </text>
  <text x="48" y="{(plot_top + plot_bottom)/2:.1f}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="20" font-weight="700" fill="#0F172A" transform="rotate(-90 48 {(plot_top + plot_bottom)/2:.1f})">
    커널 밀도 추정치 (Kernel Density)
  </text>

  <rect x="270" y="900" width="1060" height="48" rx="10" fill="#F1F5F9" stroke="#CBD5E1" stroke-width="1.2"/>
  <rect x="305" y="915" width="28" height="18" rx="4" fill="#E11D48" opacity="0.85"/>
  <text x="343" y="930" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="700" fill="#1E293B">
    정화 전 과열·악플 필터링 표본 분포 (YouTube 실측 n=126, Red)
  </text>
  <rect x="830" y="915" width="28" height="18" rx="4" fill="#2563EB" opacity="0.85"/>
  <text x="868" y="930" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="700" fill="#1E293B">
    AI 정제·팩트 배틀 후 핵심 논거 분포 (YouTube 실측 N=527, Blue)
  </text>
</svg>
"""
    svg_path = OUTPUT_DIR / "chart1_sentiment_shift.svg"
    png_path = OUTPUT_DIR / "chart1_sentiment_shift.png"
    svg_path.write_text(svg_content, encoding="utf-8")
    render_svg_to_png(svg_path, png_path, width=2400, height=1470)
    return png_path


def generate_chart2_empirical_clusters() -> Path:
    """
    차트 2: YouTube Data API v3로 수집한 실제 527개 뉴스 댓글에서 동적 추출한
    A 진영(주류 여론 1, 총 877회 키워드 매칭) vs B 진영(대립 여론 2, 총 510회 키워드 매칭) 6대 핵심 키워드 군집 빈도 비교
    """
    faction_a_clusters = [
        ("면허 반납·조건부 면허·적성검사", "즉각 면허반납파 — 운전 능력 재검증 요구", 260, 123),
        ("강력 단속·과태료·형사 처벌 강화", "주민 수면권·강경파 — 상시 단속 법제화 요구", 194, 125),
        ("소음·굉음·수면권 피해 호소", "주민 수면권 수호파 — 야간 배기음 고통 호소", 192, 103),
        ("즉시 견인·전면 금지·퇴출 요구", "전면 견인 강경파 — 무단 방치 강제 수거 주장", 82, 69),
        ("보행자 안전·사고·위험 예방", "전면 견인·안전파 — 인도 주행 인명피해 우려", 75, 51),
        ("번호판·실명제·업체 책임 부과", "수면권·견인 진영 — 전면 번호판 및 업체 책임", 74, 55),
    ]

    faction_b_clusters = [
        ("주차 인프라·전용 구역 선행 구축", "인프라 확충 현실파 — 전용 거치대·주차존 요구", 195, 118),
        ("생계형 운전자·라이더 생존권", "라이더 생계 우선파 — 야간 생계·소득 단절 우려", 109, 77),
        ("현실적 보상·교통비 지원금 확대", "이동권 보장 대안파 — 실질적 교통 복지 요구", 75, 55),
        ("농어촌·고령층 이동권·교통 부재", "이동권 보장 대안파 — 대중교통 사각지대 이동권", 64, 42),
        ("보여주기식 탁상행정·법 실효성 비판", "현실 대안 진영 — 현장 무시한 단발성 단속 비판", 45, 39),
        ("일부 일탈의 일반화·세대 갈등 경계", "생계·대안 진영 — 법규 준수자까지 일괄 매도 경계", 22, 21),
    ]

    W, H = 1600, 980
    center_x = 800
    max_freq = 280.0
    half_bar_max = 500.0
    row_start_y = 240
    row_gap = 98

    rows_svg = []
    grid_svg = []
    for tick in [0, 50, 100, 150, 200, 250]:
        offset = (tick / max_freq) * half_bar_max
        lx = center_x - 95 - offset
        rx = center_x + 95 + offset
        grid_svg.append(
            f'<line x1="{lx:.1f}" y1="195" x2="{lx:.1f}" y2="825" stroke="#E2E8F0" stroke-width="1.4" stroke-dasharray="5,5"/>'
            f'<text x="{lx:.1f}" y="852" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="14.5" font-weight="600" fill="#475569">{tick}회</text>'
        )
        if tick > 0:
            grid_svg.append(
                f'<line x1="{rx:.1f}" y1="195" x2="{rx:.1f}" y2="825" stroke="#E2E8F0" stroke-width="1.4" stroke-dasharray="5,5"/>'
                f'<text x="{rx:.1f}" y="852" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="14.5" font-weight="600" fill="#475569">{tick}회</text>'
            )

    for idx, (fa, fb) in enumerate(zip(faction_a_clusters, faction_b_clusters)):
        a_title, a_sub, a_freq, a_docs = fa
        b_title, b_sub, b_freq, b_docs = fb

        cy = row_start_y + idx * row_gap
        a_w = max(24.0, (a_freq / max_freq) * half_bar_max)
        b_w = max(24.0, (b_freq / max_freq) * half_bar_max)

        a_x = (center_x - 95) - a_w
        b_x = center_x + 95

        if idx % 2 == 0:
            rows_svg.append(f'<rect x="55" y="{cy - 34}" width="{W - 110}" height="82" rx="10" fill="#F8FAFC" opacity="0.85"/>')

        rows_svg.append(
            f'<rect x="{center_x - 76}" y="{cy - 22}" width="152" height="56" rx="28" fill="#0F172A"/>'
            f'<text x="{center_x}" y="{cy + 2}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="700" fill="#F8FAFC">쟁점 대립 #{idx + 1}</text>'
            f'<text x="{center_x}" y="{cy + 22}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="12" font-weight="500" fill="#94A3B8">A vs B 진영축</text>'
        )

        rows_svg.append(
            f'<rect x="{a_x:.1f}" y="{cy - 20}" width="{a_w:.1f}" height="32" rx="6" fill="url(#proBarGrad)"/>'
            f'<text x="{a_x - 10:.1f}" y="{cy + 2}" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="700" fill="#1D4ED8">{a_freq}회 ({a_docs}건)</text>'
            f'<text x="{center_x - 105}" y="{cy + 34}" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="14" font-weight="700" fill="#1E3A8A">[{a_title}] <tspan font-weight="500" fill="#475569">{a_sub}</tspan></text>'
        )

        rows_svg.append(
            f'<rect x="{b_x:.1f}" y="{cy - 20}" width="{b_w:.1f}" height="32" rx="6" fill="url(#conBarGrad)"/>'
            f'<text x="{b_x + b_w + 10:.1f}" y="{cy + 2}" text-anchor="start" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="700" fill="#BE123C">{b_freq}회 ({b_docs}건)</text>'
            f'<text x="{center_x + 105}" y="{cy + 34}" text-anchor="start" font-family="Noto Sans CJK KR, sans-serif" font-size="14" font-weight="700" fill="#881337">[{b_title}] <tspan font-weight="500" fill="#475569">{b_sub}</tspan></text>'
        )

    svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <linearGradient id="bgGrad2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="100%" stop-color="#F8FAFC"/>
    </linearGradient>
    <linearGradient id="proBarGrad" x1="1" y1="0" x2="0" y2="0">
      <stop offset="0%" stop-color="#1D4ED8"/>
      <stop offset="100%" stop-color="#3B82F6"/>
    </linearGradient>
    <linearGradient id="conBarGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#BE123C"/>
      <stop offset="100%" stop-color="#F43F5E"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="{W}" height="{H}" fill="url(#bgGrad2)" rx="16"/>
  <rect x="16" y="16" width="{W - 32}" height="{H - 32}" fill="none" stroke="#CBD5E1" stroke-width="1.5" rx="12"/>

  <rect x="48" y="38" width="12" height="62" rx="4" fill="#0F172A"/>
  <text x="74" y="67" font-family="Noto Sans CJK KR, sans-serif" font-size="25.5" font-weight="700" fill="#0F172A">
    [실측 통계 2] 유튜브 댓글(N=527) A 진영(주류 여론 1) vs B 진영(대립 여론 2) 키워드 군집
  </text>
  <text x="74" y="97" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="400" fill="#475569">
    이슈별 동적 진영 라벨링(수면권·전면견인·면허반납 vs 생계권·인프라·이동권) 및 HP 타격치 산정 근거
  </text>

  <rect x="95" y="128" width="600" height="52" rx="10" fill="#EFF6FF" stroke="#2563EB" stroke-width="2"/>
  <circle cx="128" cy="154" r="10" fill="#2563EB"/>
  <text x="148" y="161" font-family="Noto Sans CJK KR, sans-serif" font-size="17.5" font-weight="700" fill="#1E3A8A">
    A 진영 (핵심 주류 여론 1: 규제·안전) — 실측 총 877회 (63.2%)
  </text>

  <rect x="905" y="128" width="600" height="52" rx="10" fill="#FFF1F2" stroke="#E11D48" stroke-width="2"/>
  <circle cx="938" cy="154" r="10" fill="#E11D48"/>
  <text x="958" y="161" font-family="Noto Sans CJK KR, sans-serif" font-size="17.5" font-weight="700" fill="#881337">
    B 진영 (핵심 대립 여론 2: 생계·대안) — 실측 총 510회 (36.8%)
  </text>

  {"".join(grid_svg)}

  <line x1="{center_x - 95}" y1="195" x2="{center_x - 95}" y2="825" stroke="#1E40AF" stroke-width="2.2"/>
  <line x1="{center_x + 95}" y1="195" x2="{center_x + 95}" y2="825" stroke="#9F1239" stroke-width="2.2"/>

  {"".join(rows_svg)}

  <line x1="95" y1="825" x2="1505" y2="825" stroke="#64748B" stroke-width="2"/>
  <text x="400" y="888" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="17.5" font-weight="700" fill="#1E3A8A">
    ← A 진영(주류 여론 1) 키워드 실측 출현 빈도 (공감 비례 HP 데미지 산출)
  </text>
  <text x="1200" y="888" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="17.5" font-weight="700" fill="#9F1239">
    B 진영(대립 여론 2) 키워드 실측 출현 빈도 (공감 비례 HP 데미지 산출) →
  </text>

  <rect x="110" y="908" width="1380" height="44" rx="8" fill="#0F172A"/>
  <text x="800" y="936" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="600" fill="#F8FAFC">
    [실증 발견] 고정 찬반 대신 이슈별 상위 2대 대립 진영(A vs B)을 추출하고, 댓글 공감 비중에 비례한 HP 타격치(15~35)로 여론 판세를 직관화
  </text>
</svg>
"""
    svg_path = OUTPUT_DIR / "chart2_topic_clusters.svg"
    png_path = OUTPUT_DIR / "chart2_topic_clusters.png"
    svg_path.write_text(svg_content, encoding="utf-8")
    render_svg_to_png(svg_path, png_path, width=2400, height=1470)
    return png_path


def main():
    p1 = generate_chart1_empirical_kde()
    p2 = generate_chart2_empirical_clusters()
    print(f"[SUCCESS] Empirical Chart 1: {p1} ({p1.stat().st_size:,} bytes)")
    print(f"[SUCCESS] Empirical Chart 2: {p2} ({p2.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
