# AgentScope

AgentScope is a local-first observability and anomaly detection tool for autonomous agents.

## Quick Start

### 1. Preflight Check
Before running any components, ensure Docker Desktop is running and port 8000 is free:
- **Windows**: `.\scripts\dev-preflight.ps1`
- **Linux/Mac**: `./scripts/dev-preflight.sh`

### 2. Start Infrastructure & Backend
Start the Redis container and the FastAPI backend:
```powershell
cd infra; docker-compose up -d
cd ../backend
$env:AGENTSCOPE_API_KEY = "test-key"
uvicorn app.ingest:app --host 0.0.0.0 --port 8000
```

### 3. Start Dashboard
In a new terminal:
```powershell
cd dashboard
npm install
npm run dev
```

### 4. Run Example Agent
In a new terminal:
```powershell
cd examples/langgraph_demo_agent
pip install -r requirements.txt
$env:AGENTSCOPE_API_KEY = "test-key"
python main.py
```

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for required git configuration before committing. Read [RULES.md](RULES.md) before making any code changes.
