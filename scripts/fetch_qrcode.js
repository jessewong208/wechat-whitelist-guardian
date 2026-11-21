#!/usr/bin/env node
/**
 * 抓取微信公众平台登录二维码，输出原始图片（通用版，无账号硬编码）。
 * 用法: node fetch_qrcode.js <输出路径.gif>
 * 依赖: playwright 库 + 系统 Chrome/Edge（CHROME_PATH 可覆盖）。
 */
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');

const OUT = process.argv[2];
if (!OUT) { console.error('用法: node fetch_qrcode.js <输出路径.gif>'); process.exit(2); }

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
function fail(msg) { console.log(JSON.stringify({ ok:false, error:msg })); process.exit(1); }

(async () => {
  let browser;
  try {
    const exe = findChrome();
    if (!exe) fail('未找到可用的 Chrome/Edge，请设置 CHROME_PATH');
    browser = await chromium.launch({
      executablePath: exe, headless: true,
      args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
    });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto('https://mp.weixin.qq.com/', { waitUntil:'domcontentloaded', timeout:30000 });
    await page.waitForSelector('img.login__type__container__scan__qrcode', { timeout:20000 });
    const qr = page.locator('img.login__type__container__scan__qrcode');
    const src = await qr.getAttribute('src');
    const bytes = await page.evaluate(async (url) => {
      const r = await fetch(url.startsWith('http') ? url : new URL(url, location.origin).href);
      return Array.from(new Uint8Array(await r.arrayBuffer()));
    }, src);
    const buf = Buffer.from(bytes);
    fs.writeFileSync(OUT, buf);
    console.log(JSON.stringify({ ok:true, path:OUT, bytes:buf.length, chrome:exe,
      note:'二维码约几分钟过期，请用手机摄像头扫屏幕上显示的图' }));
  } catch (e) {
    fail(e && e.message ? e.message : String(e));
  } finally {
    if (browser) await browser.close();
  }
})();
