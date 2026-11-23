---
name: wechat-whitelist-guardian
slug: wechat-whitelist-guardian-jessewong208
displayName: 公众号IP白名单助手
version: 1.0.2
license: MIT
summary: 动态IP导致公众号报40164时，自动检测新IP、扫码登录开发者平台、填白名单并回读确认；需开启Agent操控浏览器，运行前先问电脑是否在身边，不在则配置聊天工具把二维码发到其他终端
display_name: 公众号IP白名单助手
display_name_en: WeChat Official Account IP Whitelist Guardian
description: |
  监测公网出口 IP 变化，处理微信公众号 API 白名单报错（errcode 40164）。
  支持扫码登录微信开发者平台、自动填写新 IP、推送管理员授权码、扫码后回读确认。
  使用前需在 WorkBuddy 设置→智能体 开启「浏览器操控」并给浏览器装扩展，让 Agent 能操控浏览器。
  运行前会先询问运行本技能的电脑是否在身边：不在则通过企业微信/飞书/钉钉把二维码推送到其他终端，用手机摄像头扫屏登录。
  Use when the user mentions 公众号IP白名单、IP变了、40164、动态IP、公众号又报40164、
  改白名单、确认公众号IP是否白名单、WeChat official account IP whitelist.
description_zh: |
  动态 IP 变化导致微信公众号接口报 40164 时，自动检测公网 IP、抓登录二维码、扫码登录微信开发者平台、
  自动填写新 IP 并弹出管理员授权码，扫码后回读确认白名单是否生效。适合家用宽带动态 IP 的公众号运营者。
  前置：需在 WorkBuddy「设置→智能体」开启浏览器操控（让 Agent 能操控电脑和浏览器）并给浏览器装 WorkBuddy 扩展。
  运行前会先询问运行本技能的电脑是否在身边；若不在，需先配置企业微信/飞书/钉钉，把二维码推送到身边其他终端的屏幕上，再用手机摄像头扫码登录。
description_en: |
  Detects public IP changes that cause WeChat Official Account API error 40164. Captures the login QR code,
  logs in to the WeChat Developer Platform, fills in the new IP automatically, shows the admin authorization
  QR code, and reads back the whitelist to confirm. Ideal for operators on dynamic home broadband IPs.
  Requires enabling browser control in WorkBuddy settings (Agent controls the browser) and installing the browser extension.
  Before each run it asks whether the computer running this skill is nearby; if not, configure WeCom/Feishu/DingTalk
  to push the QR code to another terminal for phone-camera scanning.
agent_created: true
---

# 公众号IP白名单助手

## 用途

家用宽带动态 IP 变化后，调用公众号 `cgi-bin/*` 接口会报 `errcode 40164 (invalid ip, not in whitelist)`。
微信**没有公开 API 可改白名单**，只能在网页端管理员扫码授权。
本 skill 把「发现变化 → 准备新 IP → 扫码登录 → 自动填 IP → 授权 → 回读确认」串成闭环，
人工只保留**手机摄像头扫电脑屏幕上的二维码**这一步。

## 使用前必读（先看这两点）

### 1. 先开通 WorkBuddy 的浏览器操控能力（一次性）

本 skill 要靠浏览器自动化打开微信开发者平台、抓二维码、填白名单，所以使用前先准备好环境：

1. 打开 WorkBuddy 左下角 **设置 → 智能体 → 浏览器操控（Beta）**
2. 打开 **「让 WorkBuddy 控制浏览器」** 开关（首次会提示安装，按提示点「安装」）
3. 给常用浏览器装官方扩展：在同一页下方找到 **WorkBuddy Chrome / Edge / QQ 浏览器扩展程序**，点「前往安装」；装好后浏览器工具栏出现 WorkBuddy 图标，点开显示**「已连接」**即可
   - 访问不了扩展商店时，用该页的「手动安装」：进 `chrome://extensions`（Edge/QQ 浏览器同理），打开「开发者模式」，把 WorkBuddy 给出的插件文件夹拖进去

没开通的话，脚本起不来浏览器、抓不到二维码，会报找不到页面元素。

### 2. 二维码「本地弹窗」和「推送到远端」是两种不同用法

