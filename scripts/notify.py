#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推送 IP 变化提醒 + 二维码到 企业微信/飞书/钉钉（通用版，渠道可选）。

身份与目标全部从 ~/.wechat-whitelist-guardian/config.json 读取，不写死任何账号。
渠道由使用者在 config 的 notify_channel 或命令行 --channel 选择：
    local(仅本地弹窗，默认) / wecom / feishu / dingtalk / all(所有已配置渠道)
个人微信无推送 API，用 local 弹窗后手机微信扫屏幕即可。

用法:
    # 白名单变化提醒（默认场景）
    python notify.py --image <图> --ip <新IP> [--old-ip <旧IP>]
                     [--channel wecom|feishu|dingtalk|local|all] [--no-image]
    # 开发者平台登录码推送（文案不同，不需要 --ip）
    python notify.py --image <图> --scene login
                     [--channel wecom|feishu|dingtalk|local|all]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shlex
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
            _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

STATE_DIR = Path(os.environ.get("WL_GUARD_HOME", str(Path.home() / ".wechat-whitelist-guardian")))
CONFIG_FILE = STATE_DIR / "config.json"
CHANNELS = ("local", "wecom", "feishu", "dingtalk", "all")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_cli(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        Path.home() / f".workbuddy/binaries/node/cli-connector-packages/{name}.CMD",
        Path.home() / f".workbuddy/binaries/node/cli-connector-packages/{name}",
        Path.home() / f".local/bin/{name}.exe",
        Path.home() / f".local/bin/{name}",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def run_cmd(argv: list[str], cwd: str | None = None, timeout: int = 90) -> dict:
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"ok": False, "error": f"找不到命令: {argv[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"命令超时: {argv[0]}"}
    out = (proc.stdout or "").strip()
    try:
        result = json.loads(out)
    except Exception:
        result = {"ok": proc.returncode == 0, "raw": out, "stderr": (proc.stderr or "").strip()}
    if isinstance(result, dict) and "ok" not in result and "success" in result:
        result["ok"] = bool(result["success"])
    return result


def run_cli(cli_name: str, args: list[str], cwd: str | None = None) -> dict:
    cli = find_cli(cli_name)
    if not cli:
        return {"ok": False, "error": f"{cli_name} 不在 PATH 中，请确认连接器已连接并授权"}
    return run_cmd([cli] + args, cwd=cwd)


def build_text(ip: str, old_ip: str | None, account: str) -> str:
    return (
        f"【{account} IP 白名单提醒】\n"
        f"公网 IP 已变化: {old_ip or '未知'} → {ip}\n"
        "微信接口会报 40164，请尽快更新白名单。\n\n"
        "让小微帮你改: 说「帮我把公众号 IP 白名单改成最新 IP」。\n\n"
        "注: 下方二维码约几分钟有效，请用摄像头扫电脑屏幕上的图。"
    )


def build_login_text(account: str) -> str:
    """开发者平台登录码场景文案（与白名单提醒区分）。"""
    return (
        f"【{account} · 微信开发者平台登录】\n"
        "请用手机微信摄像头扫描下方二维码登录开发者平台。\n\n"
        "重要: 请用摄像头对着显示此图的屏幕扫，相册/长按识别无效。\n"
        "二维码约几分钟有效，过期请让小微重新抓取。\n\n"
        "登录成功后小微会自动继续办理后续步骤。"
    )


def show_image_locally(image: Path | None) -> dict:
    """用系统默认图片查看器打开二维码（local 渠道，也是所有渠道的兜底）。"""
    if not image or not image.exists():
        return {"ok": False, "error": "没有可显示的二维码图片"}
    try:
        if os.name == "nt":
            os.startfile(str(image))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(image)], check=False, timeout=10)
        else:
            subprocess.run(["xdg-open", str(image)], check=False, timeout=10)
        return {"ok": True, "path": str(image), "note": "请用手机摄像头扫屏幕上的二维码"}
    except Exception as exc:
        return {"ok": False, "error": f"本地弹窗失败: {exc}", "path": str(image)}


def send_feishu(text: str, image: Path | None, open_id: str) -> dict:
    if not open_id:
        return {"ok": False, "error": "config.json 未填 feishu_open_id"}
    results: list[dict] = []
    ok = True
    r1 = run_cli("lark-cli", ["im", "+messages-send", "--user-id", open_id,
                              "--text", text, "--as", "bot"])
    results.append({"step": "text", "result": r1})
    ok = ok and bool(r1.get("ok"))
    if image and image.exists():
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir) / ("qrcode" + (image.suffix.lower() or ".gif"))
            shutil.copy2(image, tmp)
            r2 = run_cli("lark-cli", ["im", "+messages-send", "--user-id", open_id,
                                      "--image", "./" + tmp.name, "--as", "bot"], cwd=tmpdir)
            results.append({"step": "image", "result": r2})
            ok = ok and bool(r2.get("ok"))
    return {"ok": ok, "steps": results}


