"""
presets_data.py
YouTube Data API v3로 실제 수집한 12개 방송사 뉴스 영상 댓글(총 N = 527건) 기반 실측 프리셋 데이터셋.
- 고정된 '찬반/아나운서/40초' 포맷 폐기 -> '동적 대립 진영(Faction A vs B) HP 팩트 배틀' 스키마 통일
- 모든 프리셋은 side_a_label, side_b_label 및 6턴(A 3턴 / B 3턴) {faction, core_point, text, damage(15~35)} 구조를 따른다.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent
REAL_YT_PATH = BASE_DIR / "data" / "real_youtube_comments.json"

_raw_yt = {}
if REAL_YT_PATH.exists():
    try:
        _raw_yt = json.loads(REAL_YT_PATH.read_text(encoding="utf-8"))
    except Exception:
        _raw_yt = {}


def _get_real_comments_text_list(pid: str, fallback: List[str]) -> List[str]:
    if pid in _raw_yt and _raw_yt[pid].get("comments"):
        return [c["text"] for c in _raw_yt[pid]["comments"] if c.get("text")]
    return fallback


PRESETS: Dict[str, Dict[str, Any]] = {
    "preset_1": {
        "id": "preset_1",
        "button_label": "프리셋 1: 심야 배달 오토바이 소음 (N=200)",
        "category_badge": "YTN·MBC·연합뉴스TV 실측 200건 | 라이더 생계 vs 주민 수면권",
        "source_label": "YouTube Data API v3 실측 수집 · YTN(vNIXiWyXs90), MBC(lt7knjTuuOM), 연합뉴스TV(Cs_A2EcMsto) 댓글 200건",
        "source_url": "https://www.youtube.com/watch?v=vNIXiWyXs90",
        "video_mp4_url": "/static/videos/preset_1.mp4",
        "has_voice_track": True,
        "analysis_mode": "faction_battle",
        "mode_label": "동적 진영 HP 팩트 배틀",
        "issue_title": "심야 배달 오토바이 배기 소음 규제 논란",
        "side_a_label": "라이더 생계 우선파",
        "side_b_label": "주민 수면권 수호파",
        "side_a_ratio": 12,
        "side_b_ratio": 88,
        "perspectives": [
            {"id": "A", "label": "라이더 생계 우선파", "short_label": "라이더 생계 우선파", "ratio": 12, "color": "blue", "keywords": ["생계형", "플랫폼속도", "전기이륜차"]},
            {"id": "B", "label": "주민 수면권 수호파", "short_label": "주민 수면권 수호파", "ratio": 88, "color": "red", "keywords": ["배기소음", "단속강화", "전면번호판"]},
        ],
        "raw_stats": {
            "total_comments": 200,
            "filtered_curse_count": 58,
            "pro_ratio": 12,
            "con_ratio": 88,
            "side_a_ratio": 12,
            "side_b_ratio": 88,
            "toxicity_before": 64.2,
            "toxicity_after": 14.5,
        },
        "debate_script": [
            {
                "faction": "A",
                "core_point": "소수 불법 개조 vs 다수 생계형 라이더",
                "text": "일부 불법 튜닝 잡는다고 밤새 뛰는 생계형 라이더 전체 통행 막는 건 생존권 침해야!",
                "damage": 16,
            },
            {
                "faction": "B",
                "core_point": "새벽 주택가 굉음·수면권 파괴",
                "text": "새벽 두 시에 아파트 울리는 굉음은 소음이 아니라 주민 수면권을 부수는 일상 테러지!",
                "damage": 33,
            },
            {
                "faction": "A",
                "core_point": "배달 시간 쪼개는 플랫폼 구조 문제",
                "text": "배달 지연 패널티로 속도 경쟁 시키는 플랫폼 알고리즘부터 뜯어고치는 게 순서 아니냐!",
                "damage": 15,
            },
            {
                "faction": "B",
                "core_point": "후면 번호판 맹점·단속 도주 방치",
                "text": "뒤에만 번호판 달아놓고 경찰 앞에서 굉음 내며 도망가는데 전면 번호판 의무화가 답이야!",
                "damage": 31,
            },
            {
                "faction": "A",
                "core_point": "무소음 전기 이륜차·교환소 인프라",
                "text": "무조건 과태료만 때릴 게 아니라 전기 오토바이 전환 보조금과 충전 인프라부터 깔아줘야지!",
                "damage": 17,
            },
            {
                "faction": "B",
                "core_point": "밤 11시 주거지 정온 구역 지정",
                "text": "생계 핑계로 남의 건강 망치는 건 선 넘었으니 밤 열한 시 이후 고소음 차량 진입을 막아야 해!",
                "damage": 30,
            },
        ],
        "detox_samples": [
            {
                "faction": "B",
                "faction_label": "주민 수면권 수호파",
                "color": "red",
                "raw": "[실제 댓글 · @user-ytn] 단속 의지도 없으면서 ㄱ ㅐ소리!!! 파출소 배달가는 딸배도 붕붕 거리더라",
                "cleaned": "일선 단속이 겉돌면서 공공기관 근처까지 이륜차 소음이 방치되니 상시 단속부터 강화해야 해.",
                "removed_tokens": ["ㄱ ㅐ소리!!!", "딸배도"],
            },
            {
                "faction": "B",
                "faction_label": "주민 수면권 수호파",
                "color": "red",
                "raw": "[실제 댓글 · 좋아요 53] 강력처벌 해야 합니다..오토바이 자동차 배기음 폭발하는 소리 진짜 살인을 부릅니다.",
                "cleaned": "심야에 기준치를 넘는 폭발적인 배기음은 주민 정신 건강을 해치니까 처벌 수위를 대폭 올려야 해.",
                "removed_tokens": ["살인을 부릅니다"],
            },
            {
                "faction": "B",
                "faction_label": "주민 수면권 수호파",
                "color": "red",
                "raw": "[실제 댓글 · MBC뉴스] 오토바이 소음 단속 백날해봐라 없어지는가....처벌법이 개법인데 그때뿐이지.",
                "cleaned": "일회성 합동 단속만으로는 소음이 안 사라지니까 허용 기준과 처벌 법규 자체를 뜯어고쳐야 해.",
                "removed_tokens": ["백날해봐라", "개법인데"],
            },
            {
                "faction": "A",
                "faction_label": "라이더 생계 우선파",
                "color": "blue",
                "raw": "[실제 댓글 · 연합뉴스TV] 먹고살려고 밤잠 줄여가며 배달 뛰는 기사들까지 싸잡아서 범죄자 취급하네 법 지키는 사람이 더 많다",
                "cleaned": "법 지키는 생계형 배달 기사까지 싸잡아 규제하지 말고 불법 개조 차량만 핀셋으로 잡아내야지.",
                "removed_tokens": ["싸잡아서", "범죄자 취급하네"],
            },
        ],
        "raw_comments": _get_real_comments_text_list("preset_1", [
            "단속 의지도 없으면서 ㄱ ㅐ소리!!! 파출소 배달가는 딸배도 붕붕 거리더라",
            "강력처벌 해야 합니다..오토바이 자동차 배기음 폭발하는 소리 진짜 살인을 부릅니다.",
            "오토바이 소음 단속 백날해봐라 없어지는가....처벌법이 개법인데 그때뿐이지.",
        ]),
    },

    "preset_2": {
        "id": "preset_2",
        "button_label": "프리셋 2: 공유 전동킥보드 방치 (N=180)",
        "category_badge": "MBC·SBS·TBS 실측 180건 | 전면 견인 vs 인프라 확충",
        "source_label": "YouTube Data API v3 실측 수집 · MBC(Xt8TRqMuZRc), SBS(aI0awk0NBfc), TBS(D2hNIe74HEQ) 댓글 180건",
        "source_url": "https://www.youtube.com/watch?v=Xt8TRqMuZRc",
        "video_mp4_url": "/static/videos/preset_2.mp4",
        "has_voice_track": True,
        "analysis_mode": "faction_battle",
        "mode_label": "동적 진영 HP 팩트 배틀",
        "issue_title": "도심 공유 전동킥보드 즉시 견인·금지 논란",
        "side_a_label": "전면 견인 강경파",
        "side_b_label": "인프라 확충 현실파",
        "side_a_ratio": 87,
        "side_b_ratio": 13,
        "perspectives": [
            {"id": "A", "label": "전면 견인 강경파", "short_label": "전면 견인 강경파", "ratio": 87, "color": "blue", "keywords": ["보행안전", "무단방치", "즉시견인"]},
            {"id": "B", "label": "인프라 확충 현실파", "short_label": "인프라 확충 현실파", "ratio": 13, "color": "red", "keywords": ["주차존", "GPS감속", "라스트마일"]},
        ],
        "raw_stats": {
            "total_comments": 180,
            "filtered_curse_count": 32,
            "pro_ratio": 87,
            "con_ratio": 13,
            "side_a_ratio": 87,
            "side_b_ratio": 13,
            "toxicity_before": 61.5,
            "toxicity_after": 14.2,
        },
        "debate_script": [
            {
                "faction": "A",
                "core_point": "인도 무단 방치·유예 없는 즉시 견인",
                "text": "점자블록과 횡단보도에 나뒹구는 킥보드는 보행자 흉기니까 유예 없이 즉시 강제 견인해야 해!",
                "damage": 33,
            },
            {
                "faction": "B",
                "core_point": "전용 주차존 없는 앞뒤 바뀐 단속",
                "text": "반납할 전용 거치대 하나 안 만들어 놓고 무조건 견인료부터 뜯어가는 건 탁상행정 아니냐!",
                "damage": 16,
            },
            {
                "faction": "A",
                "core_point": "업체 수익 독식·사회적 비용 전가",
                "text": "수익은 대여 업체가 챙기고 무면허 사고랑 방치 비용은 시민 세금으로 떠안는 게 말이 되냐!",
                "damage": 31,
            },
            {
                "faction": "B",
                "core_point": "제3자 이동 억울한 견인료·GPS 제어",
                "text": "정상 반납했는데 남이 옮겨놔서 4만 원 덤터기 쓰는 피해 막으려면 지피에스 반납 제한이 먼저야!",
                "damage": 17,
            },
            {
                "faction": "A",
                "core_point": "등록제 폐지·안전 관리 허가제 전환",
                "text": "등록제 틈타서 난립한 업체들 허가제로 싹 조이고 방치 기기 누적되면 영업 정지 때려야 해!",
                "damage": 29,
            },
            {
                "faction": "B",
                "core_point": "단거리 대중교통 공백 메우는 편익",
                "text": "막차 끊긴 대학가나 골목길에선 엄연히 필요한 이동수단이니까 주차존 확충해서 제도권에 둬야지!",
                "damage": 15,
            },
        ],
        "detox_samples": [
            {
                "faction": "A",
                "faction_label": "전면 견인 강경파",
                "color": "blue",
                "raw": "[실제 댓글 · MBC뉴스] 제발 그냥 전동킥보드든 전기자전거든 다 없애라.... 사용자들이 저렇게 개판치고 서로 불편해지는데 왜 있어야 되냐???",
                "cleaned": "무단 방치랑 안전수칙 위반으로 보행 불편이 크니까 공유 킥보드 통행이랑 영업을 강하게 규제해야 해.",
                "removed_tokens": ["다 없애라", "개판치고"],
            },
            {
                "faction": "A",
                "faction_label": "전면 견인 강경파",
                "color": "blue",
                "raw": "[실제 댓글 · 좋아요 29] 도대체 킥보드는 안전문제에 불법주차등 문제투성인데 왜 채택하는거죠? 불법주차하는 사용자에게 책임을 물으세요!!!",
                "cleaned": "보행 안전이랑 보도 질서를 지키려면 불법 주차하고 방치한 이용자에게 직접 과태료를 물려야 해.",
                "removed_tokens": ["문제투성인데", "!!!"],
            },
            {
                "faction": "B",
                "faction_label": "인프라 확충 현실파",
                "color": "red",
                "raw": "[실제 댓글 · 좋아요 19] 킥보드 업체가 주차장소를 만들고 영업을 해야지... 아무 길이나 방치되어 있는 킥보드는 주차 인프라부터 강제해야 한다",
                "cleaned": "무단 방치를 없애려면 대여 업체와 지자체가 전용 주차 공간부터 의무로 확보하게 만들어야지.",
                "removed_tokens": ["아무 길이나"],
            },
            {
                "faction": "B",
                "faction_label": "인프라 확충 현실파",
                "color": "red",
                "raw": "[실제 댓글 · SBS뉴스] 킥보드 타지도 않았는데 번호판도 없으니 누가 옮겨놔도 사용자한테 4만원 덤터기 씌우는 게 말이 되냐 황당하네",
                "cleaned": "남이 기기를 옮겨서 억울하게 견인료 물지 않게 명확한 반납 인증이랑 이의 절차가 먼저 필요해.",
                "removed_tokens": ["덤터기 씌우는", "황당하네"],
            },
        ],
        "raw_comments": _get_real_comments_text_list("preset_2", [
            "제발 그냥 전동킥보드든 전기자전거든 다 없애라.... 사용자들이 저렇게 개판치고 서로 불편해지는데 왜 있어야 되냐???",
            "도대체 킥보드는 안전문제에 불법주차등 문제투성인데 왜 채택하는거죠? 불법주차하는 사용자에게 책임을 물으세요!!!",
        ]),
    },

    "preset_3": {
        "id": "preset_3",
        "button_label": "프리셋 3: 고령 운전자 면허 반납 (N=147)",
        "category_badge": "MBC·KBS·YTN 실측 147건 | 즉각 면허반납 vs 이동권 대안",
        "source_label": "YouTube Data API v3 실측 수집 · MBC(NKIvNrtdiGA), KBS(x3J5hpBci98 외 2건), YTN(yfAshZpECCo) 댓글 147건",
        "source_url": "https://www.youtube.com/watch?v=NKIvNrtdiGA",
        "video_mp4_url": "/static/videos/preset_3.mp4",
        "has_voice_track": True,
        "analysis_mode": "faction_battle",
        "mode_label": "동적 진영 HP 팩트 배틀",
        "issue_title": "고령 운전자 면허 반납 및 실기 검증 논란",
        "side_a_label": "즉각 면허반납파",
        "side_b_label": "이동권 보장 대안파",
        "side_a_ratio": 67,
        "side_b_ratio": 33,
        "perspectives": [
            {"id": "A", "label": "즉각 면허반납파", "short_label": "즉각 면허반납파", "ratio": 67, "color": "blue", "keywords": ["페달오조작", "면허반납", "실기시험"]},
            {"id": "B", "label": "이동권 보장 대안파", "short_label": "이동권 보장 대안파", "ratio": 33, "color": "red", "keywords": ["농어촌이동권", "10만원한계", "오조작방지"]},
        ],
        "raw_stats": {
            "total_comments": 147,
            "filtered_curse_count": 36,
            "pro_ratio": 67,
            "con_ratio": 33,
            "side_a_ratio": 67,
            "side_b_ratio": 33,
            "toxicity_before": 62.4,
            "toxicity_after": 14.5,
        },
        "debate_script": [
            {
                "faction": "A",
                "core_point": "급발진 주장·페달 오조작 인명피해",
                "text": "돌발 상황 반응속도 떨어져서 대형 사고 잇따르는데 형식적인 적성검사 치우고 면허부터 거둬야 해!",
                "damage": 30,
            },
            {
                "faction": "B",
                "core_point": "버스 없는 시골·일회성 10만 원 카드",
                "text": "버스도 없는 농어촌에 10만 원짜리 카드 한 장 쥐여주고 면허 내놓으라는 건 발 묶으란 소리야!",
                "damage": 21,
            },
            {
                "faction": "A",
                "core_point": "정기 실주행 시험·조건부 야간 제한",
                "text": "고속도로랑 야간 주행만이라도 바로 제한하고 실제 도로 실기시험 통과 못 하면 자격을 회수해야지!",
                "damage": 28,
            },
            {
                "faction": "B",
                "core_point": "연령 차별 대신 오조작 방지 보조장치",
                "text": "나이로 딱 잘라 뺏지 말고 페달 오조작 방지 센서랑 긴급 제동 장치 보조금부터 다는 게 현실적이지!",
                "damage": 19,
            },
            {
                "faction": "A",
                "core_point": "타인의 생명권·생계보다 앞서는 공익",
                "text": "본인 생계랑 편의를 위해 도로 위 불특정 다수 목숨을 담보로 잡는 건 어떤 이유로도 정당화 못 해!",
                "damage": 29,
            },
            {
                "faction": "B",
                "core_point": "수요응답형 복지택시·개인 역량 평가",
                "text": "호출형 복지 택시 먼저 깔아주고 나이가 아니라 실제 주행 데이터와 건강 상태로 판단하는 게 맞아!",
                "damage": 18,
            },
        ],
        "detox_samples": [
            {
                "faction": "A",
                "faction_label": "즉각 면허반납파",
                "color": "blue",
                "raw": "[실제 댓글 · MBC뉴스] 오늘 운전하다가 미친각으로 끼어드는 차 있어서 욕하고 넘어갔는데 70대 할머니더라 본인이 민폐라 생각하면 면허 반납 좀 해라",
                "cleaned": "고령으로 시야랑 반응속도가 떨어져 위험 주행이 잦아지면 도로 안전을 위해 면허 반납이 필요해.",
                "removed_tokens": ["미친각으로", "욕하고", "민폐라"],
            },
            {
                "faction": "A",
                "faction_label": "즉각 면허반납파",
                "color": "blue",
                "raw": "[실제 댓글 · KBS뉴스] 솔직히 도로에 나가보면 말도안되게 운전하는 사람들 나이 많으신분들이 대다수 본인 먹고 살겠다고 남한테 피해주면 안되지 정기 시험 봐라!!",
                "cleaned": "생계 목적이라도 타인 안전을 위협하면 안 되니까 고령 운전자 정기 실기시험을 의무화해야 해.",
                "removed_tokens": ["말도안되게", "!!"],
            },
            {
                "faction": "B",
                "faction_label": "이동권 보장 대안파",
                "color": "red",
                "raw": "[실제 댓글 · MBC뉴스] 면허 반납하면 10만원 카드 한 장 달랑 주면서 반납하라고 하는 게 코미디지 시골은 버스도 없는데 걸어 다니란 소리냐",
                "cleaned": "대중교통 없는 지역 현실을 무시한 일회성 10만 원 지원 대신 지속적인 대체 이동수단부터 마련해야지.",
                "removed_tokens": ["달랑 주면서", "코미디지"],
            },
            {
                "faction": "B",
                "faction_label": "이동권 보장 대안파",
                "color": "red",
                "raw": "[실제 댓글 · YTN뉴스] 나이로만 딱 잘라서 면허 뺏는 건 차별이다 젊은 사람 음주운전 난폭운전이 더 위험한데 운전 능력으로만 평가해야 맞지",
                "cleaned": "연령 기준 획일 규제 대신 오조작 방지 장치랑 객관적 개인별 실주행 능력 평가로 걸러내야 맞아.",
                "removed_tokens": ["딱 잘라서", "면허 뺏는"],
            },
        ],
        "raw_comments": _get_real_comments_text_list("preset_3", [
            "오늘 운전하다가 미친각으로 끼어드는 차 있어서 욕하고 넘어갔는데 70대 할머니더라 본인이 민폐라 생각하면 면허 반납 좀 해라",
            "솔직히 도로에 나가보면 말도안되게 운전하는 사람들 나이 많으신분들이 대다수 본인 먹고 살겠다고 남한테 피해주면 안되지 정기 시험 봐라!!",
        ]),
    },
}