| 方式 | 二维码出现在哪 | 解决什么问题 |
|------|---------------|-------------|
| `local`（本地弹窗，默认） | **你这台电脑的屏幕** | 省掉你自己开网页、找入口、扫码登录开发者平台的麻烦——由 skill 把网页打开、把码弹出来，你拿手机摄像头扫屏幕就行。适合你正坐在电脑旁 |
| `wecom` / `feishu` / `dingtalk`（远程推送） | **另一台电脑上的企微/飞书/钉钉客户端**（如公司 PC） | 你不在本地电脑旁边时，让远端那台电脑显示二维码，你在那台电脑前用手机摄像头扫屏，远程完成开发者平台登录和白名单修改 |

**关键限制**：无论哪种方式，二维码都必须用**手机摄像头对着显示它的那块屏幕**扫，相册/长按识别一律失败（微信官方限制）。所以选远程渠道时，不是"手机上收到图就能扫"，而是**远端那台电脑要开着 IM、你能看到那块屏幕**，扫的是远端电脑的屏幕。

## 首次配置（每个用户做一次）

1. 让小微帮你初始化（AppID 在公众号后台 → 设置与开发 → 基本配置可查）:
   ```
   python <skill_dir>/scripts/ip_guard.py init --appid wx你的AppID --account-name 我的公众号
   ```
2. 首次登录开发者平台（会弹出浏览器和二维码，用手机微信摄像头扫码）:
   ```
   node <skill_dir>/scripts/dev_login.js <任意路径>/dev_login_qr.png --local
   ```
   - 电脑在身边就加 `--local`：二维码直接显示在浏览器窗口（脚本自动置前），不推送 IM、不弹图片查看器
   - 电脑不在身边就不加 `--local`：登录码按 `notify_channel` 推到企微/飞书/钉钉，扫远端设备屏幕。登录码用专用文案（"扫码登录开发者平台"），和授权码区分。
   - 登录态存在 `~/.wechat-whitelist-guardian/browser-profile/`，后续复用。
   - **登录成功后一定要让 dev_login 进程正常结束、profile 落盘**，再启动 apply；两者共用同一 profile，不能同时跑（会锁冲突）。判断"登录成功"以出现 `logged_in` 事件 + 业务页能看到「API IP白名单」为准——**别只看"二维码消失"，码过期也会消失**。

**数据目录**：默认 `~/.wechat-whitelist-guardian/`（config.json / state.json / profile 都在这里）。
可用环境变量 `WL_GUARD_HOME` 改到别处。状态与 skill 包分离，更新 skill 不会丢配置。

**推送渠道由使用者自己选**（config 的 `notify_channel`，或命令 `--channel`）：

| 渠道值 | 说明 | 前置条件 |
|--------|------|----------|
| `local` | 电脑屏幕弹窗，手机摄像头扫屏幕（默认，最可靠） | 无 |
| `wecom` | 企业微信 | lark-cli 换成 wecom-cli 并授权，填 `wecom_chat_id`（`wo` 开头） |
| `feishu` | 飞书 | lark-cli 授权，填 `feishu_open_id`（`ou` 开头） |
| `dingtalk` | 钉钉 | 见下方"钉钉双模式" |
| `all` | 所有已配置渠道都推 + 本地弹窗兜底 | 上面按需配 |

**个人微信没有推送 API**，任何工具都无法程序化往个人微信发图——用 `local` 弹窗后手机微信扫屏幕就是等价效果（微信本来就只认摄像头扫屏幕，相册识别会失败）。

**钉钉双模式**（config 的 `dingtalk_mode`，让最终用户自选）：

| 模式 | 适合谁 | 配置 |
|------|--------|------|
| `webhook`（默认，推荐） | 所有人，零门槛 | 钉钉建群 → 群设置 → 智能群助手 → 加"自定义机器人" → 复制 Webhook 地址填 `dingtalk_webhook`；若开了"加签"再填 `dingtalk_secret` |
| `cli` | 已加入组织、有 CLI 权限的企业用户 | 装 `dingtalk-workspace-cli` + `dws auth login` → 填 `dingtalk_target_type`(user/group) 和 `dingtalk_target_id` |

