#!/usr/bin/env python3
"""코스피200 선물·옵션 만기 캘린더 산출 스크립트.

규칙
- 월물 만기(최종거래일): 매월 둘째 목요일. 휴장일이면 직전 거래일로 앞당김.
- 동시만기: 3·6·9·12월 (선물 + 옵션 + 주식선물·옵션).
- 위클리 옵션: 매주 월요일·목요일 만기. 목요일물은 월물 만기주에는 상장되지 않음.
  (월요일물의 월물 만기주 취급은 KRX 규정 확인 필요 → DESIGN.md '확인 필요' 항목)
- 알림 스케줄: D-6(전주 금요일) 브리핑, D-3~D-1(월·화·수) 일일 추적, D-0 만기일, D+1 리뷰.

사용법
    python3 expiry_calendar.py            # 2026~2027 월물 캘린더 + 향후 8주 위클리
    python3 expiry_calendar.py 2027       # 특정 연도
    python3 expiry_calendar.py --weekly   # 위클리 옵션 날짜만

휴장일 목록은 임시 하드코딩입니다. 운영 단계에서는 KIS '국내휴장일조회' API 또는
KRX 휴장일 안내로 교체합니다(WORKLOG.md 작업 1-3).
"""
import sys
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# 임시 휴장일 (검증 필요). 주말은 자동 처리하므로 평일 휴장일만 적으면 됨.
# ---------------------------------------------------------------------------
HOLIDAYS = {
    # 2026
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 2), date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 25),
    date(2026, 6, 3), date(2026, 8, 17), date(2026, 9, 24), date(2026, 9, 25),
    date(2026, 10, 5), date(2026, 10, 9), date(2026, 12, 25), date(2026, 12, 31),
    # 2027
    date(2027, 1, 1), date(2027, 2, 8), date(2027, 2, 9), date(2027, 3, 1),
    date(2027, 5, 5), date(2027, 5, 13), date(2027, 6, 7), date(2027, 8, 16),
    date(2027, 9, 14), date(2027, 9, 15), date(2027, 9, 16), date(2027, 10, 4),
    date(2027, 10, 11), date(2027, 12, 27), date(2027, 12, 31),
}

QUAD_WITCHING_MONTHS = {3, 6, 9, 12}
WEEKDAY_KO = "월화수목금토일"


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def prev_trading_day(d: date) -> date:
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d: date) -> date:
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def second_thursday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset = (3 - first.weekday()) % 7  # 3 = 목요일
    return first + timedelta(days=offset + 7)


def monthly_expiry(year: int, month: int) -> dict:
    nominal = second_thursday(year, month)
    actual = prev_trading_day(nominal)
    # 전주 금요일: 명목 만기일 기준 6일 전(금요일), 휴장이면 앞당김
    d_minus_6 = prev_trading_day(nominal - timedelta(days=6))
    daily = []
    cur = next_trading_day(nominal - timedelta(days=3))  # 월요일
    while cur < actual:
        daily.append(cur)
        cur = next_trading_day(cur + timedelta(days=1))
    return {
        "nominal": nominal,
        "actual": actual,
        "moved": nominal != actual,
        "quad": month in QUAD_WITCHING_MONTHS,
        "d_minus_6": d_minus_6,
        "daily": daily,
        "d_plus_1": next_trading_day(actual + timedelta(days=1)),
    }


def fmt(d: date) -> str:
    return f"{d.isoformat()}({WEEKDAY_KO[d.weekday()]})"


def print_monthly(years):
    print("| 만기월 | 최종거래일 | 구분 | 전주 금요일 브리핑(D-6) | 일일 추적일 | 사후 리뷰(D+1) |")
    print("|---|---|---|---|---|---|")
    for y in years:
        for m in range(1, 13):
            e = monthly_expiry(y, m)
            kind = "동시만기" if e["quad"] else "옵션 월물"
            if e["moved"]:
                kind += f" ⚠휴장 앞당김({e['nominal'].isoformat()}→)"
            daily = ", ".join(d.strftime("%m-%d") for d in e["daily"])
            print(f"| {y}-{m:02d} | {fmt(e['actual'])} | {kind} | {fmt(e['d_minus_6'])} | {daily} | {fmt(e['d_plus_1'])} |")


def weekly_expiries(start: date, weeks: int):
    """start 이후 weeks주 동안의 위클리 옵션 만기일(월·목) 목록."""
    rows = []
    monthly_days = {monthly_expiry(y, m)["actual"] for y in {start.year, start.year + 1} for m in range(1, 13)}
    monthly_weeks = {d.isocalendar()[:2] for d in monthly_days}
    cur = start
    end = start + timedelta(weeks=weeks)
    while cur <= end:
        if cur.weekday() in (0, 3):  # 월, 목
            week = cur.isocalendar()[:2]
            if cur.weekday() == 3 and week in monthly_weeks:
                rows.append((cur, "월물 만기주: 목요일 위클리 미상장(월물 만기로 대체)"))
            else:
                actual = prev_trading_day(cur)
                note = "월요일물" if cur.weekday() == 0 else "목요일물"
                if actual != cur:
                    note += f" ⚠휴장 앞당김 → {fmt(actual)}"
                if cur.weekday() == 0 and week in monthly_weeks:
                    note += " (월물 만기주 월요일물 취급: KRX 규정 확인 필요)"
                rows.append((cur, note))
        cur += timedelta(days=1)
    return rows


def print_weekly(start: date, weeks: int = 8):
    print(f"| 위클리 만기(명목) | 비고 |")
    print("|---|---|")
    for d, note in weekly_expiries(start, weeks):
        print(f"| {fmt(d)} | {note} |")


if __name__ == "__main__":
    args = sys.argv[1:]
    today = date.today()
    if "--weekly" in args:
        print_weekly(today)
    else:
        years = [int(a) for a in args if a.isdigit()] or [2026, 2027]
        print_monthly(years)
        print()
        print_weekly(today)
