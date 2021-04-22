from fastapi import FastAPI
from app.api.transcribeAPI import transcribe

app = FastAPI()

app.include_router(transcribe, prefix='/transcribe')