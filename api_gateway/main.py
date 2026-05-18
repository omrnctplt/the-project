import httpx
import os
import time
import json
import jwt
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from prometheus_client import Counter, make_asgi_app

app = FastAPI(title="On-Premise AI API Gateway")

# Configuration
BIG_MODEL_URL = os.getenv("BIG_MODEL_URL", "http://localhost:8001/generate")
SMALL_MODEL_URL = os.getenv("SMALL_MODEL_URL", "http://localhost:8002/generate")
SECRET_KEY = "super-secret-poc-key"
ALGORITHM = "HS256"

# Mock Database
USERS = {
    "dev_user": {"password": "dev123", "role": "developer"},
    "hr_user": {"password": "hr123", "role": "hr"},
    "gen_user": {"password": "gen123", "role": "general"}
}
ROLE_TO_MODEL = {"developer": "big_model", "hr": "small_model", "general": "small_model"}

# Metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

request_counter = Counter("ai_gateway_requests_total", "Total requests forwarded to models", ["model", "role"])
fallback_counter = Counter("ai_gateway_fallbacks_total", "Total fallback events triggered")

# Security
security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

class PromptRequest(BaseModel):
    prompt: str

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=1)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_role(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role: str = payload.get("role")
        if role is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return role
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def log_audit(role: str, target_model: str, fallback_triggered: bool):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_role": role,
        "target_model": target_model,
        "fallback_triggered": fallback_triggered
    }
    print(json.dumps(log_entry))

async def call_model(url: str, prompt: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json={"prompt": prompt}, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except:
            raise HTTPException(status_code=503, detail="Model hatası")

@app.post("/login")
async def login(request: LoginRequest):
    user = USERS.get(request.username)
    if not user or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token(data={"sub": request.username, "role": user["role"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/v1/chat")
async def chat_endpoint(request: PromptRequest, role: str = Depends(get_current_user_role)):
    target = ROLE_TO_MODEL.get(role, "small_model")
    fallback = False
    model_called = target

    if target == "big_model":
        try:
            response = await call_model(BIG_MODEL_URL, request.prompt)
            request_counter.labels(model="big_model", role=role).inc()
            log_audit(role, "big_model", fallback)
            return response
        except:
            fallback = True
            model_called = "small_model"
            fallback_counter.inc()
            request_counter.labels(model="small_model", role=role).inc()
            log_audit(role, "small_model", fallback)
            return await call_model(SMALL_MODEL_URL, request.prompt)

    request_counter.labels(model="small_model", role=role).inc()
    log_audit(role, "small_model", fallback)
    return await call_model(SMALL_MODEL_URL, request.prompt)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
