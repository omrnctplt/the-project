import httpx
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
import os

app = FastAPI(title="On-Premise AI API Gateway")

BIG_MODEL_URL = os.getenv("BIG_MODEL_URL", "http://localhost:8001/generate")
SMALL_MODEL_URL = os.getenv("SMALL_MODEL_URL", "http://localhost:8002/generate")

ROLE_TO_MODEL = {"developer": "big_model", "hr": "small_model", "general": "small_model"}

class PromptRequest(BaseModel):
    prompt: str

async def call_model(url: str, prompt: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json={"prompt": prompt}, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except:
            raise HTTPException(status_code=503, detail="Model hatası")

@app.post("/api/v1/chat")
async def chat_endpoint(request: PromptRequest, x_user_role: str = Header(default="general")):
    role = x_user_role.lower()
    target = ROLE_TO_MODEL.get(role, "small_model")
    if target == "big_model":
        try:
            return await call_model(BIG_MODEL_URL, request.prompt)
        except:
            return await call_model(SMALL_MODEL_URL, request.prompt)
    return await call_model(SMALL_MODEL_URL, request.prompt)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)