import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cp, mkdtemp, readFile, rm, access } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { resolve, extname } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const require = createRequire(resolve(root, "../dashboard/package.json"));
const { chromium } = require("playwright");
const out = await mkdtemp(resolve(tmpdir(), "loopx-analytics-smoke-"));
const inject = (id) => spawnSync(process.execPath, [resolve(root, "scripts/add-analytics.mjs"), out], {
  env: { ...process.env, LOOPX_GA_MEASUREMENT_ID: id }, encoding: "utf8",
});
let browser;
try {
  await cp(resolve(process.argv[2] ?? resolve(root, "dist")), out, { recursive: true });
  const initial = await readFile(resolve(out, "index.html"), "utf8");
  assert.equal(inject("").status, 0);
  assert.equal(await readFile(resolve(out, "index.html"), "utf8"), initial, "disabled mode leaves HTML unchanged");
  assert.notEqual(inject('invalid"><script>').status, 0, "malformed ID rejected");
  // This fixture ID never reaches Google: the browser intercepts every request.
  assert.equal(inject("G-TEST123456").status, 0);
  const enabled = await readFile(resolve(out, "index.html"), "utf8");
  assert.equal(inject("G-TEST123456").status, 0);
  assert.equal(await readFile(resolve(out, "index.html"), "utf8"), enabled, "injection is idempotent");
  browser = await chromium.launch({ headless: true });
  for (const scenario of ["enabled", "local", "dnt", "gpc"]) {
    const context = await browser.newContext();
    if (scenario === "dnt") await context.addInitScript(() => Object.defineProperty(navigator, "doNotTrack", { value: "1" }));
    if (scenario === "gpc") await context.addInitScript(() => Object.defineProperty(navigator, "globalPrivacyControl", { value: true }));
    const tagRequests = [];
    const origin = scenario === "local" ? "http://localhost" : "https://loopx-project.github.io";
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.hostname === "www.googletagmanager.com") {
        tagRequests.push(url.href);
        return route.fulfill({ contentType: "text/javascript", body: "" });
      }
      if (url.origin !== origin) return route.abort();
      const path = url.pathname.replace(/^\/(?:loopx\/)?/, "");
      try {
        const file = resolve(out, path || "index.html");
        const contentType = ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png" })[extname(file)] ?? "application/octet-stream";
        await route.fulfill({ contentType, body: await readFile(file) });
      } catch { await route.fulfill({ status: 404, body: "Not found" }); }
    });
    const page = await context.newPage();
    await page.goto(`${origin}/loopx/?secret=never-send-this#private-task`);
    await page.locator("h1").waitFor();
    if (scenario !== "enabled") {
      assert.equal(tagRequests.length, 0, `${scenario}: no Google request`);
      assert.equal(await page.evaluate(() => window.dataLayer), undefined);
      await context.close();
      continue;
    }
    await page.waitForFunction(() => window.dataLayer?.length >= 5);
    assert.equal(tagRequests.length, 1);
    await page.locator('.hero [data-analytics-event="setup_open"]').click();
    // Only the successful copy path in App dispatches this signal. Invalid
    // detail must never become an event or pass arbitrary data to analytics.
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("loopx:setup-copy", { detail: "shell" }));
      window.dispatchEvent(new CustomEvent("loopx:setup-copy", { detail: "never-send-this" }));
    });
    await page.getByRole("button", { name: "Close setup", exact: true }).click();
    await page.locator(".language-toggle").click();
    const rows = await page.evaluate(() => window.dataLayer.map((args) => [...args]));
    assert.equal(rows.filter((r) => r[0] === "event" && r[1] === "page_view").length, 1);
    assert.equal(rows.filter((r) => r[0] === "event" && r[1] === "setup_open").length, 1);
    assert.equal(rows.filter((r) => r[0] === "event" && r[1] === "setup_copy").length, 1);
    assert(!JSON.stringify(rows).includes("never-send-this") && !JSON.stringify(rows).includes("private-task"));
    assert.equal(rows.find((r) => r[0] === "config")[2].allow_google_signals, false);
    await page.evaluate(() => {
      document.querySelector('link[rel="canonical"]').href = "https://loopx-project.github.io/loopx/docs/";
    });
    await page.waitForFunction(() => window.dataLayer.filter((r) => r[0] === "event" && r[1] === "page_view").length === 2);
    await context.close();
  }
  assert.equal(inject("").status, 0);
  assert.equal(await readFile(resolve(out, "index.html"), "utf8"), initial, "disable removes injection");
  await assert.rejects(access(resolve(out, "site-assets/analytics.js")));
  console.log("Analytics smoke: opt-in/off, injection idempotence, invalid ID, public-host scope, DNT/GPC, pageviews, locale dedupe, CTA schema and URL redaction passed; no Google traffic sent");
} finally {
  await browser?.close();
  await rm(out, { recursive: true, force: true });
}
