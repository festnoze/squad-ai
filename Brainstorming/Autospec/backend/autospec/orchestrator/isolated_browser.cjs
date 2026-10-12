// Trusted driver: only a supplied loopback origin, no source code or commands.
let chromium;
try { chromium = require('playwright').chromium; }
catch { console.error('INFRA: Playwright missing in the factory'); process.exit(2); }
async function main() {
  const origin = new URL(process.argv[2]);
  if (origin.hostname !== '127.0.0.1' || origin.protocol !== 'http:' || origin.pathname !== '/') throw Error('Invalid owned origin');
  const timeout = Number(process.argv[3] || 15000);
  let browser;
  try { browser = await chromium.launch({timeout,args:['--force-webrtc-ip-handling-policy=disable_non_proxied_udp']}); }
  catch(e) { console.error('INFRA: ' + e); process.exitCode=2; return; }
  try {
    const context = await browser.newContext({serviceWorkers:'block'});
    if (!context.routeWebSocket) throw Error('INFRA: WebSocket routing required');
    await context.routeWebSocket(/.*/, ws=>ws.close());
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return url.origin === origin.origin ? route.continue() : route.abort();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(timeout);
    const errors=[];
    page.on('pageerror', e=>errors.push(String(e)));
    page.on('console', e=> { if(e.type()==='error') errors.push(e.text()); });
    const response=await page.goto(origin.href,{waitUntil:'networkidle',timeout});
    if(!response || response.status()!==200) throw Error('HTTP entrypoint unavailable');
    await page.waitForFunction(()=>{
      const root=document.getElementById('root');
      return root && root.childElementCount>0 && (root.innerText.trim() || root.querySelector('canvas,svg,img'));
    });
    if(process.argv[4]==='1') await page.waitForFunction(()=>/Frontend → API(?: → base de données)? : OK/.test(document.body.innerText));
    if(errors.length) throw Error(errors.slice(0,6).join('\n'));
    console.log('Chromium: production UI rendered' + (process.argv[4]==='1'?' ; frontend → API probe OK':''));
  } catch(e) { console.error('FAIL: ' + String(e).slice(0,4000)); process.exitCode=1; }
  finally { await browser.close(); }
}
main().catch(e=>{console.error(String(e));process.exitCode=1;});
