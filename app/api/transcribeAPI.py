# from fastapi import FastAPI
# from app.api.transcribeAPI import transcribe

# app = FastAPI()

# app.include_router(transcribe, prefix='/transcribe')


from typing import List, Optional, Dict
from fastapi import File, FastAPI, APIRouter, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field 
#from vosk import Model, KaldiRecognizer, SetLogLevel
from stt import Model, version
import os
import json
import re
import wave
import csv

transcribe = APIRouter()

#constants
CONFIG_JSON_PATH = os.getenv('ASR_API_CONFIG') 
MODELS_ROOT_DIR = os.getenv('MODELS_ROOT')
VOCABS_ROOT_DIR = os.getenv('VOCABS_ROOT')
MOSES_TOKENIZER_DEFAULT_LANG = 'en'
SUPPORTED_MODEL_TYPES = ['vosk']
MODEL_TAG_SEPARATOR = "-"
SAMPLE_RATE=44100

# transcribe = APIRouter()

#models and data
loaded_models = {}
config_data = {}
language_codes = {}

#processors
# preprocessor =  lambda x: x #string IN -> string OUT
# postprocessor =  lambda x: x #string IN -> string OUT

#ASR operations
def get_model_id(lang, alt_id=None):
    model_id = lang
    if alt_id:
        model_id += MODEL_TAG_SEPARATOR + alt_id
    return model_id

def parse_model_id(model_id):
    fields = model_id.split(MODEL_TAG_SEPARATOR)
    if len(fields) == 1:
        alt=""
    elif len(fields) == 2:
        alt = fields[1]
    else:
        return False

    lang = fields[0]

    return lang, alt

