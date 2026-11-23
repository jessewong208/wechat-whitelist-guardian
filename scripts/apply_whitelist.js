/**
 * 自动修改公众号 API IP 白名单（微信开发者平台）+ 管理员授权扫码流程（通用版）。
 * 需要已用 dev_login.js 扫码登录过开发者平台（登录态存 profile）。
 *
 * 流程: 填新IP → 确定 → 弹"管理员扫码授权"二维码 → 等扫码 → 回读确认
 * 用法: node apply_whitelist.js <AppID> <新IP> <二维码输出路径.png> [--local]
 *   --local  电脑在身边：授权码就在已打开的浏览器窗口里，不弹图片查看器、不推送任何 IM。
 *            电脑不在身边时不加此参数：抓码存图并按 config 渠道推送到远端屏幕。
 * 结果写入 <二维码路径>.result.json
 *
 * 环境变量:
 *   WL_GUARD_LOCAL  设为 1 等价于 --local
 *   WL_GUARD_HOME   自定义数据目录（默认 ~/.wechat-whitelist-guardian）
 *   CHROME_PATH     自定义 Chrome/Edge 路径
 */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, execFileSync } = require('child_process');

const APPID = process.argv[2];
const NEW_IP = process.argv[3];
const OUT_PNG = process.argv[4];
// 电脑在身边：授权码就在浏览器弹窗里，不推 IM、不弹图片查看器
const LOCAL = process.argv.includes('--local') || process.env.WL_GUARD_LOCAL === '1';
const RESULT = OUT_PNG + '.result.json';
const HOME = process.env.WL_GUARD_HOME || path.join(os.homedir(), '.wechat-whitelist-guardian');
const PROFILE = path.join(HOME, 'browser-profile');

function writeResult(o){ fs.writeFileSync(RESULT, JSON.stringify(o, null, 2)); }

