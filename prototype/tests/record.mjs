import { chromium } from "playwright";
import fs from "fs";
const dir = "../video/raw"; fs.mkdirSync(dir, { recursive: true });
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir, size: { width: 1920, height: 1080 } } });
const pg = await ctx.newPage(); const errs = [];
pg.on("pageerror", e => errs.push(e.message));
await pg.goto("http://localhost:8600/?autoplay=" + (process.argv[2] || "all"));
const t0 = Date.now(); const shots = [];
let last = "";
while (Date.now() - t0 < 330000) {
  const step = await pg.locator("#step").textContent();
  if (step !== last) { last = step; const f = `${dir}/step_${shots.length}.png`; await pg.waitForTimeout(2500); await pg.screenshot({ path: f }); shots.push([step, f]); console.log((Date.now()-t0)/1000|0, "s", step); }
  if (step === "SafePause") break;
  await pg.waitForTimeout(500);
}
await pg.waitForTimeout(5000);
const vid = await pg.video().path(); await ctx.close(); await b.close();
fs.renameSync(vid, `${dir}/safepause_demo_raw.webm`);
console.log("errors:", errs, "video:", `${dir}/safepause_demo_raw.webm`);
