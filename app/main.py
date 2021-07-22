from fastapi import FastAPI
import os
from app.api.transcribeAPI import transcribe
from fastapi.middleware.cors import CORSMiddleware

ROOT_PATH = '/' + os.environ.get('PROXY_PREFIX') if os.environ.get('PROXY_PREFIX') else None

app = FastAPI(title="Speech API",
              description="API for automatic transcription and diarization",
              version="0.1", 
              root_path=ROOT_PATH, 
              redoc_url="/redoc", openapi_url="/openapi.json", docs_url="/docs")

origins = [
    "http://127.0.0.1",
    "http://127.0.0.1:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transcribe, prefix='/transcribe')