def send_wecom(text: str, image: Path | None, chat_id: str) -> dict:
    if not chat_id:
        return {"ok": False, "error": "config.json 未填 wecom_chat_id"}
    results: list[dict] = []
    ok = True
    auth = run_cli("wecom-cli", ["auth", "show", "--status"])
    if "unauthorized" in json.dumps(auth, ensure_ascii=False):
        return {"ok": False, "error": "企微未授权，请先 wecom-cli auth init 扫码授权"}
    # markdown 不要用 "> " 前缀（.CMD 经 cmd.exe 会当重定向符）
    r1 = run_cli("wecom-cli", ["message", "aibot", "send",
                               "--chat-id", chat_id, "--msg-type", "markdown",
                               "--markdown", json.dumps({"content": text}, ensure_ascii=False)])
    results.append({"step": "text", "result": r1})
    ok = ok and bool(r1.get("ok"))
    if image and image.exists():
        up = run_cli("wecom-cli", ["media", "upload", "--file-path", str(image), "--type", "image"])
        results.append({"step": "upload", "result": up})
        media_id = up.get("media_id") or (up.get("data", {}) or {}).get("media_id")
        if media_id:
            r2 = run_cli("wecom-cli", ["message", "aibot", "send",
                                       "--chat-id", chat_id, "--msg-type", "image",
                                       "--image", json.dumps({"media_id": media_id}, ensure_ascii=False)])
            results.append({"step": "image", "result": r2})
            ok = ok and bool(r2.get("ok"))
        else:
            ok = False
            results.append({"step": "image", "result": {"ok": False, "error": "图片上传未拿到 media_id"}})
    return {"ok": ok, "steps": results}


def _dingtalk_command(template: str, *, text: str, image: Path | None, target: str, title: str) -> list[str]:
    """按模板拼 dws 命令；占位符 {text}/{image}/{target}/{title}，用 shlex 安全分词。"""
    filled = (template.replace("{text}", text)
                      .replace("{image}", str(image) if image else "")
                      .replace("{target}", target)
                      .replace("{title}", title))
    return shlex.split(filled)


def _http_post_json(url: str, payload: dict, timeout: int = 20) -> dict:
    """向钉钉 Webhook POST 一个 JSON 消息，按 errcode 判断成功。"""
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "ignore")
        res = json.loads(body)
        return {"ok": res.get("errcode") == 0, "raw": res}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def send_dingtalk_webhook(text: str, image: Path | None, cfg: dict) -> dict:
    """钉钉群机器人 Webhook 模式：无需装 CLI/加组织，建群加机器人拿 Webhook 即可。"""
    webhook = cfg.get("dingtalk_webhook", "")
    if not webhook or "dingtalk.com" not in webhook:
        return {"ok": False, "error": "config.json 未填有效的 dingtalk_webhook（群机器人 Webhook 地址）"}
    url = webhook
    secret = cfg.get("dingtalk_secret", "")
    if secret:  # 加签：timestamp + 换行 + secret 做 HMAC-SHA256，base64 后 urlencode
        ts = str(round(time.time() * 1000))
        sign = base64.b64encode(
            hmac.new(secret.encode(), (ts + "\n" + secret).encode(), hashlib.sha256).digest()
        ).decode()
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"

    results: list[dict] = []
    # 文字用 markdown 消息
    r1 = _http_post_json(url, {"msgtype": "markdown",
                               "markdown": {"title": text.split("\n", 1)[0], "text": text}})
    results.append({"step": "text", "result": r1})
    ok = bool(r1.get("ok"))
    # 二维码图片用 base64+md5（钉钉 image 消息要求）
    if image and image.exists():
        raw = image.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            results.append({"step": "image", "result": {"ok": False, "error": "图片超过 2MB"}})
            ok = False
        else:
            r2 = _http_post_json(url, {"msgtype": "image", "image": {
                "base64": base64.b64encode(raw).decode(),
                "md5": hashlib.md5(raw).hexdigest(),
            }})
            results.append({"step": "image", "result": r2})
            ok = ok and bool(r2.get("ok"))
    return {"ok": ok, "steps": results, "mode": "webhook",
            "note": "群机器人 Webhook 模式；若机器人开了加签，请填 dingtalk_secret"}


