// Lightweight production-browser check for the deterministic React foundation.
// No server is started here: Python owns the live services and process deadline.
// Usage: node bootstrap_browser_check.js <url> <timeout-ms> <expect-api-probe:0|1>
// Exit 1 = broken application; exit 2 = missing/unlaunchable browser dependency.
let chromium;
try { chromium = require("playwright").chromium; }
catch {
  try { chromium = require("@playwright/test").chromium; }
  catch {
    console.error("INFRA: Playwright absent; installer les dépendances frontend d'Autospec et Chromium.");
    process.exit(2);
  }
}

async function main() {
  const target = process.argv[2];
  const timeout = Math.max(100, Number(process.argv[3] || 15000));
  const requireApiProbe = process.argv[4] === "1";
  let browser;
  try { browser = await chromium.launch({ timeout }); }
  catch (error) {
    console.error(`INFRA: Chromium indisponible : ${String(error).slice(0, 700)}`);
    process.exitCode = 2;
    return;
  }
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(timeout);
    page.setDefaultNavigationTimeout(timeout);
    const failures = [];
    page.on("pageerror", error => failures.push(String(error)));
    page.on("console", message => {
      if (message.type() === "error" && !message.location().url?.endsWith("/favicon.ico")) {
        failures.push(message.text());
      }
    });
    page.on("response", response => {
      if (response.status() >= 400 && !response.url().endsWith("/favicon.ico")) {
        failures.push(`HTTP ${response.status()}: ${response.url()}`);
      }
    });
    page.on("requestfailed", request => {
      if (!request.url().endsWith("/favicon.ico")) failures.push(`Request failed: ${request.url()}`);
    });
    const response = await page.goto(target, { waitUntil: "networkidle" });
    if (!response || response.status() >= 400) throw new Error("La page principale n'est pas accessible");
    if (failures.length) throw new Error(failures.slice(0, 6).join("\n"));
    await page.waitForFunction(() => {
      const root = document.getElementById("root");
      return root && root.childElementCount > 0 && (root.innerText.trim() || root.querySelector("canvas,svg,img"));
    });
    if (requireApiProbe) {
      await page.waitForFunction(() => /Frontend → API(?: → base de données)? : OK/.test(document.body.innerText));
    }
    if (failures.length) throw new Error(failures.slice(0, 6).join("\n"));
    console.log("Production React montée dans Chromium" + (requireApiProbe ? " ; fetch frontend → API vérifié" : ""));
  } catch (error) {
    console.error(`FAIL: ${String(error).slice(0, 2000)}`);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(String(error)); process.exitCode = 1; });
