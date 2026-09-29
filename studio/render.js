// コマ書き出し（Playwright）。使い方:
//   node render.js <URL> <出力フォルダ> [秒,秒,...]   秒を省略すると全コマ(30fps)
// ページのエラーは標準エラーに「[pageerror] …」で出し、終了コード1で終わる（直しの材料にする）
const path = require('path'), fs = require('fs');
const { chromium } = require(path.join(process.env.USERPROFILE, 'playwright-local', 'node_modules', 'playwright'));
(async () => {
  const [url, out, list] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch();
  let failed = false;
  try {
    const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
    p.on('pageerror', e => { console.error('[pageerror]', e.message); failed = true; });
    await p.goto(url);
    await p.evaluate(() => window.ready);
    const total = await p.evaluate(() => window.TOTAL);
    const times = list ? list.split(',').map(Number) : [...Array(Math.ceil(total * 30)).keys()].map(i => i / 30);
    let n = 0;
    for (const t of times) {
      const [data, issues] = await p.evaluate(tt => { window.AUDIT = []; window.render(tt); const is = window.auditIssues(); window.AUDIT = null;
                                                    return [document.getElementById('c').toDataURL('image/png'), is]; }, t);
      if (list && issues.length) for (const s of issues) console.log(`[audit] ${t.toFixed(2)}秒: ${s}`);
      const name = list ? `t_${t.toFixed(2)}.png` : `f_${String(n).padStart(5, '0')}.png`;
      fs.writeFileSync(path.join(out, name), Buffer.from(data.split(',')[1], 'base64'));
      n++;
    }
    console.log('done', n, 'frames, total', total.toFixed(2), 's');
  } catch (e) { console.error('[pageerror]', e.message); failed = true; }
  await b.close();
  process.exit(failed ? 1 : 0);
})();
