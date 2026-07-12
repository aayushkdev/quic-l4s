# QCL4S - QUIC L4S

QCL4S is a Python QUIC testbed for exploring whether L4S-style congestion
control can keep latency low while still using the available bandwidth.

The project compares classic congestion controls such as Reno and Cubic with an
experimental Prague-style mode. Prague sends ECN-capable `ECT(1)` traffic,
reads `ACK_ECN` feedback, counts CE marks, and reacts when the queue starts
marking packets.

The goal is not just to make a single transfer faster. The useful question is
whether a QUIC sender can notice early congestion signals and avoid building a
large queue, which should show up as lower RTT, fewer drops, and smoother
congestion-window behavior under a bottleneck.

## Setup

```bash
uv sync
```

## Quick Benchmark

Run one local benchmark:

```bash
uv run qcl4s-bench --bytes 10485760 --cc prague
```

Use `--cc reno`, `--cc cubic`, or `--cc prague`.

Benchmark runs are written to:

```text
runs/<run-id>/
  summary.json
  server-metrics.csv
  client-metrics.csv
```

## ECN Check

```bash
uv run qcl4s-ecn-check
```

## Local CE-Marking Test

This creates a localhost bottleneck with ECN marking:

```bash
sudo tc qdisc replace dev lo root handle 1: htb default 10
sudo tc class replace dev lo parent 1: classid 1:10 htb rate 20mbit ceil 20mbit
sudo tc qdisc replace dev lo parent 1:10 fq_codel ecn
```

Run a Prague benchmark through that queue:

```bash
uv run qcl4s-bench --bytes 10485760 --cc prague
```

Inspect queue stats:

```bash
tc -s qdisc show dev lo
```

Look for `ecn_mark` in the `fq_codel` stats. In QCL4S metrics, check:

```text
ecn_received_ce
prague_alpha
prague_cwnd_reductions
```

Clean up when finished:

```bash
sudo tc qdisc del dev lo root
```

## Manual Client/Server

For manual testing, start a server:

```bash
uv run qcl4s-server --host 127.0.0.1 --port 4433
```

In another terminal:

```bash
uv run qcl4s-client --host 127.0.0.1 --port 4433 --bytes 10485760 --cc prague
```

## Notes

```text
reno and cubic are classic baselines.
prague marks packets ECT(1), uses ACK_ECN feedback, and reacts to CE marks.
The localhost tc setup is useful for development, but it is not a full real-world L4S test.
```
