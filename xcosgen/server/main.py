from fastapi import FastAPI, HTTPException, WebSocket, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import json
import os
import asyncio
import datetime

from intelligence import AutonomousLoop
from scilab_ipc import ScilabBridge

app = FastAPI(title="Xcos AI Web Dashboard API")

# Enable CORS for React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Logging Directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "backend.log")

# Clear/Initialize log file
try:
    with open(LOG_FILE, "a") as f: # Use 'a' to avoid immediate truncation on every reload in dev
        f.write(f"\n--- Xcos AI Backend Session Started: {datetime.datetime.now()} ---\n")
except Exception as e:
    print(f"FAILED TO INITIALIZE LOG FILE: {e}")

def log_event(step: str, message: str = "", level: str = "info"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event = {
        "step": step,
        "message": message,
        "level": level,
        "timestamp": timestamp
    }
    system_logs.append(event)
    
    # Write to file (Defensive for Windows file locks)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] [{level.upper()}] {step}: {message}\n")
    except Exception as e:
        # Don't crash the whole server if logging to file fails
        print(f"[LOGGING ERROR] Could not write to {LOG_FILE}: {e}")
    
    print(f"[{level.upper()}] {step}: {message}")

# Shared state
system_logs = []
loop_manager = AutonomousLoop()

# Polling IPC state
pending_tasks = asyncio.Queue()
task_results = {} # task_id -> {"status": "ok"|"error", "error": "..."}
last_heartbeat_time = 0

# Master Poller Logic (to prevent ghost pollers from hijacking tasks)
master_poller = {
    "loop_id": None,
    "last_seen": 0,
    "port": None
}

class ScilabPollingBridge:
    async def verify(self, xml: str) -> tuple[bool, str]:
        """
        Instead of socket, we queue the task and wait for Scilab to poll and respond.
        """
        task_id = f"v_{int(datetime.datetime.now().timestamp())}"
        
        # Write XML to a temp file for Scilab to import
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xcos", delete=False, encoding="utf-8") as f:
            f.write(xml)
            tmp_path = f.name

        log_event("IPC", f"Queuing verification task {task_id} with file {tmp_path}")
        
        # Put task in queue for Scilab to pick up
        await pending_tasks.put({
            "task_id": task_id,
            "zcos_path": tmp_path,
            "attempt": 1 # For compatibility with guide logic
        })
        
        # Wait for result (poll task_results)
        # In a real app, use an Event or Condition, but for simplicity we poll here
        max_wait = 300 # 5 minutes timeout (ample time for Scilab library loading)
        start_time = asyncio.get_event_loop().time()
        
        while task_id not in task_results:
            if asyncio.get_event_loop().time() - start_time > max_wait:
                log_event("IPC", f"Task {task_id} timed out waiting for Scilab.", "error")
                return False, "Timed out waiting for Scilab polling."
            await asyncio.sleep(0.5)
            
        result = task_results.pop(task_id)
        if result["status"] == "ok":
            return True, ""
        else:
            return False, result.get("error", "Unknown Scilab error")

scilab_bridge = ScilabPollingBridge()

# Resolve client/dist path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "client", "dist")

# Mount Static Files
if os.path.exists(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")
    
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(DIST_DIR, "index.html"))

class Attachment(BaseModel):
    name: str
    type: str
    data: str  # Base64

class GenerateRequest(BaseModel):
    prompt: str
    model: str
    initial_xml: Optional[str] = None
    attachments: Optional[List[Attachment]] = None
    api_key: Optional[str] = None

class ScilabResult(BaseModel):
    task_id: str
    success: bool
    error: str = ""

# Simple global to store the latest job status
class JobStatus:
    def __init__(self):
        self.output = []
        self.finished = False
        self.result = None

current_job = JobStatus()

@app.on_event("startup")
async def startup_event():
    log_event("System", "Xcos AI Backend starting up...")
    log_event("System", f"Base Directory: {BASE_DIR}")
    if os.path.exists(DIST_DIR):
        log_event("System", "Client production build found and mounted.")
    else:
        log_event("Warning", "Client production build NOT found. Serve from Vite dev server during development.", "warn")

@app.get("/config")
async def get_config():
    log_event("System", "Configuration requested by frontend.")
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "models": ["gemini-3.1-flash-lite-preview", "gemini-1.5-flash-latest"]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "connected_clients": connected_clients,
        "api_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "pending_tasks": pending_tasks.qsize()
    }


