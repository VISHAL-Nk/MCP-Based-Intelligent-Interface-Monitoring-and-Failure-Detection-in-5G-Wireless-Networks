import os
from dotenv import load_dotenv
load_dotenv()  # Load .env file from project root

import uvicorn
import subprocess
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .telemetry import TelemetryIngestor
from .mcp import MCPContextEngine
from .ai import AIClient

app = FastAPI(
    title="WMN 5G Core MCP Context Engine",
    description="Exposes structured telemetry, correlated network status, and chaos control center endpoints.",
    version="1.0.0"
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ingestor = TelemetryIngestor()
mcp_engine = MCPContextEngine(ingestor=ingestor)
ai_client = AIClient()

@app.get("/health")
def health_check():
    return {"status": "UP"}

@app.get("/telemetry/metrics")
def get_metrics():
    return ingestor.get_metrics()

@app.get("/telemetry/logs")
def get_logs(limit: int = 50):
    return ingestor.get_logs(limit=limit)

@app.get("/telemetry/captures")
def get_captures():
    return ingestor.get_packet_captures()

@app.get("/mcp/context")
def get_mcp_context():
    return mcp_engine.generate_context()

@app.get("/mcp/diagnose")
def get_mcp_diagnose():
    context = mcp_engine.generate_context()
    return ai_client.diagnose(context)

# Chaos Control APIs
@app.post("/chaos/inject/{scenario}")
def inject_chaos(scenario: str):
    if scenario not in ["amf", "upf", "network", "n4", "nrf"]:
        return {"error": "Invalid scenario"}
    try:
        # Run scripts asynchronously so we don't block API threads
        subprocess.Popen(["./scripts/failures/{}/inject.sh".format(scenario)])
        return {"status": "Injected", "scenario": scenario}
    except Exception as e:
        return {"error": str(e)}

@app.post("/chaos/restore/{scenario}")
def restore_chaos(scenario: str):
    if scenario not in ["amf", "upf", "network", "n4", "nrf"]:
        return {"error": "Invalid scenario"}
    try:
        subprocess.Popen(["./scripts/failures/{}/restore.sh".format(scenario)])
        return {"status": "Restoring", "scenario": scenario}
    except Exception as e:
        return {"error": str(e)}

@app.post("/chaos/heal")
def heal_all():
    try:
        subprocess.Popen(["./scripts/failures/amf/restore.sh"])
        subprocess.Popen(["./scripts/failures/upf/restore.sh"])
        subprocess.Popen(["./scripts/failures/network/restore.sh"])
        subprocess.Popen(["./scripts/failures/n4/restore.sh"])
        subprocess.Popen(["./scripts/failures/nrf/restore.sh"])
        return {"status": "Healing all"}
    except Exception as e:
        return {"error": str(e)}

# Serve static dashboard frontend files
os.makedirs("frontend/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("frontend/static/index.html")

if __name__ == "__main__":
    uvicorn.run("backend.src.main:app", host="0.0.0.0", port=8000, reload=True)
