from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
app = FastAPI()
class InferenceRequest(BaseModel):
    prompt: str
@app.post("/generate")
async def generate(request: InferenceRequest):
    await asyncio.sleep(0.5)
    return {"model": "Big-Model-GPU", "response": f"Büyük Model: '{request.prompt}'"}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)