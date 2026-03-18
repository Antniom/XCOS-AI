import os
import datetime
print(f"Current working directory: {os.getcwd()}")
print(f"__file__: {__file__}")
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
print(f"Target log directory: {log_dir}")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "test.log")
try:
    with open(log_file, "w") as f:
        f.write(f"Test log at {datetime.datetime.now()}\n")
    print(f"Successfully wrote to {log_file}")
except Exception as e:
    print(f"Failed to write: {e}")