function findChrome() {
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
 * 授权码显示策略：
 * - LOCAL（电脑在身边）：什么都不做——授权对话框就在浏览器页面里，脚本已把窗口置前；
 *   既不弹图片查看器，也不推 IM。
 * - 非 LOCAL（电脑不在身边）：按 config 渠道推送到远端屏幕；本地弹窗仅作兜底。
 */
function pushAuthQr(file) {
  if (LOCAL) return 'browser';
  const cfg = readConfig();
  const ch = cfg.notify_channel || 'local';
  showImageLocally(file);  // 兜底：先本地弹窗
  if (ch === 'local' || ch === 'none') return ch;
  try {
    const py = process.env.WL_PYTHON || 'python';
    execFileSync(py, [path.join(__dirname, 'notify.py'), '--image', file, '--ip', NEW_IP, '--channel', ch],
      { encoding: 'utf-8', timeout: 180000, stdio: 'ignore' });
    return ch;
  } catch (e) {
    return ch + '(推送失败,已本地弹窗)';
  }
}

(async () => {
  if (!APPID || !NEW_IP || !OUT_PNG) {
    writeResult({ok:false, error:'用法: node apply_whitelist.js <AppID> <新IP> <输出.png>'});
    process.exit(2);
  }
  fs.mkdirSync(HOME, { recursive: true });
  const exe = findChrome();
  if (!exe) { writeResult({ok:false, error:'未找到 Chrome/Edge，请设置 CHROME_PATH'}); process.exit(1); }
  writeResult({ok:false, status:'running'});

  const ctx = await chromium.launchPersistentContext(PROFILE, {
    executablePath: exe,
    headless: false,
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  const url = `https://developers.weixin.qq.com/console/product/mp/${APPID}?tab1=basicInfo&tab2=dev`;
  await page.goto(url, { waitUntil:'domcontentloaded', timeout:30000 });
  // 白名单数据通常 3-8 秒加载出来，给足 30 秒；不要用 body 里的「登录」字样判断登录态
  await page.waitForFunction(() => document.body.innerText.includes('API IP白名单'), {timeout:30000}).catch(()=>{});
  await page.waitForTimeout(800);

  // 未登录判断：只认明确的扫码登录标志（二维码框 / 登录页 URL），避免误判
  const onLoginPage = /\/login|passport|login\.html/i.test(page.url())
    || (await page.locator('.login-qrcode-box').count()) > 0
    || (await page.locator('text=请使用微信扫码登录').count()) > 0;
  const hasWhitelist = (await page.locator('body').innerText()).includes('API IP白名单');
  if (onLoginPage || !hasWhitelist) {
    writeResult({ok:false, status:'need_login', note:'开发者平台未登录或白名单页未加载，请先运行 dev_login.js 扫码登录',
      url: page.url(), hasWhitelist});
    await ctx.close();
    process.exit(1);
  }

  const item = page.locator('.deploy-info-item').filter({hasText:'API IP白名单'}).first();
  const oldIp = (await item.locator('.deploy-info-item__content').innerText()).trim().replace(/编辑$/,'').trim();

  await item.locator('text=编辑').first().click();
  await page.waitForTimeout(500);
  const dlg = page.locator('.weui-desktop-dialog').filter({hasText:'设置 API IP 白名单'}).first();
  await dlg.locator('textarea').fill(NEW_IP);
  await dlg.locator('button.weui-desktop-btn_primary').first().click();
  await page.waitForTimeout(1800);

  const authDlg = page.locator('.weui-desktop-dialog:visible').filter({hasText:'管理员扫码授权'}).first();
  const authCount = await page.locator('.weui-desktop-dialog:visible').filter({hasText:'管理员扫码授权'}).count();
  writeResult({ok:false, status:'waiting_scan', old_ip:oldIp, target_ip:NEW_IP,
    auth_dialog:authCount>0, qr_channel: LOCAL ? 'browser' : 'remote'});

  if (authCount > 0) {
    // 让浏览器窗口置前，用户直接扫页面里的授权码
    await page.bringToFront().catch(()=>{});
    const b64 = await authDlg.locator('img').evaluateAll(imgs => {
      const q = imgs.map(i=>i.src).find(s=>s.startsWith('data:image/') && s.length>1000);
      return q || null;
    });
    if (b64) {
      fs.writeFileSync(OUT_PNG, Buffer.from(b64.split(',')[1], 'base64'));
      pushAuthQr(OUT_PNG);
    } else {
      // 没存到图也不影响 LOCAL 模式——页面里本来就显示授权码
      if (!LOCAL) writeResult({ok:false, status:'no_qr_found', note:'授权弹窗未找到二维码图片'});
    }
  }

  let authorized = false;
  for (let i=0; i<150; i++) {
    await page.waitForTimeout(2000);
    try {
      const stillAuth = await page.locator('.weui-desktop-dialog:visible').filter({hasText:'管理员扫码授权'}).count();
      if (authCount > 0 && stillAuth === 0) { authorized = true; break; }
    } catch(e){}
  }

  if (authorized) {
    await page.waitForTimeout(1500);
    await page.goto(url, {waitUntil:'domcontentloaded', timeout:30000});
    await page.waitForFunction(()=>document.body.innerText.includes('API IP白名单'),{timeout:25000}).catch(()=>{});
    await page.waitForTimeout(1200);
    const item2 = page.locator('.deploy-info-item').filter({hasText:'API IP白名单'}).first();
    const newIp = (await item2.locator('.deploy-info-item__content').innerText()).trim().replace(/编辑$/,'').trim();
    writeResult({ok:newIp===NEW_IP, status:'done', old_ip:oldIp, new_ip:newIp, target_ip:NEW_IP,
      note:newIp===NEW_IP?'白名单已更新成功':'授权完成但白名单值不符，请检查'});
  } else {
    writeResult({ok:false, status:'timeout', old_ip:oldIp, target_ip:NEW_IP,
      note:'5分钟内未检测到扫码授权，二维码可能已过期，请重新执行'});
  }
  await page.waitForTimeout(2000);
  await ctx.close();
})().catch(e => { writeResult({ok:false, status:'error', error:e.message}); });
