import socket
import json
import tempfile
import os

class ScilabBridge:
    def __init__(self, host="localhost", port=12345):
        self.host = host
        self.port = port

    def verify(self, xml: str) -> tuple[bool, str]:
        """
        Sends XML to the active Scilab session for validation.
        Returns (is_valid, error_message).
        """
        tmp_file = None
        try:
            # Create a temp file for Scilab to read
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xcos", delete=False, encoding="utf-8") as f:
                f.write(xml)
                tmp_file = f.name

            # Connect to Scilab's IPC server
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(30)  # 30 second timeout for simulation
                s.connect((self.host, self.port))
                
                # Command format: VERIFY <path>
                command = f"VERIFY {tmp_file}\n"
                s.sendall(command.encode("utf-8"))
                
                # Wait for response
                data = s.recv(4096).decode("utf-8")
                result = json.loads(data)
                
                if result.get("status") == "ok":
                    return True, ""
                else:
                    # Save failed XML for debugging
                    try:
                        log_dir = os.path.join(os.path.dirname(__file__), "logs")
                        os.makedirs(log_dir, exist_ok=True)
                        with open(os.path.join(log_dir, "last_failed.xcos"), "w", encoding="utf-8") as f:
                            f.write(xml)
                    except:
                        pass
                    return False, result.get("error", "Unknown Scilab error")

        except ConnectionRefusedError:
            return False, "Could not connect to Scilab. Is the IPC server running?"
        except socket.timeout:
            return False, "Scilab simulation timed out."
        except Exception as e:
            return False, f"IPC Error: {str(e)}"
        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.unlink(tmp_file)
                except:
                    pass
