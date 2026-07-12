def main() -> None:
    print("QCL4S baseline commands:")
    print("  uv run qcl4s-bench --bytes 1048576 --cc reno")
    print("  uv run qcl4s-server --host 127.0.0.1 --port 4433")
    print("  uv run qcl4s-client --host 127.0.0.1 --port 4433 --bytes 1048576")
