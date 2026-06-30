# IDS Queue Throughput Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce sustained packet queue pressure so SmartIDS can tolerate larger traffic bursts without dropping packets or stalling the live IDS path.

**Architecture:** Keep the sniff callback minimal, but make the downstream path more scalable by adding queue configuration, overload telemetry, bounded adaptive backpressure, and a clearer separation between packet ingestion and expensive processing work. Improve the current single-consumer path incrementally before considering more invasive multi-consumer or multiprocessing changes.

**Tech Stack:** Python, `queue.Queue`, Scapy capture thread, SmartIDS packet/session/ML runtime, unittest

---

## File Map

- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffer_service.py`
  - Own queue sizing, worker-count config, consumer startup, and runtime logging of throughput settings.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffers\live_sniffer.py`
  - Keep callback minimal while adding overload-aware counters or lightweight sampling hooks only.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\processor\packet_processor.py`
  - Add safe overload-aware behavior, especially around repeated prediction frequency and low-value work under pressure.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\telemetry\engine_telemetry.py`
  - Add queue high-water, sustained-backlog, and processing-lag telemetry.
- Modify: `D:\Roshan\Projects\smartIDS\backend\CHECKLIST.md`
  - Record planned, in-progress, and completed queue-scaling work.
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_engine_telemetry.py`
  - Cover new telemetry fields and overload detection rules.
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_sniffer_service.py`
  - Cover queue sizing and consumer startup behavior.
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_packet_processor.py`
  - Cover overload-aware prediction throttling or reduced-work behavior.

---

### Task 1: Add Throughput Baseline And Queue Controls

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffer_service.py`
- Modify: `D:\Roshan\Projects\smartIDS\backend\CHECKLIST.md`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_sniffer_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_sniffer_service_uses_configured_packet_queue_size():
    service = SnifferService(interface="test0", packet_filter="ip", processor=object())
    assert service.packet_queue.maxsize == 50000


def test_sniffer_service_exposes_overload_threshold_settings():
    service = SnifferService(interface="test0", packet_filter="ip", processor=object())
    assert service.packet_queue_high_watermark_percent == 70.0
    assert service.packet_queue_critical_watermark_percent == 90.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: FAIL because queue-size and watermark config do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
self.packet_queue_maxsize = max(
    1000,
    int(os.getenv("SMARTIDS_PACKET_QUEUE_MAXSIZE", "10000")),
)
self.packet_queue_high_watermark_percent = max(
    1.0,
    float(os.getenv("SMARTIDS_PACKET_QUEUE_HIGH_WATERMARK_PERCENT", "70")),
)
self.packet_queue_critical_watermark_percent = max(
    self.packet_queue_high_watermark_percent,
    float(os.getenv("SMARTIDS_PACKET_QUEUE_CRITICAL_WATERMARK_PERCENT", "90")),
)
self.packet_queue = Queue(maxsize=self.packet_queue_maxsize)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/CHECKLIST.md packet_capture/sniffer_service.py tests/unit/core/test_sniffer_service.py
git commit -m "feat: add configurable packet queue capacity"
```

---

### Task 2: Add Real Overload Telemetry Instead Of Queue Percent Alone

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\telemetry\engine_telemetry.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_engine_telemetry.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_snapshot_reports_queue_high_watermark_and_backlog_growth():
    snapshot = collector.snapshot(packet_queue=queue, session_builder=builder)
    assert snapshot["queue_overloaded"] is True
    assert snapshot["queue_critical"] is False
    assert snapshot["processing_backlog"] == 40


def test_snapshot_reports_critical_queue_state():
    snapshot = collector.snapshot(packet_queue=queue, session_builder=builder)
    assert snapshot["queue_critical"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_engine_telemetry -v`
Expected: FAIL because those telemetry fields are missing.

- [ ] **Step 3: Write minimal implementation**

```python
processing_backlog = max(0, packets_received_total - packets_processed_total)
queue_overloaded = queue_usage_percent >= high_watermark_percent
queue_critical = queue_usage_percent >= critical_watermark_percent
```

Add the fields to the returned snapshot:

```python
"processing_backlog": processing_backlog,
"queue_overloaded": queue_overloaded,
"queue_critical": queue_critical,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_engine_telemetry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/telemetry/engine_telemetry.py tests/unit/core/test_engine_telemetry.py
git commit -m "feat: add queue overload telemetry"
```

---

### Task 3: Throttle Expensive Prediction Work Under Sustained Backlog

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\processor\packet_processor.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_packet_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_processor_skips_nonfinal_repeat_prediction_when_queue_is_critical():
    prediction = processor._maybe_predict_active_session(session_key, session, packet, heuristic)
    assert prediction is None


def test_processor_still_allows_final_prediction_when_queue_is_critical():
    prediction = processor._process_finalized_prediction(finalized, heuristic)
    assert prediction is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_packet_processor -v`
Expected: FAIL because the processor has no overload-aware prediction throttling.

- [ ] **Step 3: Write minimal implementation**

Introduce a helper that reads live queue state from telemetry or injected queue stats:

```python
def _queue_is_critical(self) -> bool:
    snapshot = self.telemetry_collector.latest_runtime_snapshot() if self.telemetry_collector else None
    return bool(snapshot and snapshot.get("queue_critical"))
```

Use it to skip only repeat active-session ML work:

```python
if self._queue_is_critical():
    self._publish_session_update(... prediction=None ...)
    return
```

Do not skip:
- packet parsing
- session tracking
- finalized-flow prediction
- blocking/manual command handling

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_packet_processor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/processor/packet_processor.py tests/unit/core/test_packet_processor.py
git commit -m "feat: throttle active-session ml under queue pressure"
```

