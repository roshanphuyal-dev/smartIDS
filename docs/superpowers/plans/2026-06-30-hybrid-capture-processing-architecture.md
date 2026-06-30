# Hybrid Capture + Processing Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split SmartIDS into a fast capture-side process and a session-owner processing-side process so packet ingestion stays responsive while ML, session tracking, alerts, and backend reporting remain correct and scalable.

**Architecture:** Move packet sniffing into a dedicated capture process that performs only minimal parse and IPC enqueue. Keep one processing process as the single owner of session state, feature extraction, XGBoost primary prediction, DecisionTree secondary prediction, response policy, and backend event generation. Inside the processing process, keep publishers and telemetry on background threads so network I/O never blocks the main packet/session pipeline.

**Tech Stack:** Python `multiprocessing`, `threading`, `queue`, Scapy, SmartIDS packet/session/ML runtime, unittest

---

## Target Shape

```text
Capture Process
-> LiveSniffer
-> minimal parse
-> IPC queue

Processing Process
-> IPC reader
-> SessionBuilder (single owner)
-> SessionFeatureExtractor
-> XGBoost primary predictor
-> DecisionTree secondary predictor
-> ResponsePolicy / AutoBlocker
-> background publisher threads
-> FastAPI backend
```

## Why This Model

- Capture and processing are isolated, so packet intake is less likely to stall when ML or session work spikes.
- Session ownership stays in one process, which avoids cross-process flow-state corruption.
- Backend forwarding, alert publishing, block-event publishing, and telemetry stay off the hot path.
- It is a safer upgrade from the current design than full multiprocessing of all packet workers.

## File Map

- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\capture_process.py`
  - Capture-process entrypoint and lifecycle.
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\processing_process.py`
  - Processing-process entrypoint and IPC consumer loop.
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\ipc_contracts.py`
  - Minimal packet envelope and process-control message helpers.
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\hybrid_runner.py`
  - Parent coordinator that starts both processes and monitors them.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffers\live_sniffer.py`
  - Allow sniffer to target an abstract queue/publisher instead of only local `Queue`.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffer_service.py`
  - Preserve current single-process service, but add opt-in hybrid-mode launcher path.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\processor\packet_processor.py`
  - Make processor work cleanly inside processing process with external queue-pressure signals.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\telemetry\engine_telemetry.py`
  - Track IPC backlog and processing backlog separately.
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\main.py`
  - Add environment-driven mode switch between current and hybrid runtime.
- Modify: `D:\Roshan\Projects\smartIDS\backend\CHECKLIST.md`
  - Record planned/in-progress/completed architecture work.
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_hybrid_ipc_contracts.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_hybrid_runner.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_engine_telemetry.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_sniffer_service.py`

---

### Task 1: Define The Minimal IPC Packet Contract

**Files:**
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\ipc_contracts.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_hybrid_ipc_contracts.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_packet_message_keeps_only_runtime_required_fields():
    payload = build_packet_message(
        src_ip="10.0.0.1",
        dst_ip="10.0.0.2",
        src_port=1234,
        dst_port=443,
        protocol=6,
        packet_size=128,
        flags={"syn": 1},
        timestamp=123.45,
        payload_len=64,
        header_length=20,
        tcp_window=1024,
    )
    assert payload["type"] == "packet"
    assert payload["src_ip"] == "10.0.0.1"
    assert payload["protocol"] == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_hybrid_ipc_contracts -v`
Expected: FAIL because the IPC contract module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_packet_message(**kwargs) -> dict:
    return {
        "type": "packet",
        "src_ip": kwargs["src_ip"],
        "dst_ip": kwargs["dst_ip"],
        "src_port": kwargs["src_port"],
        "dst_port": kwargs["dst_port"],
        "protocol": kwargs["protocol"],
        "packet_size": kwargs["packet_size"],
        "flags": kwargs.get("flags", {}),
        "timestamp": kwargs["timestamp"],
        "payload_len": kwargs.get("payload_len", 0),
        "header_length": kwargs.get("header_length", 0),
        "tcp_window": kwargs.get("tcp_window", 0),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_hybrid_ipc_contracts -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/runtime/ipc_contracts.py tests/unit/core/test_hybrid_ipc_contracts.py
git commit -m "feat: add hybrid runtime ipc packet contract"
```

---

### Task 2: Add Capture Process Entry Point

