#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
广期所仓单数据自动更新脚本
每日运行此脚本可更新 data.json，配合静态网站实现自动更新。
建议使用 cron 或 GitHub Actions 每日 17:30 后执行。
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
                "regWbillQty": int(item.get("regWbillQty") or 0),      # 注册量
                "logoutWbillQty": int(item.get("logoutWbillQty") or 0),  # 注销量
                "wbillQty": int(item.get("wbillQty") or 0),              # 今日仓单量
                "diff": int(item.get("diff") or 0),                      # 净变化量
            }
        elif order in ("lc", "ps", "si") and item.get("whAbbr"):
            details.setdefault(order, []).append({
                "warehouse": item.get("whAbbr"),
                "last": int(item.get("lastWbillQty") or 0),
                "reg": int(item.get("regWbillQty") or 0),
                "logout": int(item.get("logoutWbillQty") or 0),
                "today": int(item.get("wbillQty") or 0),
                "diff": int(item.get("diff") or 0),
            })
    if not targets:
        return None
    return {"summary": targets, "details": details}


def main():
    script_dir = Path(__file__).parent
    out_path = script_dir / "data.json"

    today = datetime.now()
    result = None
    used_date = None

    for i in range(10):  # 最多回溯 10 天找最近交易日
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            raw = get_gfex_data(d)
            processed = process_data(raw)
            if processed:
                result = {
                    "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "data_date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "data_date_raw": d,
                    "summary": processed["summary"],
                    "details": processed["details"],
                    "source": "广州期货交易所 仓单日报 http://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml",
                }
                used_date = d
                break
        except Exception as e:
            print(f"[跳过] {d}: {e}")
            continue

    if result is None:
        print("错误：未能获取到有效仓单数据")
        return 1

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已更新 data.json （数据日期: {used_date}）")
    print("汇总：")
    for code, s in result["summary"].items():
        print(f"  {s['variety']}({s['code']}): 注册 {s['regWbillQty']} | 注销 {s['logoutWbillQty']} | 净变化 {s['diff']:+d} | 今日仓单 {s['wbillQty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