Webhook 模式不用装任何东西、不用登录、不用加组织；CLI 模式命令以实际 dws 版本为准，可用 `dingtalk_text_cmd`/`dingtalk_image_cmd` 配 `{text}/{image}/{target}/{title}` 占位符覆盖。任何远程渠道推送失败都会自动降级为本地弹窗，扫码链路不断。

## 核心工作流

### 0. 【每次必做】先问用户：跑 skill 的这台电脑在不在身边

**在启动任何扫码流程（dev_login / apply）之前，先问用户**：

> 「运行 skill 的这台电脑现在在你身边吗？在身边我就直接把二维码显示在浏览器上给你扫；不在的话我把二维码发到企微/飞书/钉钉，你在能看到那台设备屏幕的地方扫。」

按回答走两条**完全不同的分支**：

- **在身边** → 两个脚本都加 `--local` 参数（或设 `WL_GUARD_LOCAL=1`）：
  - 二维码/授权码**直接显示在已打开的浏览器窗口里**，脚本会把窗口置前，用户拿手机摄像头扫屏幕即可
  - **不推送任何 IM**（企微/飞书/钉钉都不发）、**不弹图片查看器**——浏览器本身就是显示载体，多此一举反而添乱
  - 命令示例：`node dev_login.js <输出.png> --local` / `node apply_whitelist.js <AppID> <新IP> <输出.png> --local`
  - 此时 `notify_channel` 配什么都无所谓，`--local` 优先级最高，会跳过全部推送
- **不在身边** → 脚本**不加** `--local`：先确认推送渠道已配好（见「首次配置」），抓码存图后按 `notify_channel` 推到远端设备屏幕，用户扫远端那块屏幕；本地弹窗仅作兜底。**绝不能默认本地弹窗就开跑**，否则用户对空屏幕找不到码

这是硬性前置判断。用户没回答前不要启动 dev_login/apply。登录码和授权码走同一套分支逻辑，一次判断全程生效。

### 1. 检查 IP 是否变化（主入口）

```bash
python <skill_dir>/scripts/ip_guard.py check --json --verbose
```

- 多源交叉验证当前公网 IP，与 `state.json` 基线对比
- `unchanged`：白名单无需改，一句话带过
- `changed`：报出「旧 IP → 新 IP」，新 IP 已复制到剪贴板、已打开开发者平台，问用户是否要立即改
- 跨网段变化（如 103.x→120.x）时 CIDR /24 方案无效，别硬推

其他命令：`show`（只看 IP）、`history`（变化历史，用于判断是否可用 CIDR 网段）。

### 2. 自动改白名单（完整闭环）

**前提**：已完成首次配置 + dev_login 登录。

```bash
export NODE_PATH="<skill_dir>/../node_modules"   # 或指向已装 playwright 的 node_modules
# 电脑在身边：加 --local，授权码显示在浏览器窗口，不推送不弹图
node <skill_dir>/scripts/apply_whitelist.js <AppID> <新IP> <二维码输出路径.png> --local
# 电脑不在身边：不加 --local，授权码按 notify_channel 推到远端屏幕
```

**必须用后台任务/保持进程存活的方式启动**——普通 `&` 启动会随 shell 退出，授权窗口失效导致扫码报「系统错误」。脚本自动：
1. 进开发者平台控制台，定位「API IP白名单」，读旧 IP
2. 点编辑 → 填新 IP → 点确定
3. 弹「管理员扫码授权」→ 浏览器窗口置前显示授权码（`--local` 时）或推送到远端（非 `--local` 时），手机摄像头扫屏幕
4. 保持进程存活轮询等授权（最多 5 分钟）
5. 授权后重新加载页面**回读白名单**，结果写 `<二维码路径>.result.json`（含 `qr_channel`: `browser` 或 `remote`）

判读结果文件：`status=done && ok=true` → 白名单已改好；`waiting_scan` → 请扫码；`need_login` → 先跑 dev_login；`timeout`/`error` → 重新跑（二维码会过期，输出文件换新名字）。

### 3. 抓登录二维码推送（可选）

