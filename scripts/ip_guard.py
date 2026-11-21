#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公众号 API IP 白名单助手 - 公网 IP 检测与状态对比（通用版）.

与个人版的区别：所有路径基于脚本位置/用户主目录动态定位，AppID 从 config 读取，
不绑定任何具体账号或本机绝对路径，可直接分发给他人使用。

用法:
    python ip_guard.py init --appid wx... [--account-name 名称]   # 首次配置
    python ip_guard.py check [--json] [--no-open] [--no-copy]
    python ip_guard.py show  [--json]
    python ip_guard.py history [--limit N] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import webbrowser
from collections import Counter
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
            _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 状态目录：用户主目录下，与 skill 包分离，更新 skill 不会丢数据。
# 可用环境变量 WL_GUARD_HOME 覆盖，方便自定义位置。
STATE_DIR = Path(os.environ.get("WL_GUARD_HOME", str(Path.home() / ".wechat-whitelist-guardian")))
STATE_FILE = STATE_DIR / "state.json"
CONFIG_FILE = STATE_DIR / "config.json"
MAX_CHANGES = 50

IP_SOURCES = [
    ("ipip", "https://myip.ipip.net"),
    ("ipify", "https://api.ipify.org"),
    ("ip.sb", "https://api.ip.sb/ip"),
    ("ipinfo", "https://ipinfo.io/ip"),
    ("icanhazip", "https://icanhazip.com"),
]
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
# 2025-12 起白名单入口迁移到微信开发者平台；旧 mp 后台已无此入口。
CONSOLE_URL = "https://developers.weixin.qq.com/platform/"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_state() -> dict:
    default = {"last_ip": None, "last_check": None, "first_seen": None, "changes": []}
    if not STATE_FILE.exists():
        return default
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for key, value in default.items():
            data.setdefault(key, value)
        return data
    except Exception:
        return default


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["changes"] = state["changes"][-MAX_CHANGES:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_public_ip(timeout: float = 5.0, verbose: bool = False) -> str | None:
    results: list[str] = []
    for name, url in IP_SOURCES:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (IP-Guardian/2.0)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read(2048).decode("utf-8", "ignore")
            match = IPV4_RE.search(text)
            if match:
                ip = match.group(0)
                results.append(ip)
                if verbose:
                    print(f"  [{name}] {ip}", file=sys.stderr)
                if results.count(ip) >= 2:
                    break
            elif verbose:
                print(f"  [{name}] 未解析到 IPv4", file=sys.stderr)
        except Exception as exc:
            if verbose:
                print(f"  [{name}] 失败: {type(exc).__name__}", file=sys.stderr)
    if not results:
        return None
    return Counter(results).most_common(1)[0][0]


def copy_to_clipboard(text: str) -> bool:
    try:
        if os.name == "nt":
            clip = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "clip.exe"
            cmd = [str(clip)] if clip.exists() else ["clip"]
            subprocess.run(cmd, input=text, text=True, check=True,
                           capture_output=True, timeout=10)
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=10)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text,
                           text=True, check=True, timeout=10)
        return True
    except Exception:
        return False


def open_console_page() -> bool:
    try:
        return bool(webbrowser.open(CONSOLE_URL))
    except Exception:
        return False


def suggest_cidr(current_ip: str, state: dict, min_samples: int = 3) -> dict | None:
    ips = [c.get("new") for c in state.get("changes", []) if c.get("new")]
    if current_ip and current_ip not in ips:
        ips.append(current_ip)
    ips = list(dict.fromkeys(ips))
    if len(ips) < min_samples:
        return None
    segments: dict[str, list[str]] = {}
    for ip in ips:
        parts = ip.split(".")
        if len(parts) != 4:
            continue
        seg = ".".join(parts[:3]) + ".0/24"
        segments.setdefault(seg, []).append(ip)
    if not segments:
        return None
    seg, matched = max(segments.items(), key=lambda item: len(item[1]))
    if len(matched) < 2:
        return None
    return {
        "cidr": seg,
        "covered": len(matched),
        "total": len(ips),
        "ratio": round(len(matched) / len(ips), 2),
    }


def fmt_time(iso_str: str | None) -> str:
    if not iso_str:
        return "未知"
    try:
        return datetime.fromisoformat(iso_str).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str


def build_steps(new_ip: str, cfg: dict) -> str:
    appid = cfg.get("appid") or "<你的AppID>"
    return (
        "操作步骤（约 1 分钟）:\n"
        "  1. 登录微信开发者平台 developers.weixin.qq.com（管理员微信扫码）\n"
        f"  2. 控制台 → 我的业务 → 公众号 → {cfg.get('account_name', '你的公众号')} → 基础信息 → 开发密钥 → API IP白名单\n"
        f"  3. 填入新 IP 并确定（AppID: {appid}，新 IP 已复制到剪贴板）\n"
        "  4. 管理员手机扫码授权，等 3-5 分钟生效\n"
        f"\n新 IP: {new_ip}\n"
        "提示: 让小微帮你改的话，直接说「帮我把公众号 IP 白名单改成最新 IP」。"
    )