def send_dingtalk_cli(text: str, image: Path | None, cfg: dict) -> dict:
    """钉钉 dws CLI 模式：企业级，需加入组织并有 CLI 访问权限。"""
    dws = find_cli("dws")
    if not dws:
        return {"ok": False, "error": "未找到钉钉 dws CLI，请先安装并 dws auth login"}
    target_type = cfg.get("dingtalk_target_type", "user")
    target = cfg.get("dingtalk_target_id", "")
    if not target:
        return {"ok": False, "error": "config.json 未填 dingtalk_target_id（userId 或群 openConversationId）"}
    title = text.split("\n", 1)[0]
    results: list[dict] = []

    tpl = cfg.get("dingtalk_text_cmd") or (
        f'"{dws}" chat +messages-send --as user --{target_type} "{target}" --title "{title}" --markdown "{text}" --yes'
    )
    try:
        argv = _dingtalk_command(tpl, text=text, image=image, target=target, title=title)
        results.append({"step": "text", "result": run_cmd(argv)})
    except Exception as exc:
        results.append({"step": "text", "result": {"ok": False, "error": f"命令模板解析失败: {exc}"}})

    if image and image.exists():
        itpl = cfg.get("dingtalk_image_cmd") or (
            f'"{dws}" chat +messages-send --as user --{target_type} "{target}" --image "{image}" --yes'
        )
        try:
            iargv = _dingtalk_command(itpl, text=text, image=image, target=target, title=title)
            results.append({"step": "image", "result": run_cmd(iargv)})
        except Exception as exc:
            results.append({"step": "image", "result": {"ok": False, "error": f"图片命令模板解析失败: {exc}"}})
    ok = bool(results) and all(step["result"].get("ok") for step in results)
    return {"ok": ok, "steps": results, "mode": "cli",
            "note": "dws 命令以你实际安装版本为准，可用 dingtalk_*_cmd 模板覆盖"}


def send_dingtalk(text: str, image: Path | None, cfg: dict) -> dict:
    """钉钉渠道分发：webhook（默认，零门槛）或 cli（企业级需组织权限）。"""
    mode = cfg.get("dingtalk_mode", "webhook")
    if mode == "cli":
        return send_dingtalk_cli(text, image, cfg)
    return send_dingtalk_webhook(text, image, cfg)


def main() -> int:
    parser = argparse.ArgumentParser(description="推送 IP 变化/登录码与二维码（渠道可选）")
    parser.add_argument("--image")
    parser.add_argument("--ip", help="新 IP（scene=whitelist 时必填）")
    parser.add_argument("--old-ip")
    parser.add_argument("--scene", choices=["whitelist", "login"], default="whitelist",
                        help="whitelist=IP变化提醒(默认), login=开发者平台登录码")
    parser.add_argument("--channel", choices=CHANNELS, help="覆盖 config 里的 notify_channel")
    parser.add_argument("--no-image", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    channel = args.channel or cfg.get("notify_channel", "local")
    account = cfg.get("account_name", "公众号")
    if args.scene == "login":
        text = build_login_text(account)
    else:
        if not args.ip:
            print(json.dumps({"ok": False, "error": "scene=whitelist 需要 --ip"}, ensure_ascii=False))
            return 2
        text = build_text(args.ip, args.old_ip, account)
    image = None if args.no_image else (Path(args.image) if args.image else None)
    if image and not image.exists():
        print(json.dumps({"ok": False, "error": f"图片不存在: {image}"}, ensure_ascii=False))
        return 1

    result: dict = {"ok": True, "channel": channel}
    senders = {
        "wecom": lambda: send_wecom(text, image, cfg.get("wecom_chat_id", "")),
        "feishu": lambda: send_feishu(text, image, cfg.get("feishu_open_id", "")),
        "dingtalk": lambda: send_dingtalk(text, image, cfg),
    }
    picked = list(senders) if channel == "all" else ([channel] if channel in senders else [])
    for name in picked:
        res = senders[name]()
        result[name] = res
        if not res.get("ok"):
            result["ok"] = False
    # local 或 all：始终本地弹窗兜底（也是个人微信扫码的等价方式）
    if channel == "local" or channel == "all" or not result["ok"]:
        result["local"] = show_image_locally(image)
        if result["local"].get("ok"):
            result["ok"] = True  # 远程失败但本地可见，扫码链路仍成立
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
