/**
 * 微信开发者平台扫码登录（通用版）。
 * 打开 platform → 点登录 → 显示二维码 → 保持窗口等扫码。
 * 登录态存入用户主目录下的 profile，后续脚本复用。
 *
 * 用法: node dev_login.js <二维码输出路径.gif> [--local]
 *   --local  电脑在身边：二维码就在已打开的浏览器窗口里，不弹图片查看器、不推送任何 IM。
 *            电脑不在身边时不加此参数：抓码存图并按 config 渠道推送到远端屏幕。
 * 输出 JSON 后持续运行，扫码登录成功后打印 logged_in 事件。
 *
 * 环境变量:
 *   WL_GUARD_LOCAL  设为 1 等价于 --local
 *   WL_GUARD_HOME   自定义数据目录（默认 ~/.wechat-whitelist-guardian）
 *   CHROME_PATH     自定义 Chrome/Edge 路径
 *   NODE_PATH       playwright 所在 node_modules（本 skill 会自动探测常见位置）
 */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, execFileSync } = require('child_process');

const OUT = process.argv[2];
// 电脑在身边：--local 或 WL_GUARD_LOCAL=1 → 只用浏览器窗口显示二维码，不推 IM、不弹图片查看器
const LOCAL = process.argv.includes('--local') || process.env.WL_GUARD_LOCAL === '1';
const HOME = process.env.WL_GUARD_HOME || path.join(os.homedir(), '.wechat-whitelist-guardian');
const PROFILE = path.join(HOME, 'browser-profile');

function findChrome() {
  const exe = process.platform === 'win32' ? '.exe' : '';
  const candidates = [
    process.env.CHROME_PATH,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    path.join(os.homedir(), 'AppData/Local/Google/Chrome/Application/chrome.exe'),
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
    chromium.executablePath(),
  ].filter(Boolean);
  for (const c of candidates) { try { if (fs.existsSync(c)) return c; } catch (e) {} }
  return undefined;
}

function showImageLocally(file) {
  try {
    if (process.platform === 'win32') spawn('cmd', ['/c', 'start', '', file], { detached: true, stdio: 'ignore' }).unref();
    else if (process.platform === 'darwin') spawn('open', [file], { detached: true, stdio: 'ignore' }).unref();
    else spawn('xdg-open', [file], { detached: true, stdio: 'ignore' }).unref();
    return true;
  } catch (e) { return false; }
}

function readConfig() {
  try { return JSON.parse(fs.readFileSync(path.join(HOME, 'config.json'), 'utf8')); }
  catch (e) { return {}; }
}

/**
 * 二维码显示策略：
 * - LOCAL（电脑在身边）：什么都不做——浏览器窗口本身就显示着二维码，脚本已把它置前；
 *   既不弹图片查看器，也不推 IM，避免多此一举。
 * - 非 LOCAL（电脑不在身边）：按 config 渠道推送到远端屏幕；本地弹窗仅作兜底。
 */
function pushLoginQr(file) {
  if (LOCAL) return 'browser';  // 电脑在身边：直接用浏览器窗口里的二维码
  const cfg = readConfig();
  const ch = cfg.notify_channel || 'local';
  showImageLocally(file);  // 兜底：先本地弹窗
  if (ch === 'local' || ch === 'none') return ch;
  try {
    const py = process.env.WL_PYTHON || 'python';
    // --scene login 用登录专用文案，不带 --ip
    execFileSync(py, [path.join(__dirname, 'notify.py'), '--image', file,
      '--scene', 'login', '--channel', ch],
      { encoding: 'utf-8', timeout: 180000, stdio: 'ignore' });
    return ch;
  } catch (e) {
    return ch + '(推送失败,已本地弹窗)';
  }
}

(async () => {
  fs.mkdirSync(HOME, { recursive: true });
  if (!OUT) { console.log(JSON.stringify({ok:false, error:'用法: node dev_login.js <输出路径.gif>'})); process.exit(2); }
  const exe = findChrome();
  if (!exe) { console.log(JSON.stringify({ok:false, error:'未找到 Chrome/Edge，请设置 CHROME_PATH'})); process.exit(1); }

  const ctx = await chromium.launchPersistentContext(PROFILE, {
    executablePath: exe,
    headless: false,
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto('https://developers.weixin.qq.com/platform/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1500);

  const loginText = await page.locator('text=登录').count();
  if (loginText === 0) {
    console.log(JSON.stringify({ ok: true, already_logged_in: true, url: page.url() }));
    await new Promise(() => {});
  }

  await page.locator('text=登录').first().click().catch(()=>{});
  await page.waitForSelector('.login-qrcode-box', { timeout: 15000 });
  await page.waitForTimeout(1200);

  const b64 = await page.locator('.login-qrcode-box img').evaluateAll(imgs => {
    const cands = imgs.map(i => i.src).filter(s => s.startsWith('data:image/gif;base64,'));
    return cands.length ? cands.sort((a,b)=>b.length-a.length)[0] : null;
  });
  if (!b64) { console.log(JSON.stringify({ok:false, error:'未找到登录二维码'})); await ctx.close(); process.exit(1); }
  fs.writeFileSync(OUT, Buffer.from(b64.split(',')[1], 'base64'));
  // 让浏览器窗口置前，确保用户能看到页面里的二维码
  await page.bringToFront().catch(()=>{});
  const pushed = pushLoginQr(OUT);
  console.log(JSON.stringify({ ok: true, qr_path: OUT, bytes: fs.statSync(OUT).size,
    channel: pushed, local: LOCAL, chrome: exe,
    note: LOCAL
      ? '电脑在身边：二维码已显示在浏览器窗口，请用手机微信摄像头直接扫屏幕上的码（相册识别无效）'
      : '登录码已按配置渠道推送（本地弹窗兜底）。请用手机微信摄像头对着显示二维码的屏幕扫，相册识别无效' }));

  let done = false;
  const timer = setInterval(async () => {
    if (done) return;
    try {
      if (await page.locator('.login-qrcode-box').count() === 0) {
        done = true;
        console.log(JSON.stringify({ event: 'logged_in', url: page.url() }));
      }
    } catch (e) {}
  }, 2000);
  await new Promise(() => {});
})().catch(e => { console.log(JSON.stringify({ ok:false, error:e.message })); process.exit(1); });