```bash
python <skill_dir>/scripts/ip_guard.py check --notify <渠道>
# 渠道: local / wecom / feishu / dingtalk / all，不传则读 config 的 notify_channel
```

抓公众号登录二维码 + IP 提醒，推到选定渠道。`local`（默认）只在电脑弹窗；远程渠道需先配好身份，失败会自动降级为本地弹窗。也可以不传 `--notify`，直接靠 `config.json` 的 `notify_channel` 决定。

## 关键事实（不要搞错）

- **入口已迁移**：2025-12 起白名单在**微信开发者平台** `developers.weixin.qq.com` → 控制台 → 我的业务 → 公众号 → 基础信息 → 开发密钥 → API IP白名单。旧的 mp.weixin.qq.com「设置与开发→基本配置」已无此入口。
- 白名单无公开 API，无法绕过管理员扫码；本 skill 用网页自动化填 IP + 弹授权码，扫码后自动回读确认。
- **微信扫码只支持摄像头实时扫描**，相册/长按识别一律失败。二维码必须显示在**电脑屏幕**上，手机摄像头对着扫。
- 二维码几分钟过期，过期重抓且**换新文件名**（旧文件已存在会报 AlreadyExists）。
- 白名单支持 CIDR 段（如 `58.246.68.0/24`），同段 IP 变化可一劳永逸；配置修改后等 3-5 分钟生效。
- 40164 就是 IP 不在白名单，不是 AppID/AppSecret 错误。详见 `references/wechat_whitelist.md`。

## 依赖与排错

- **Python 3.9+**（标准库，无需 pip 包）。
- **Node.js + playwright**：`npm install playwright`；不下载 Chromium，用系统 Chrome/Edge，可用 `CHROME_PATH` 指定。
- **可选 CLI**：lark-cli（飞书）/ wecom-cli（企微），需本机连接器已授权。
- Windows 若 `dirname`/`ls` 报 command not found：Bash 里先 `export PATH="/c/Program Files/Git/usr/bin:$PATH"`。
- 企微 `.CMD` 调用：subprocess 用 list 形式直接执行，不要包 `cmd.exe /c`；输出用 `encoding="utf-8", errors="replace"`；markdown 不要用 `> ` 前缀（被当重定向符）。
- **Node `execFileSync` 的 `timeout` 单位是毫秒不是秒**！推送 python 子进程要写 `timeout: 180000`（=3分钟）；写成 `180` 会在 python 启动前就超时杀进程，表现为推送失败且无报错。
- **不要给 `WL_PYTHON` 指不存在的路径**：dev_login/apply 调 notify.py 时用 `process.env.WL_PYTHON || 'python'`。不设它、用 PATH 里的 `python` 最稳；设错路径会导致推送静默失败。
- **apply 的登录判断别用 `text=登录`**：页面上其他菜单也含"登录"二字会误判成 `need_login`。只认明确标志：URL 含 `/login`/`passport`、出现 `.login-qrcode-box` 或「请使用微信扫码登录」，且业务页 30 秒内没出现「API IP白名单」才算未登录/未加载。
- **业务页加载要等足 30 秒**：微信开发者平台白名单数据异步加载，实测 6 秒出，慢时更久；等不到别急着判失败。
- **dev_login 判断"已登录"不能只看二维码消失**：码过期也会消失。要确认业务页能看到「API IP白名单」或收到 `logged_in` 事件。

## 资源

- `scripts/ip_guard.py` — IP 检测、状态对比、剪贴板、打开控制台、CIDR 分析、init 配置
- `scripts/fetch_qrcode.js` — 抓公众号登录二维码原图
- `scripts/dev_login.js` — 扫码登录开发者平台（保存 profile；`--local` 时纯浏览器扫码不推送）
- `scripts/apply_whitelist.js` — 自动改白名单 + 授权码 + 回读确认（`--local` 时纯浏览器扫码不推送）
- `scripts/notify.py` — 企微/飞书/钉钉推送（渠道可选；钉钉支持 webhook 群机器人 + dws CLI 双模式；失败降级本地弹窗）
- `scripts/config.example.json` — 配置模板（含各渠道说明）
- `references/wechat_whitelist.md` — 白名单规则、修改路径、根治方案
