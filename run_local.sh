export ASR_API_CONFIG=config.json
export MODELS_ROOT=models
export VOCABS_ROOT=vocabularies
uvicorn app.main:app --reload --port 8005
