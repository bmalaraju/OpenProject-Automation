
import re

log_file = "output_opt_final.txt"

try:
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "delta_filter" in line or "created=" in line or "router_start" in line:
                print(line.strip())
except Exception as e:
    print(f"Error reading file: {e}")
