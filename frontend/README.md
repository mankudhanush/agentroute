# AgentRoute web

React workspace for the AgentRoute API. Routing stays in the Python core.

```text
cd backend
uvicorn main:app --reload
```

```text
cd frontend
npm install
npm run dev
```

The UI reads `VITE_API_URL` (default `http://localhost:8000`). Provider keys stay in `agentroute/.env`.
