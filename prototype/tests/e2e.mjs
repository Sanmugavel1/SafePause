// End-to-end run of the SafePause demo, with screenshots for the deck and a check of every step.
import { chromium } from "playwright";
const OUT = process.argv[2] || "../deck/shots";
import fs from "fs"; fs.mkdirSync(OUT, { recursive: true });
const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1920, height: 1080 } });
const errs = []; pg.on("pageerror", e => errs.push(e.message));
await fetch("http://localhost:8600/api/reset", { method: "POST", body: "{}" });
await pg.goto("http://localhost:8600/");
await pg.waitForTimeout(2000);
const app = pg.frameLocator("iframe[src^='app.html']");
const con = pg.frameLocator("iframe[src^='contact.html']");
const off = pg.frameLocator("iframe[src='officer.html']");
const state = async () => (await fetch("http://localhost:8600/api/state")).json();
const pin = async () => { for (const k of ["1", "9", "4", "7"]) { await app.locator(`#keys button[data-k='${k}']`).click(); await pg.waitForTimeout(150); } };

// A. genuine usual bill (Kamala) -> paid instantly
await pg.screenshot({ path: `${OUT}/00_home.png` });
await app.locator("text=Fill: usual bill").click();
await app.locator("text=Continue").click(); await pg.waitForTimeout(1500); await pin(); await pg.waitForTimeout(1500);
let s = await state(); console.log("A usual bill:", s.payments[0].status, s.payments[0].tier, s.payments[0].score.toFixed(4));
await app.locator("text=Done").click();

// B. scam payment 1 -> silent pause, son alerted
await app.locator("text=Fill: scam payment 1").click();
await app.locator("text=Continue").click(); await pg.waitForTimeout(7000);   // long, hesitant confirm
await pin(); await pg.waitForTimeout(2500);
s = await state(); const p1 = s.payments[0];
console.log("B scam 1:", p1.status, p1.tier, p1.score.toFixed(4), p1.reasons.map(r => r.text));
await pg.screenshot({ path: `${OUT}/01_paused.png` });

// C. son says "No. Stop it" -> escalated to officer hold
await con.locator("text=No. Stop it").click(); await pg.waitForTimeout(2500);
s = await state(); console.log("C after son:", s.payments[0].status, s.payments[0].tier);
await pg.screenshot({ path: `${OUT}/02_son_says_no.png` });

// D. officer stops it -> money returned
await off.locator("#note").fill("Customer said a 'CBI officer' is on video call. Payee name does not match stated purpose.");
await off.locator("text=Stop payment and return money").click(); await pg.waitForTimeout(2500);
s = await state(); const c1 = s.customers.find(c => c.id === 1);
console.log("D officer stop:", s.payments[0].status, "balance back:", c1.balance);
await pg.screenshot({ path: `${OUT}/03_stopped.png` });

// E. scam payment 2 from the same victim, to another new account -> straight to hold
await app.locator("text=Back to home").click();
await app.locator("text=Fill: scam payment 2").click();
await app.locator("text=Continue").click(); await pg.waitForTimeout(5000); await pin(); await pg.waitForTimeout(2500);
s = await state(); console.log("E scam 2:", s.payments[0].status, s.payments[0].tier, s.payments[0].score.toFixed(4), s.payments[0].rule);
await pg.screenshot({ path: `${OUT}/04_second_attempt.png` });

// F. genuine big payment by Rahul -> paid with no delay
await app.locator("#cust").selectOption("2"); await pg.waitForTimeout(800);
await app.locator("text=Fill: genuine big payment").click();
await app.locator("text=Continue").click(); await pg.waitForTimeout(2500); await pin(); await pg.waitForTimeout(2000);
s = await state(); console.log("F genuine 45k:", s.payments[0].status, s.payments[0].tier, s.payments[0].score.toFixed(4));
await pg.screenshot({ path: `${OUT}/05_genuine_paid.png` });

// single-pane shots for slides
const p2 = await b.newPage({ viewport: { width: 1280, height: 860 } });
await p2.goto("http://localhost:8600/officer.html"); await p2.waitForTimeout(1500);
await p2.locator(".item").filter({ hasText: "Stopped" }).first().click(); await p2.waitForTimeout(1200);
await p2.screenshot({ path: `${OUT}/officer.png` });
const lat = s.events.filter(e => e.kind === "timing").map(e => e.ms);
console.log("decision latency ms:", lat, "page errors:", errs);
await b.close();
