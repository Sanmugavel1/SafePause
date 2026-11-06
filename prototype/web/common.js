// Shared helpers for all SafePause demo screens.
const rs = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const mask = (acc) => "XXXX" + String(acc).slice(-4);
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}
function poll(fn, ms = 1000) {
  let busy = false;
  const tick = async () => { if (busy) return; busy = true;
    try { fn(await api("/api/state")); } catch (e) { console.warn(e); } busy = false; };
  tick(); return setInterval(tick, ms);
}
function clock(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
