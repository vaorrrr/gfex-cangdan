#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
广期所仓单数据自动更新脚本

- 优先用 requests；若命中反爬挑战页，则用无头 Chrome(Selenium) 过验证后取数
- 最新日度注册/注销/净变化、周/月累计、分仓库明细
- 写入 data.json + days-YYYY.json + available_dates.json
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

API_URL = "http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList"
PAGE_URL = "http://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "http://www.gfex.com.cn",
        "Referer": PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
)

_browser_ready = False


def _looks_like_challenge(text: str) -> bool:
    t = (text or "").lstrip()
    if not t:
        return True
    if t.startswith("{") or t.startswith("["):
        return False
    low = t[:500].lower()
    return (
        "<html" in low
        or "<!doctype" in low
        or "eo-bot" in low
        or "_amyjpel" in low.lower()
    )


def _bootstrap_browser_cookies(timeout: int = 45) -> None:
    """用无头 Chrome 打开仓单页，把 EO-Bot-Js-Token 等 cookie 写入 SESSION。"""
    global _browser_ready
    if _browser_ready:
        return

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=zh-CN")
    opts.add_argument(f"user-agent={UA}")
    # GitHub Actions / 本机常见路径
    for binary in (
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if Path(binary).exists():
            opts.binary_location = binary
            break

    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(PAGE_URL)
        ok = False
        for _ in range(20):
            src = driver.page_source or ""
            if "仓单" in src or "广州期货交易所" in (driver.title or ""):
                ok = True
                break
            time.sleep(1.5)
        if not ok:
            raise RuntimeError("浏览器打开广期所页面超时，未能通过反爬验证")

        for c in driver.get_cookies():
            SESSION.cookies.set(
                c.get("name"),
                c.get("value"),
                domain=c.get("domain") or "www.gfex.com.cn",
                path=c.get("path") or "/",
            )
        # 在页面上下文再打一次接口，确认可用
        probe = driver.execute_async_script(
            """
            const done = arguments[arguments.length - 1];
            const d = arguments[0];
            fetch('/u/interfacesWebTdWbillWeeklyQuotes/loadList', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'
              },
              body: 'gen_date=' + d,
              credentials: 'include'
            }).then(r => r.text()).then(t => done(t.slice(0, 80)))
              .catch(e => done('ERR:' + e));
            """,
            datetime.now().strftime("%Y%m%d"),
        )
        if isinstance(probe, str) and probe.startswith("ERR"):
            raise RuntimeError(f"浏览器内请求失败: {probe}")
        if isinstance(probe, str) and _looks_like_challenge(probe):
            raise RuntimeError("浏览器内仍返回挑战页")
        _browser_ready = True
        print("[信息] 已通过无头浏览器完成反爬验证，后续用 Cookie 拉数")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def get_gfex_data(date_str: str, allow_browser: bool = True) -> dict:
    """拉取指定交易日仓单。失败时自动尝试浏览器过验证。"""
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = SESSION.post(API_URL, data={"gen_date": date_str}, timeout=25)
            text = resp.text or ""
            if _looks_like_challenge(text):
                raise ValueError("命中反爬挑战页")
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("返回非 JSON 对象")
            return data
        except Exception as e:
            last_err = e
            print(f"[重试] {date_str} attempt={attempt + 1}: {e}")
            if allow_browser and attempt == 0:
                try:
                    _bootstrap_browser_cookies()
                except Exception as be:
                    print(f"[警告] 浏览器过验证失败: {be}")
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"拉取 {date_str} 失败: {last_err}")


def process_data(raw: dict) -> dict | None:
    if raw.get("code") != "0" or not raw.get("data"):
        return None

    targets: dict[str, Any] = {}
    details: dict[str, list] = {}
    for item in raw["data"]:
        variety = item.get("variety", "") or ""
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
            details.setdefault(order, []).append(
                {
                    "warehouse": item.get("whAbbr") or "",
                    "trademark": (item.get("trademarkName") or "").strip(),
                    "last": int(item.get("lastWbillQty") or 0),
                    "reg": int(item.get("regWbillQty") or 0),
                    "logout": int(item.get("logoutWbillQty") or 0),
                    "today": int(item.get("wbillQty") or 0),
                    "diff": int(item.get("diff") or 0),
                }
            )
    if not targets:
        return None
    return {"summary": targets, "details": details}


def fmt_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    out_path = script_dir / "data.json"

    old_history: list = []
    if out_path.exists():
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
            old_history = old.get("history") or []
        except Exception:
            pass

    today = datetime.now()
    snaps: list[tuple[str, dict]] = []

    # 最多回溯 45 个自然日，凑满约 22 个有数据的交易日（周/月基准）
    for i in range(0, 45):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            raw = get_gfex_data(d)
            processed = process_data(raw)
            if processed:
                snaps.append((d, processed))
                print(f"[OK] {d} 品种小计 {list(processed['summary'].keys())}")
                if len(snaps) >= 22:
                    break
            else:
                print(f"[空] {d} 无仓单小计（可能非交易日）")
        except Exception as e:
            print(f"[跳过] {d}: {e}")
            continue

    if not snaps:
        print("错误：未能获取到有效仓单数据（请检查网络/反爬）")
        return 1

    latest_d, latest = snaps[0]
    week_d, week = snaps[min(5, len(snaps) - 1)]
    month_d, month = snaps[min(20, len(snaps) - 1)]

    summary: dict[str, Any] = {}
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

    def row_key(wh: dict) -> tuple:
        return (wh.get("warehouse") or "", wh.get("trademark") or "")

    details: dict[str, list] = {}
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

    year = latest_d[:4]
    year_path = script_dir / f"days-{year}.json"
    year_map: dict = {}
    if year_path.exists():
        try:
            year_map = json.loads(year_path.read_text(encoding="utf-8"))
        except Exception:
            year_map = {}
    year_map[fmt_date(latest_d)] = day_snap
    year_path.write_text(json.dumps(year_map, ensure_ascii=False), encoding="utf-8")

    available: set[str] = set()
    day_files: list[str] = []
    for p in sorted(script_dir.glob("days-*.json")):
        day_files.append(p.name)
        try:
            chunk = json.loads(p.read_text(encoding="utf-8"))
            available.update(chunk.keys())
        except Exception:
            pass
    available.add(fmt_date(latest_d))
    available_list = sorted(available, reverse=True)
    (script_dir / "available_dates.json").write_text(
        json.dumps(available_list, ensure_ascii=False), encoding="utf-8"
    )

    result = {
        **day_snap,
        "history": history,
        "available_dates": available_list,
        "day_files": day_files or [f"days-{year}.json"],
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 已更新 data.json （数据日期: {latest_d}）")
    print(f"   周基准: {week_d}  月基准: {month_d}")
    print(f"   可浏览日期: {len(available_list)} 天（已写入 {year_path.name}）")
    for code, s in result["summary"].items():
        print(
            f"  {s['variety']}({s['code']}): "
            f"日 {s['diff']:+d} | 周 {s['weekDiff']:+d} | 月 {s['monthDiff']:+d} | "
            f"今日仓单 {s['wbillQty']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