def notify_with_qrcode(ip: str, previous: str | None, channel: str) -> dict:
    """抓公众号登录二维码，按选定渠道推送。返回推送结果。"""
    import tempfile
    scripts = Path(__file__).resolve().parent
    result: dict = {"qrcode": False, "notified": False, "channel": channel}

    env = os.environ.copy()
    if os.name == "nt":
        git_usr = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin"
        if not git_usr.exists():
            git_usr = Path(r"C:\Program Files\Git\usr\bin")
        if git_usr.exists():
            env["PATH"] = str(git_usr) + os.pathsep + env.get("PATH", "")
    node_modules = env.get("NODE_PATH") or str(Path.home() / ".workbuddy/binaries/node/workspace/node_modules")
    env["NODE_PATH"] = node_modules

    with tempfile.TemporaryDirectory() as tmpdir:
        raw = Path(tmpdir) / "qrcode.gif"
        try:
            proc = subprocess.run(
                ["node", str(scripts / "fetch_qrcode.js"), str(raw)],
                env=env, capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace",
            )
            qr = json.loads(proc.stdout.strip())
            if not qr.get("ok"):
                result["error"] = f"抓二维码失败: {qr.get('error', proc.stderr.strip())}"
                return result
            result["qrcode"] = True
        except Exception as exc:
            result["error"] = f"抓二维码异常: {type(exc).__name__}: {exc}"
            return result

        cmd = [sys.executable, str(scripts / "notify.py"),
               "--image", str(raw), "--ip", ip, "--channel", channel]
        if previous:
            cmd += ["--old-ip", previous]
        try:
            proc2 = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180,
                                   encoding="utf-8", errors="replace")
            result["notify_raw"] = proc2.stdout.strip()
            try:
                result["notification"] = json.loads(proc2.stdout.strip())
                result["notified"] = bool(result["notification"].get("ok"))
            except Exception:
                result["error"] = "推送结果解析失败"
        except Exception as exc:
            result["error"] = f"推送异常: {type(exc).__name__}: {exc}"
    return result


