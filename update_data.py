#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
广期所仓单数据自动更新脚本
- 最新日度注册/注销/净变化
- 周度、月度累计净变化（约 5 / 20 个交易日回溯）
- 分仓库日/周/月变化
- 保留 history 用于多年同期对比图
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path


def get_gfex_data(date_str: str) -> dict:
    url = "http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://www.gfex.com.cn",
    }
    resp = requests.post(url, data={"gen_date": date_str}, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def process_data(raw: dict) -> dict | None:
    if raw.get("code") != "0" or not raw.get("data"):
        return None

    targets = {}
    details = {}
    for item in raw["data"]:
        variety = item.get("variety", "")
        order = (item.get("varietyOrder") or "").lower()
        if "小计" in variety and order in ("lc", "ps", "si"):
            targets[order] = {
                "variety": variety.replace("小计", ""),
                "code": order.upper(),
                "lastWbillQty": int(item.get("lastWbillQty") or 0),
                "regWbillQty": int(item.get("regWbillQty") or 0),
                "logoutWbillQty": int(item.get("logoutWbillQty") or 0),
                "wbillQty": int(item.get("wbillQty") or 0),
                "diff": int(item.get("diff") or 0),
            }
        elif order in ("lc", "ps", "si") and item.get("whAbbr"):
            details.setdefault(order, []).append({
                "warehouse": item.get("whAbbr") or "",
                "trademark": (item.get("trademarkName") or "").strip(),
                "last": int(item.get("lastWbillQty") or 0),
                "reg": int(item.get("regWbillQty") or 0),
                "logout": int(item.get("logoutWbillQty") or 0),
                "today": int(item.get("wbillQty") or 0),
                "diff": int(item.get("diff") or 0),
            })
    if not targets:
        return None
    return {"summary": targets, "details": details}


def fmt_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def main():
    script_dir = Path(__file__).parent
    out_path = script_dir / "data.json"

    # 保留旧 history
    old_history = []
    if out_path.exists():
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
            old_history = old.get("history") or []
        except Exception:
            pass

    today = datetime.now()
    snaps = []  # (date_raw, processed)

    for i in range(0, 40):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            raw = get_gfex_data(d)
            processed = process_data(raw)
            if processed:
                snaps.append((d, processed))
                if len(snaps) >= 22:
                    break
        except Exception as e:
            print(f"[跳过] {d}: {e}")
            continue

    if not snaps:
        print("错误：未能获取到有效仓单数据")
        return 1

    latest_d, latest = snaps[0]
    week_d, week = snaps[min(5, len(snaps) - 1)]
    month_d, month = snaps[min(20, len(snaps) - 1)]

    summary = {}
    for code in ("lc", "ps", "si"):
        if code not in latest["summary"]:
            continue
        s = dict(latest["summary"][code])
        w_qty = week["summary"].get(code, {}).get("wbillQty", s["wbillQty"])
        m_qty = month["summary"].get(code, {}).get("wbillQty", s["wbillQty"])
        s["weekDiff"] = s["wbillQty"] - w_qty
        s["monthDiff"] = s["wbillQty"] - m_qty
        s["weekBaseDate"] = fmt_date(week_d)
        s["monthBaseDate"] = fmt_date(month_d)
        summary[code] = s

    def row_key(wh):
        return (wh.get("warehouse") or "", wh.get("trademark") or "")

    details = {}
    for code in ("lc", "ps", "si"):
        week_map = {row_key(x): x["today"] for x in week["details"].get(code, [])}
        month_map = {row_key(x): x["today"] for x in month["details"].get(code, [])}
        rows = []
        for wh in latest["details"].get(code, []):
            k = row_key(wh)
            w_base = week_map.get(k)
            m_base = month_map.get(k)
            week_diff = (wh["today"] - w_base) if w_base is not None else wh["today"]
            month_diff = (wh["today"] - m_base) if m_base is not None else wh["today"]
            rows.append({**wh, "weekDiff": week_diff, "monthDiff": month_diff})
        details[code] = rows

    # 更新 history：追加最新一天汇总
    hist_map = {h["date"]: h for h in old_history}
    hist_map[fmt_date(latest_d)] = {
        "date": fmt_date(latest_d),
        "lc": summary.get("lc", {}).get("wbillQty", 0),
        "ps": summary.get("ps", {}).get("wbillQty", 0),
        "si": summary.get("si", {}).get("wbillQty", 0),
    }
    history = sorted(hist_map.values(), key=lambda x: x["date"])

    day_snap = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date": fmt_date(latest_d),
        "data_date_raw": latest_d,
        "week_base_date": fmt_date(week_d),
        "month_base_date": fmt_date(month_d),
        "summary": summary,
        "details": details,
        "source": "广州期货交易所 仓单日报 http://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml",
    }

    days_dir = script_dir / "days"
    days_dir.mkdir(exist_ok=True)
    (days_dir / f"{latest_d}.json").write_text(
        json.dumps(day_snap, ensure_ascii=False), encoding="utf-8"
    )

    # 维护可浏览日期列表与 days-all 缓存（供页面日期选择）
    available = set()
    for p in days_dir.glob("*.json"):
        available.add(f"{p.stem[:4]}-{p.stem[4:6]}-{p.stem[6:8]}")
    available.add(fmt_date(latest_d))
    available_list = sorted(available, reverse=True)
    (script_dir / "available_dates.json").write_text(
        json.dumps(available_list, ensure_ascii=False), encoding="utf-8"
    )

    all_days = {}
    all_path = script_dir / "days-all.json"
    if all_path.exists():
        try:
            all_days = json.loads(all_path.read_text(encoding="utf-8"))
        except Exception:
            all_days = {}
    all_days[fmt_date(latest_d)] = day_snap
    all_path.write_text(json.dumps(all_days, ensure_ascii=False), encoding="utf-8")

    result = {
        **day_snap,
        "history": history,
        "available_dates": available_list,
    }

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已更新 data.json （数据日期: {latest_d}）")
    print(f"   周基准: {week_d}  月基准: {month_d}")
    print(f"   可浏览日期: {len(available_list)} 天（已写入 days/{latest_d}.json）")
    for code, s in result["summary"].items():
        print(
            f"  {s['variety']}({s['code']}): "
            f"日 {s['diff']:+d} | 周 {s['weekDiff']:+d} | 月 {s['monthDiff']:+d} | "
            f"今日仓单 {s['wbillQty']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
