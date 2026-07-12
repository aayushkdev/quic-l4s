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

Start the server:

```bash
uv run qcl4s-server --host 127.0.0.1 --port 4433
```

In another terminal, run the client:

```bash
uv run qcl4s-client --host 127.0.0.1 --port 4433 --bytes 1048576
```