---

### Task 4: Add More Consumer Capacity Without Touching The Sniff Callback

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffer_service.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_sniffer_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_sniffer_service_starts_configured_consumer_threads():
    service = SnifferService(interface="test0", packet_filter="ip", processor=fake_processor)
    assert service.packet_consumer_count == 2


def test_consumer_threads_are_named_for_debugging():
    names = service._build_consumer_thread_names()
    assert names == ["packet-consumer-1", "packet-consumer-2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: FAIL because the service currently runs exactly one consumer loop on the main thread.

- [ ] **Step 3: Write minimal implementation**

```python
self.packet_consumer_count = max(
    1,
    int(os.getenv("SMARTIDS_PACKET_CONSUMER_COUNT", "1")),
)
```

Start workers:

```python
for index in range(self.packet_consumer_count):
    thread = threading.Thread(
        target=self._consume_packets,
        name=f"packet-consumer-{index + 1}",
        daemon=True,
    )
    thread.start()
```

Important guardrail:
- only do this after verifying `PacketProcessor`, `SessionBuilder`, and related state are safe for shared access;
- if not thread-safe, replace this task with a staged plan that keeps one session owner thread and moves only pre-processing or forwarding off-thread.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/sniffer_service.py tests/unit/core/test_sniffer_service.py
git commit -m "feat: add configurable packet consumer workers"
```

---

### Task 5: Add Safe Load-Shedding Policy Before Packet Loss Starts

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffers\live_sniffer.py`
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\processor\packet_processor.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_packet_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_processor_prefers_new_session_tracking_over_optional_ml_when_overloaded():
    result = processor.process(packet)
    assert session_builder_called is True
    assert live_predictor_called is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_packet_processor -v`
Expected: FAIL because all optional work still runs even under overload.

- [ ] **Step 3: Write minimal implementation**

Add an overload policy in this order:

```python
1. Never drop inside the sniff callback before parse+enqueue attempt.
2. Preserve session accounting and finalized predictions.
3. Skip repeat active-session ML first.
4. Skip optional verbose logs next.
5. Keep backend publishers asynchronous and bounded.
```

Represent it with a helper:

```python
def _overload_mode(self) -> str:
    if queue_critical:
        return "critical"
    if queue_overloaded:
        return "high"
    return "normal"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_packet_processor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/sniffers/live_sniffer.py packet_capture/processor/packet_processor.py tests/unit/core/test_packet_processor.py
git commit -m "feat: add overload load-shedding policy"
```

---

### Task 6: Validate With Burst Traffic And Set Production Defaults

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\backend\README.md`
- Modify: `D:\Roshan\Projects\smartIDS\backend\CHECKLIST.md`
- Test: `D:\Roshan\Projects\smartIDS\backend\smoke\api_smoke_engine_telemetry.py`

- [ ] **Step 1: Write the failing smoke expectation**

Document target acceptance:

```text
- Normal browsing: queue stays below 30%
- Short bursts: queue may spike but drains back below 50% quickly
- Sustained stress: queue overload flag turns on before packet-drop spikes
```

- [ ] **Step 2: Run the current smoke/telemetry flow**

Run:

```bash
D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_engine_telemetry tests.unit.core.test_sniffer_service tests.unit.core.test_packet_processor
```

Expected: PASS

- [ ] **Step 3: Apply initial deployment defaults**

Suggested first-pass `.env` values:

```env
SMARTIDS_PACKET_QUEUE_MAXSIZE=50000
SMARTIDS_PACKET_QUEUE_HIGH_WATERMARK_PERCENT=70
SMARTIDS_PACKET_QUEUE_CRITICAL_WATERMARK_PERCENT=90
SMARTIDS_FORWARDER_QUEUE_SIZE=4096
SMARTIDS_PACKET_CONSUMER_COUNT=1
```

Start with `SMARTIDS_PACKET_CONSUMER_COUNT=1` until shared-state thread safety is proven.

- [ ] **Step 4: Run live validation**

Run the IDS runtime and observe:

```text
1. Packet queue percent under normal browsing
2. Backlog growth during downloads/updates/video
3. Drop count during short bursts
4. ML latency under load
```

Expected:
- lower steady-state queue occupancy than the current ~72%;
- no regression in alerts or backend reporting;
- critical mode activates before queue exhaustion.

- [ ] **Step 5: Commit**

```bash
git add backend/README.md backend/CHECKLIST.md backend/smoke/api_smoke_engine_telemetry.py
git commit -m "docs: record queue throughput tuning defaults"
```

---

## Recommendation Notes

- Do **not** start by only increasing `Queue(maxsize=10000)`; that delays pressure but does not fix throughput.
- Do **not** add ML or DB work into `LiveSniffer._handle_packet`.
- The first safe win is:
  - configurable larger queue,
  - overload telemetry,
  - skip repeated active-session prediction under pressure.
- The second safe win is consumer parallelism, but only if shared session state is proven thread-safe; otherwise keep one session owner and move other work off-thread.

## Suggested Initial Rollout Order

1. Task 1
2. Task 2
3. Task 3
4. Live measurement
5. Task 4 only if Task 3 is not enough
6. Task 5 and Task 6

## Self-Review

- Spec coverage: covers queue sizing, telemetry, overload behavior, worker scaling, and live validation.
- Placeholder scan: no `TODO` or `TBD` placeholders left.
- Type consistency: environment variable names, telemetry field names, and queue terminology are consistent across tasks.
