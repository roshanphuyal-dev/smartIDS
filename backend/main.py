from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import HTMLResponse


app = FastAPI(title="SmartIDS Alert Stub")
MAX_ALERTS = 500
ALERTS = deque(maxlen=MAX_ALERTS)


class AlertIn(BaseModel):
    type: str = "ml_attack_detected"
    attack_type: str
    confidence: float
    src_ip: str
    dst_ip: str
    src_port: int | None = None
    dst_port: int | None = None
    protocol: int | None = None
    timestamp: float | None = None


@app.post("/alerts")
def receive_alert(alert: AlertIn):
    item = alert.model_dump()
    item["received_at"] = datetime.now(timezone.utc).isoformat()
    ALERTS.appendleft(item)
    return {"ok": True, "count": len(ALERTS)}


@app.get("/alerts")
def list_alerts(limit: int = 100):
    safe_limit = max(1, min(int(limit), MAX_ALERTS))
    return {"count": len(ALERTS), "alerts": list(ALERTS)[:safe_limit]}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SmartIDS Alert Stub</title>
  <style>
    :root { --bg:#0f172a; --panel:#111827; --text:#e5e7eb; --muted:#9ca3af; --warn:#ef4444; --ok:#22c55e; }
    body { margin:0; font-family: Segoe UI, sans-serif; background:linear-gradient(135deg,#0b1022,#111827 55%,#1f2937); color:var(--text); }
    .wrap { max-width:1000px; margin:0 auto; padding:24px; }
    h1 { margin:0 0 12px; font-size:24px; }
    .meta { color:var(--muted); margin-bottom:16px; }
    table { width:100%; border-collapse:collapse; background:rgba(17,24,39,.8); border:1px solid #263042; border-radius:10px; overflow:hidden; }
    th, td { padding:10px; text-align:left; border-bottom:1px solid #263042; font-size:14px; }
    th { color:#cbd5e1; background:#0b1220; }
    .attack { color:var(--warn); font-weight:600; }
    .normal { color:var(--ok); font-weight:600; }
    code { color:#93c5fd; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>SmartIDS Alerts</h1>
    <div class="meta">Auto-refresh every 2 seconds. Endpoint: <code>POST /alerts</code></div>
    <div id="count" class="meta">Loading...</div>
    <table>
      <thead>
        <tr>
          <th>Attack Type</th>
          <th>Confidence</th>
          <th>Source</th>
          <th>Destination</th>
          <th>Protocol</th>
          <th>Timestamp</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </div>

  <script>
    async function refreshAlerts() {
      const res = await fetch('/alerts?limit=100');
      const data = await res.json();
      document.getElementById('count').textContent = `Stored alerts: ${data.count}`;
      const rows = document.getElementById('rows');
      rows.innerHTML = '';
      for (const a of data.alerts) {
        const tr = document.createElement('tr');
        const attackClass = a.attack_type === 'Normal Traffic' ? 'normal' : 'attack';
        tr.innerHTML = `
          <td class="${attackClass}">${a.attack_type}</td>
          <td>${(a.confidence ?? 0).toFixed(4)}</td>
          <td>${a.src_ip}:${a.src_port ?? '-'}</td>
          <td>${a.dst_ip}:${a.dst_port ?? '-'}</td>
          <td>${a.protocol ?? '-'}</td>
          <td>${a.received_at ?? '-'}</td>
        `;
        rows.appendChild(tr);
      }
    }
    refreshAlerts();
    setInterval(refreshAlerts, 2000);
  </script>
</body>
</html>
"""