def cmd_init(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.appid:
        cfg["appid"] = args.appid
    if args.account_name:
        cfg["account_name"] = args.account_name
    if args.feishu_open_id:
        cfg["feishu_open_id"] = args.feishu_open_id
    if args.wecom_chat_id:
        cfg["wecom_chat_id"] = args.wecom_chat_id
    if args.qr_display:
        cfg["qr_display"] = args.qr_display
    if args.notify_channel:
        cfg["notify_channel"] = args.notify_channel
    if args.dingtalk_target_id:
        cfg["dingtalk_target_id"] = args.dingtalk_target_id
    if args.dingtalk_target_type:
        cfg["dingtalk_target_type"] = args.dingtalk_target_type
    if args.dingtalk_mode:
        cfg["dingtalk_mode"] = args.dingtalk_mode
    if args.dingtalk_webhook:
        cfg["dingtalk_webhook"] = args.dingtalk_webhook
    if args.dingtalk_secret:
        cfg["dingtalk_secret"] = args.dingtalk_secret
    cfg.setdefault("qr_display", "local")
    cfg.setdefault("notify_channel", "local")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "config": str(CONFIG_FILE), "appid": cfg.get("appid")},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.verbose:
        print("正在查询公网出口 IP（多源交叉验证）...", file=sys.stderr)
    ip = get_public_ip(timeout=args.timeout, verbose=args.verbose)
    if not ip:
        message = "所有 IP 查询源均失败，请检查网络"
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False)
              if args.json else f"[失败] {message}")
        return 2

    state = load_state()
    previous = state.get("last_ip")
    changed = previous is not None and previous != ip
    first_run = previous is None
    timestamp = now_iso()

    if first_run:
        state["first_seen"] = timestamp
    if changed:
        state.setdefault("changes", []).append(
            {"old": previous, "new": ip, "time": timestamp}
        )
    state["last_ip"] = ip
    state["last_check"] = timestamp
    save_state(state)

    clipboard_ok = False
    browser_ok = False
    cidr = suggest_cidr(ip, state)
    notification = None

    if changed and not args.no_copy:
        clipboard_ok = copy_to_clipboard(ip)
    if changed and not args.no_open:
        browser_ok = open_console_page()
    notify_chan = args.notify or (cfg.get("notify_channel") if cfg.get("notify_channel") != "local" else None)
    if changed and notify_chan:
        notification = notify_with_qrcode(ip, previous, notify_chan)

    if args.json:
        print(json.dumps({
            "status": "changed" if changed else ("first_run" if first_run else "unchanged"),
            "current_ip": ip,
            "previous_ip": previous,
            "checked_at": timestamp,
            "clipboard": clipboard_ok,
            "browser_opened": browser_ok,
            "cidr_suggestion": cidr,
            "appid_configured": bool(cfg.get("appid")),
            "notification": notification,
        }, ensure_ascii=False, indent=2))
        return 0

    if changed:
        print(f"[IP 已变化] {fmt_time(timestamp)}")
        print(f"旧 IP: {previous}")
        print(f"新 IP: {ip}")
        print()
        print("新 IP 已复制到剪贴板。" if clipboard_ok else
              f"剪贴板复制失败，请手动复制: {ip}")
        print("已打开微信开发者平台，请登录后台修改白名单。" if browser_ok else
              "请打开 https://developers.weixin.qq.com 修改白名单。")
        print()
        print(build_steps(ip, cfg))
        if cidr:
            print()
            print(f"[省事建议] 历史 {cidr['total']} 个 IP 中有 {cidr['covered']} 个属于 "
                  f"{cidr['cidr']} 段。若这段覆盖你常见的出口 IP，"
                  f"可直接在白名单填 {cidr['cidr']}，以后同段变化都不用再改。")
        if notification:
            print()
            if notification.get("notified"):
                print(f"已按渠道 {notify_chan} 推送登录二维码 + IP 提醒。请用手机摄像头扫屏幕上的图。")
            else:
                print(f"推送失败: {notification.get('error', '未知原因')}。已本地弹窗兜底，请按上面步骤手动操作。")
    elif first_run:
        print(f"[基线已建立] 当前公网 IP: {ip}")
        print("已记录。下次 IP 变化时会提醒你并自动复制新 IP。")
        if not cfg.get("appid"):
            print("还没配置 AppID，请先运行: python ip_guard.py init --appid wx你的AppID")
    else:
        print(f"[IP 未变] 当前公网 IP: {ip}（上次检查 {fmt_time(state.get('last_check'))}）")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    ip = get_public_ip(timeout=args.timeout, verbose=args.verbose)
    if not ip:
        print(json.dumps({"status": "error"}, ensure_ascii=False) if args.json
              else "[失败] 查询不到公网 IP")
        return 2
    if args.json:
        print(json.dumps({"status": "ok", "current_ip": ip}, ensure_ascii=False))
    else:
        print(f"当前公网 IP: {ip}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    state = load_state()
    changes = state.get("changes", [])[-args.limit:]
    if args.json:
        print(json.dumps({"last_ip": state.get("last_ip"), "changes": changes},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"当前记录 IP: {state.get('last_ip') or '未记录'}")
    print(f"累计变化: {len(state.get('changes', []))} 次")
    if not changes:
        print("暂无变化记录。")
        return 0
    print()
    for item in reversed(changes):
        print(f"{fmt_time(item.get('time'))}  {item.get('old')} → {item.get('new')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="公众号 API IP 白名单助手（通用版）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="首次配置 AppID 等")
    p_init.add_argument("--appid", help="公众号 AppID（wx 开头）")
    p_init.add_argument("--account-name", help="公众号名称，便于识别")
    p_init.add_argument("--feishu-open-id", help="飞书 open_id（可选，用于推送二维码）")
    p_init.add_argument("--wecom-chat-id", help="企微 chat_id（可选，用于推送二维码）")
    p_init.add_argument("--qr-display", choices=["local", "none"], help="二维码显示方式")
    p_init.add_argument("--notify-channel", choices=["local", "wecom", "feishu", "dingtalk", "all"],
                        help="二维码推送渠道，由使用者自选（默认 local 本地弹窗）")
    p_init.add_argument("--dingtalk-mode", choices=["webhook", "cli"], help="钉钉模式：webhook=群机器人(默认零门槛) / cli=dws命令行(需组织权限)")
    p_init.add_argument("--dingtalk-webhook", help="钉钉群机器人 Webhook 地址（webhook 模式）")
    p_init.add_argument("--dingtalk-secret", help="钉钉机器人加签 secret（可选）")
    p_init.add_argument("--dingtalk-target-id", help="钉钉接收方 userId 或群 openConversationId（cli 模式）")
    p_init.add_argument("--dingtalk-target-type", choices=["user", "group"], help="钉钉接收类型（cli 模式）")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="检测并对比，变化时提醒+复制+打开页面")
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument("--no-open", action="store_true")
    p_check.add_argument("--no-copy", action="store_true")
    p_check.add_argument("--verbose", action="store_true")
    p_check.add_argument("--timeout", type=float, default=5.0)
    p_check.add_argument("--notify", choices=["local", "wecom", "feishu", "dingtalk", "all"],
                         help="IP变化时抓登录二维码并按渠道推送（默认读 config 的 notify_channel）")
    p_check.set_defaults(func=cmd_check)

    p_show = sub.add_parser("show", help="只显示当前公网 IP，不更新状态")
    p_show.add_argument("--json", action="store_true")
    p_show.add_argument("--verbose", action="store_true")
    p_show.add_argument("--timeout", type=float, default=5.0)
    p_show.set_defaults(func=cmd_show)

    p_hist = sub.add_parser("history", help="查看 IP 变化历史")
    p_hist.add_argument("--limit", type=int, default=20)
    p_hist.add_argument("--json", action="store_true")
    p_hist.set_defaults(func=cmd_history)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