@app.get("/task")
async def get_task(request: Request):
    """Scilab polls this endpoint for verification tasks."""
    global last_heartbeat_time
    now = asyncio.get_event_loop().time()
    
    client_id = f"{request.client.host}:{request.client.port}"
    loop_id = request.query_params.get("loop_id", "unknown")
    port = request.client.port
    
    # --- Master Poller Logic ---
    master_id = master_poller["loop_id"]
    master_last = master_poller["last_seen"]
    
    # If there's an active master and this is a different ID
    if master_id is not None and master_id != loop_id:
        # ALLOW DISPLACEMENT of deterministic ghosts immediately
        is_ghost_id = master_id in ["unknown", "2113"]
        
        # If the master polled recently (within 15 seconds), reject this one UNLESS it's a ghost ID
        if now - master_last < 15 and not is_ghost_id:
            # Silently reject ghosts to prevent them from stealing tasks from the queue
            return {"status": "busy", "loop_id": loop_id}
        else:
            reason = "timeout" if now - master_last >= 15 else "ghost displacement"
            log_event("IPC", f"Master poller switched ({reason}). Old: {master_id}, New: {loop_id}")
    
    # Update master state
    master_poller["loop_id"] = loop_id
    master_poller["last_seen"] = now
    master_poller["port"] = port
    # ---------------------------

    try:
        # Time-based heartbeat
        if now - last_heartbeat_time > 30:
            log_event("Heartbeat", f"Port {port} polling (LoopID: {loop_id})")
            last_heartbeat_time = now
            
        if pending_tasks.empty():
            return {"status": "idle", "loop_id": loop_id}
            
        task = await pending_tasks.get()
        response_data = {
            "status": "pending",
            "task_id": task["task_id"],
            "zcos_path": task["zcos_path"],
            "attempt": task["attempt"]
        }
        log_event("IPC", f"Task {task['task_id']} DISPATCHED to {client_id} (LoopID: {loop_id}, Port: {port}). Data: {json.dumps(response_data)}")
        return response_data
    except Exception as e:
        log_event("IPC", f"Error in /task for {client_id}: {e}", "error")
        return {"status": "error", "message": str(e)}

@app.post("/result")
async def post_result(data: ScilabResult):
    """Scilab posts the result of a verification task here."""
    task_id = data.task_id
    success = data.success
    error = data.error
    
    log_event("IPC", f"Result received for {task_id}: success={success}")
    if not success and error:
        log_event("IPC", f"Verification Error Detail: {error}", "warn")
    
    task_results[task_id] = {
        "status": "ok" if success else "error",
        "error": error
    }
    return {"status": "received"}

@app.get("/ping")
async def ping():
    return {"ok": True}

@app.post("/generate")
async def generate_diagram(request: GenerateRequest, background_tasks: BackgroundTasks):
    global current_job
    req_id = f"req_{int(datetime.datetime.now().timestamp())}"
    current_job = JobStatus()
    
    # RESET Master Poller on new generation to ensure the newest session takes over
    master_poller["loop_id"] = None
    
    log_event("Job", f"[{req_id}] New generation request received: {request.model}. Prompt length: {len(request.prompt)}")
    
    if request.api_key:
        os.environ["GEMINI_API_KEY"] = request.api_key
        log_event("System", "Custom API Key applied for this session.")
    
    async def update_callback(data):
        current_job.output.append(data)
        step = data.get("step")
        if step == "Success":
            current_job.finished = True
            current_job.result = data.get("xml")
            log_event("Job", f"[{req_id}] Generation completed successfully.", "success")
        elif step == "Error":
            log_event("Error", f"[{req_id}] {data.get('error', 'Unknown error')}", "error")
        elif step in ["Verifying", "Fixing", "Warning", "Generating"]:
            msg = data.get("message") or data.get("error") or "..."
            log_event(step, f"[{req_id}] Iter #{data.get('iteration', '?')}: {msg}")

    log_event("System", f"[{req_id}] Scheduling background task for generation...")
    background_tasks.add_task(
        loop_manager.run, 
        request.prompt, 
        request.model, 
        scilab_bridge, 
        update_callback,
        initial_xml=request.initial_xml,
        attachments=request.attachments
    )
    return {"status": "started", "request_id": req_id}

# Auto-shutdown state
connected_clients = 0
shutdown_event = None

async def delayed_shutdown():
    await asyncio.sleep(5)
    if connected_clients == 0:
        log_event("System", "No active sessions. Auto-shutting down...", "warn")
        # Give a moment for the log to be written
        await asyncio.sleep(0.5)
        os._exit(0)

@app.websocket("/ws/status")
async def status_websocket(websocket: WebSocket):
    global connected_clients, shutdown_event
    await websocket.accept()
    log_event("System", "WebSocket connection accepted.")
    
    connected_clients += 1
    if shutdown_event:
        shutdown_event.cancel()
        shutdown_event = None
        log_event("System", "Client reconnected. Shutdown cancelled.")
    
    last_sent_job = 0
    last_sent_system = 0
    try:
        while True:
            updates = []
            
            # 1. Check system logs
            if len(system_logs) > last_sent_system:
                new_logs = system_logs[last_sent_system:]
                updates.extend(new_logs)
                last_sent_system = len(system_logs)
            
            # 2. Check job logs
            if len(current_job.output) > last_sent_job:
                new_job_logs = current_job.output[last_sent_job:]
                updates.extend(new_job_logs)
                last_sent_job = len(current_job.output)
            
            if updates:
                await websocket.send_json(updates)
            
            if current_job.finished:
                await websocket.send_json([{"step": "Finished", "xml": current_job.result}])
                # Reset job status for UI but KEEP the connection open
                current_job.finished = False 
                
            await asyncio.sleep(0.5)
    except Exception:
        pass
    finally:
        connected_clients -= 1
        await websocket.close()
        # DISABLED AUTO-SHUTDOWN: Ensuring server stays alive for Scilab even if browser refreshes
        # if connected_clients == 0:
        #     log_event("System", "Last client disconnected. Shutdown in 5s...")
        #     shutdown_event = asyncio.create_task(delayed_shutdown())

@app.get("/diagnostics")
async def get_diagnostics():
    return {
        "system_prompt": loop_manager.get_system_prompt(),
        "reference_blocks": loop_manager.get_reference_blocks()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
