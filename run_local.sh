export ASR_API_CONFIG=config.json
export MODELS_ROOT=models
uvicorn app.main:app --reload --port 8005
