# SmartIDS (Agent Notes)

## What This Repo Is (Do Not Mislabel)

- Passive, userland IDS with reactive mitigation (NOT inline IPS). Scapy sniffs copies of packets after the OS stack; responses can only block future traffic.

## Current Reality (Verify Before Assuming)

- Only `packet_capture/` has real code right now.
- `backend/`, `client/`, `ml/`, `feature_engine/`, `traffic_engine/`, `threat_engine/`, `response_engine/`, `tests/` exist but are empty stubs.
- `README.md` describes FastAPI/Next.js/Postgres and a `python/` directory; that does not match the current tree.

## Primary Entrypoint (Known Working Command)

- Packet capture service: `sudo .venv/bin/python -m packet_capture.main`
  - `sudo` is typically required for live sniffing.
  - Prefer invoking the venv interpreter explicitly (repo has `.venv/`).

## Capture Architecture Constraint (Easy To Break)

- `scapy.sniff(...)` is blocking; it runs in a dedicated thread (`packet_capture/sniffer_service.py`).
- The `prn=` callback (`LiveSniffer._handle_packet`) must stay minimal: parse + enqueue only. Do not add I/O, ML, DB, or network calls there.

## Known Footguns In Current Code

- Import path mismatch: `packet_capture/sniffer_service.py` imports `packet_capture.processors.packet_processor`, but the folder is `packet_capture/processor/packet_processor.py`.
- Type mismatch: `PacketData.packet_size` is annotated as `str`, but `PacketParser` assigns `len(packet)` (an `int`).

## Dependencies / Updating Them

- Python deps are tracked in `requirements.txt` (currently only `scapy==2.7.0`).
- Repo convention (see `toDo.txt`): after dependency changes run `pip freeze > requirements.txt`.

## High-Signal Docs

- `CONTEXT.md` and `app.md` contain the intended end-state architecture and non-negotiable rules (manual ML, firewall abstraction, keep capture non-blocking).

## Future implementation and project modelling

Reference @CONTEXT.md