def read_vocabulary(vocab_csv):
    glossary_list = []
    with open(vocab_csv, newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if "\n" in row[0]:
                print("Skipping %s"%row[0])
            else:
                glossary_list.append(row[0].lower())
        
    glossary_list = list(set(glossary_list))
    glossary_list.sort()
    glossary_list.append("[unk]")
    return json.dumps(glossary_list), len(glossary_list)

def vosk_transcriber(wf, sample_rate, model, vocabulary_json=None):
    if vocabulary_json:
        rec = KaldiRecognizer(model, sample_rate, vocabulary_json)
    else:
        rec = KaldiRecognizer(model, sample_rate)

    results = []
    words = []
    while True:
       data = wf.readframes(4000)
       if len(data) == 0:
           break
       if rec.AcceptWaveform(data):
           #results.append(json.loads(rec.Result()))
           segment_result = json.loads(rec.Result())
           results.append(segment_result)

           words.extend(segment_result['result'])
    #results.append(json.loads(rec.FinalResult()))
    return words

def do_transcribe(model_id, input):
    #Wav read
    try:
        wf = wave.open(input.file, "rb")
    except:
        raise HTTPException(status_code=404, detail="Broken WAV")
        
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
        raise HTTPException(status_code=404, detail="Audio file not WAV format mono PCM.")

    framerate = wf.getframerate()
    
    if loaded_models[model_id]['model_type'] == 'vosk':
        words = vosk_transcriber(wf, framerate, loaded_models[model_id]['stt-model'], loaded_models[model_id]['vocabulary'])
    elif loaded_models[model_id]['model_type'] == 'coqui':
        words = []

    #Postprocess (text)
    #...
    transcript = " ".join([w["word"] for w in words])

    return words, transcript

async def load_models(config_path):
    #Check if config file is there and well formatted
    if not os.path.exists(CONFIG_JSON_PATH):
        print("WARNING: Config file %s not found. No models will be loaded."%CONFIG_JSON_PATH)
        return 0

    try:
        with open(CONFIG_JSON_PATH, "r") as jsonfile: 
            config_data = json.load(jsonfile)
    except:
        print("ERROR: Config file format broken. No models will be loaded.")
        return 0

    #Check if MODELS_ROOT_DIR exists
    if not os.path.exists(MODELS_ROOT_DIR):
        print("ERROR: models directory not found. No models will be loaded.")
        return 0

    #Check if VOCABS_ROOT_DIR exists
    if not os.path.exists(VOCABS_ROOT_DIR):
        print("WARNING: Vocabularies directory not found. No restricted vocabulary will be loaded.")

    if 'languages' in config_data:
        global language_codes
        language_codes = config_data['languages']
        print("Languages: %s"%language_codes)
    else:
        print("WARNING: Language name specification dictionary ('languages') not found in configuration." )

    if not 'models' in config_data:
        print("ERROR: Model specification list ('models') not found in configuration." )
        return 0

    for model_config in config_data['models']:
        if not 'load' in model_config or model_config['load']:
            #CONFIG CHECKS
            #Check if model_type and lang fields are specified
            if not 'lang' in model_config:
                print("WARNING: Language (lang) not speficied for a model. Skipping load.")
                continue

            if not 'model_type' in model_config:
                print("WARNING: Model type (model_type) not speficied for model. Skipping load.")
                continue

            if not model_config['model_type'] in SUPPORTED_MODEL_TYPES:
                print("WARNING: model_type not recognized: %s. Skipping load"%model_config['model_type'])
                continue

            #Load model variables
            model = {}
            model['lang'] = model_config['lang']
            
            if 'alt' in model_config:
                alt_id = model_config['alt']
                model['alt'] = model_config['alt']
            else:
                alt_id = None

            model_id = get_model_id(model_config['lang'], alt_id)

            #Check if language names exist for the language ids
            if not model['lang'] in language_codes:
                print("WARNING: Source language code %s not defined in languages dict. This will probably break something."%model['lang'])

            #Check ASR model path
            if 'model_path' in model_config and model_config['model_path']:
                model_dir = os.path.join(MODELS_ROOT_DIR, model_config['model_path'])
                if not os.path.exists(model_dir):
                    print("WARNING: Model path %s not found for model %s. Skipping load."%(model_dir, model_id))
                    continue
            else:
                print("WARNING: Model path not specified for model %s. Skipping load."%model_id)
                continue

            #Check conflicting model ids
            if model_id in loaded_models:
                print("WARNING: Overwriting model %s. Make sure you give an 'alt' ids to load alternate models for same language."%model_id)

            #Load model pipeline
            print("Model: %s ("%model_id, end=" ")
            
            print("ASR", end="")
            if model_config['model_type'] == 'vosk':
                model['type'] = 'vosk'
                model['stt-model'] = Model(model_dir)
                print("-vosk", end=" ") 

            print(")")

            #Load restricted vocabulary (if any)
            if os.path.exists(VOCABS_ROOT_DIR) and 'vocabulary' in model_config and model_config['vocabulary']:
                vocab_path = os.path.join(VOCABS_ROOT_DIR, model_config['vocabulary'])
                if not os.path.exists(vocab_path):
                    print("WARNING: Vocabulary path %s not found for model %s. Skipping vocabulary load."%(vocab_path, model_id))
                    continue

                model['vocabulary'], no_items = read_vocabulary(vocab_path)
                print("Restricted vocabulary: %i items"%no_items)
            else:
                model['vocabulary'] = None

            #All good, add model to the list
            loaded_models[model_id] = model
        
    return 1

    
#HTTP operations
class TranscriptionResponse(BaseModel):
    words: List
    transcript: str

class LanguagesResponse(BaseModel):
    models: List
    languages: Dict

@transcribe.post('/short', status_code=200)
async def transcribe_short_audio(lang: str = Form(...), file: UploadFile = File(...), alt: Optional[str] = Form(None)) :
    model_id = get_model_id(lang, alt) 
    
    if not model_id in loaded_models:
        raise HTTPException(status_code=404, detail="Language %s is not supported."%model_id)
    
    w, t = do_transcribe(model_id, file)

    response = TranscriptionResponse(words=w, transcript=t)
    return response


@transcribe.get('/', status_code=200)
async def languages():
    return LanguagesResponse(languages=language_codes, models=list(loaded_models.keys()))


@transcribe.on_event("startup")
async def startup_event():
    await load_models(CONFIG_JSON_PATH)
    print("Models loaded successfully")