**Files:**
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\capture_process.py`
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffers\live_sniffer.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_sniffer_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_capture_process_uses_sniffer_and_ipc_submitter():
    submitter = FakeSubmitter()
    process = CaptureProcess(interface="test0", packet_filter="ip", submit=submitter.submit)
    assert process.interface == "test0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: FAIL because there is no capture-process wrapper yet.

- [ ] **Step 3: Write minimal implementation**

```python
class CaptureProcess:
    def __init__(self, interface, packet_filter, submit, telemetry_collector=None):
        self.sniffer = LiveSniffer(
            packet_queue=None,
            interface=interface,
            packet_filter=packet_filter,
            telemetry_collector=telemetry_collector,
            packet_submitter=submit,
        )

    def run(self):
        self.sniffer.start()
```

Update `LiveSniffer` so `_handle_packet` prefers `packet_submitter(parsed_packet)` over local `put_nowait`.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/runtime/capture_process.py packet_capture/sniffers/live_sniffer.py tests/unit/core/test_sniffer_service.py
git commit -m "feat: add capture process entrypoint"
```

---

### Task 3: Add Processing Process Entry Point

**Files:**
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\processing_process.py`
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\processor\packet_processor.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_packet_processor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_processing_process_reads_packet_messages_and_calls_processor():
    process = ProcessingProcess(packet_source=fake_source, processor=fake_processor)
    process.consume_once()
    assert fake_processor.process_called is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_packet_processor -v`
Expected: FAIL because there is no processing-process wrapper.

- [ ] **Step 3: Write minimal implementation**

```python
class ProcessingProcess:
    def __init__(self, packet_source, processor):
        self.packet_source = packet_source
        self.processor = processor

    def consume_once(self):
        message = self.packet_source.get()
        if message.get("type") != "packet":
            return
        packet = packet_from_message(message)
        self.processor.process(packet)
```

This process is the only owner of:
- `SessionBuilder`
- `FeatureStore`
- `PacketProcessor`
- live/final prediction calls

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_packet_processor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/runtime/processing_process.py packet_capture/processor/packet_processor.py tests/unit/core/test_packet_processor.py
git commit -m "feat: add processing process entrypoint"
```

---

### Task 4: Add Parent Hybrid Runner

**Files:**
- Create: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\hybrid_runner.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_hybrid_runner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_hybrid_runner_builds_capture_and_processing_processes():
    runner = HybridRunner(interface="test0", packet_filter="ip")
    assert runner is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_hybrid_runner -v`
Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
class HybridRunner:
    def __init__(self, interface, packet_filter):
        self.packet_queue = multiprocessing.Queue(maxsize=50000)
        self.interface = interface
        self.packet_filter = packet_filter

    def start(self):
        self.capture_process = multiprocessing.Process(target=self._run_capture, daemon=True)
        self.processing_process = multiprocessing.Process(target=self._run_processing, daemon=True)
        self.capture_process.start()
        self.processing_process.start()
```

The runner should also:
- log startup mode as `hybrid`;
- detect child-process death;
- fail closed if processing dies;
- optionally restart only in a later phase, not the first pass.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_hybrid_runner -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/runtime/hybrid_runner.py tests/unit/core/test_hybrid_runner.py
git commit -m "feat: add hybrid runtime process runner"
```

---

### Task 5: Keep Background Publishing Threaded Inside Processing Process

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffer_service.py`
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\runtime\processing_process.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_sniffer_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_processing_process_builds_background_publishers_for_backend_io():
    process = ProcessingProcess(...)
    assert process.alert_publisher is not None
    assert process.event_publisher is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: FAIL because publisher construction still assumes the legacy service path only.

- [ ] **Step 3: Write minimal implementation**

Move publisher setup into a reusable factory:

```python
def build_runtime_publishers_from_env() -> RuntimePublishers:
    ...
```

Use it from:
- existing single-process `SnifferService`
- new `ProcessingProcess`

Keep:
- alert forwarding thread
- IDS event forwarding thread
- session update forwarding thread
- block event forwarding thread
- telemetry thread

inside the processing side only.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_sniffer_service -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/sniffer_service.py packet_capture/runtime/processing_process.py tests/unit/core/test_sniffer_service.py
git commit -m "refactor: share runtime publisher wiring"
```

---

### Task 6: Split Telemetry Into Capture-Side And Processing-Side Signals

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\telemetry\engine_telemetry.py`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_engine_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_snapshot_reports_ipc_queue_and_processing_backlog_separately():
    snapshot = collector.snapshot(...)
    assert "ipc_queue_usage_percent" in snapshot
    assert "processing_backlog" in snapshot
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_engine_telemetry -v`
Expected: FAIL because hybrid telemetry fields do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add fields like:

```python
"capture_packets_received_total": ...,
"ipc_queue_size": ...,
"ipc_queue_maxsize": ...,
"ipc_queue_usage_percent": ...,
"processing_packets_processed_total": ...,
"processing_backlog": ...,
```

Retain old fields for compatibility during rollout.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_engine_telemetry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/telemetry/engine_telemetry.py tests/unit/core/test_engine_telemetry.py
git commit -m "feat: add hybrid runtime telemetry fields"
```

---

### Task 7: Add Mode Switch Without Removing Current Runtime

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\main.py`
- Modify: `D:\Roshan\Projects\smartIDS\packet_capture\sniffer_service.py`
- Modify: `D:\Roshan\Projects\smartIDS\backend\CHECKLIST.md`
- Test: `D:\Roshan\Projects\smartIDS\tests\unit\core\test_hybrid_runner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_main_uses_hybrid_runner_when_env_flag_is_enabled():
    runner = build_runtime_from_env()
    assert runner.mode == "hybrid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_hybrid_runner -v`
Expected: FAIL because there is no runtime mode selection yet.

- [ ] **Step 3: Write minimal implementation**

Use:

```env
SMARTIDS_RUNTIME_MODE=single_process
SMARTIDS_RUNTIME_MODE=hybrid
```

And route startup:

```python
if runtime_mode == "hybrid":
    runner = HybridRunner(...)
else:
    runner = SnifferService(...)
```

Default remains `single_process` until hybrid mode is verified.

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.core.test_hybrid_runner -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packet_capture/main.py packet_capture/sniffer_service.py backend/CHECKLIST.md tests/unit/core/test_hybrid_runner.py
git commit -m "feat: add hybrid runtime mode switch"
```

---

### Task 8: Validate Throughput And Safety Before Expanding Further

**Files:**
- Modify: `D:\Roshan\Projects\smartIDS\backend\README.md`
- Modify: `D:\Roshan\Projects\smartIDS\backend\CHECKLIST.md`

- [ ] **Step 1: Write the acceptance checklist**

```text
- Capture process stays alive during sustained traffic
- Processing process keeps queue below critical most of the time
- Session predictions still arrive at backend
- No packet parsing or session-state corruption appears
- Both XGBoost and DecisionTree outputs still reach IDS events
```

- [ ] **Step 2: Run focused verification**

Run:

```bash
D:\Roshan\Projects\smartIDS\.venv_windows\Scripts\python.exe -m unittest tests.unit.ml.test_runtime_artifact_validation tests.unit.core.test_forwarding_contracts tests.unit.core.test_engine_telemetry tests.unit.core.test_hybrid_ipc_contracts tests.unit.core.test_hybrid_runner
```

Expected: PASS

- [ ] **Step 3: Apply first-pass runtime defaults**

Suggested `.env`:

```env
SMARTIDS_RUNTIME_MODE=hybrid
SMARTIDS_PACKET_QUEUE_MAXSIZE=50000
SMARTIDS_FORWARDER_QUEUE_SIZE=4096
SMARTIDS_PACKET_QUEUE_HIGH_WATERMARK_PERCENT=70
SMARTIDS_PACKET_QUEUE_CRITICAL_WATERMARK_PERCENT=90
```

- [ ] **Step 4: Run live smoke**

Observe:

```text
1. Normal browsing
2. Large download
3. Video stream
4. Fast repeated connection bursts
```

Record:
- IPC queue percent
- processing backlog
- drop count
- ML latency
- alert correctness

- [ ] **Step 5: Commit**

```bash
git add backend/README.md backend/CHECKLIST.md
git commit -m "docs: record hybrid runtime rollout guidance"
```

---

## Important Guardrails

- Do not let multiple processes mutate `SessionBuilder.sessions`.
- Do not run backend HTTP calls in the capture process.
- Do not move ML back into the sniff callback.
- Keep hybrid mode additive and opt-in until it proves stable.
- If process IPC overhead is high, batch messages later; do not start with batching in the first pass.
- If multiple processing workers are ever added later, shard by session key so one flow always maps to one owner.

## Recommended Rollout Order

1. IPC contract
2. Capture process
3. Processing process
4. Shared publisher wiring
5. Telemetry split
6. Mode switch
7. Live validation

## Self-Review

- Spec coverage: includes process split, session ownership, threaded backend I/O, telemetry, mode switch, and rollout validation.
- Placeholder scan: no `TODO`/`TBD` placeholders left.
- Type consistency: uses one processing-process owner model consistently and keeps XGBoost primary / DecisionTree secondary intact.
