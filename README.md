# QCL4S - QUIC L4S

QCL4S is a Python project for experimenting with L4S-style low-latency
congestion control over QUIC. It provides a QUIC client/server testbed for
measuring transfer speed, latency, and transport behavior as the congestion
control logic evolves.

## Setup

```bash
uv sync
```

## Run

Run a manual server:

```bash
uv run qcl4s-server --host 127.0.0.1 --port 4433
```

In another terminal, run a manual client:

```bash
uv run qcl4s-client --host 127.0.0.1 --port 4433 --bytes 1048576
```

Run an automated Reno benchmark:

```bash
uv run qcl4s-bench --bytes 1048576 --cc reno
```

Run an automated Cubic benchmark:

```bash
uv run qcl4s-bench --bytes 1048576 --cc cubic
```

Check local ECN socket support:

```bash
uv run qcl4s-ecn-check
```

Benchmark runs are written to `runs/`:

```text
runs/<run-id>/
  summary.json
  server-metrics.csv
  client-metrics.csv
```
