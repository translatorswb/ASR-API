from typing import List, Optional, Dict
from fastapi import File, APIRouter, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field 
from vosk import Model, KaldiRecognizer, SetLogLevel
import os
import json
import re
import wave


#constants
CONFIG_JSON_PATH = os.getenv('ASR_API_CONFIG') 
MODELS_ROOT_DIR = os.getenv('MODELS_ROOT')
MOSES_TOKENIZER_DEFAULT_LANG = 'en'
SUPPORTED_MODEL_TYPES = ['vosk']
MODEL_TAG_SEPARATOR = "-"
SAMPLE_RATE=44100

transcribe = APIRouter()

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


def get_vosk_transcriber(model_path):
    model = Model(model_path)
    rec = KaldiRecognizer(model, SAMPLE_RATE)

    def transcriber(wf):
        results = []
        while True:
           data = wf.readframes(4000)
           if len(data) == 0:
               break
           if rec.AcceptWaveform(data):
               results.append(json.loads(rec.Result()))
        #results.append(json.loads(rec.FinalResult()))
        return results

    return transcriber


def do_transcribe(model_id, input):
    #Preprocess 
    #...

    #Wav read
    try:
        wf = wave.open(input.file, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
            print ("Audio file not WAV format mono PCM.")
            raise HTTPException(status_code=404, detail="Audio file not WAV format mono PCM.")
    except:
        raise HTTPException(status_code=404, detail="Broken WAV")


    print("Framerate", wf.getframerate())
        
    #transcriber = loaded_models[model_id]['transcriber']
    results = []
    if loaded_models[model_id]['transcriber']:
        results = loaded_models[model_id]['transcriber'](wf)

    #Postprocess
    #...
    text = " ".join([r["text"] for r in results])

    return results, text

def load_models(config_path):
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

    if 'languages' in config_data:
        global language_codes
        language_codes = config_data['languages']
        print("Languages: %s"%language_codes)
    else:
        print("WARNING: Language name spefication dictionary ('languages') not found in configuration." )

    if not 'models' in config_data:
        print("ERROR: Model spefication list ('models') not found in configuration." )
        return 0

    for model_config in config_data['models']:
        if not 'load' in model_config or model_config['load']:
            #CONFIG CHECKS
            #Check if model_type and lang fields are specified
            if not 'lang' in model_config:
                print("WARNING: Language (lang) not speficied for a model. Skipping load")
                continue

            if not 'model_type' in model_config:
                print("WARNING: Model type (model_type) not speficied for model. Skipping load")
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
                print("WARNING: Source language code %s not defined in languages dict. This will surely break something."%model['lang'])

            #Check model path
            if 'model_path' in model_config and model_config['model_path']:
                model_dir = os.path.join(MODELS_ROOT_DIR, model_config['model_path'])
                if not os.path.exists(model_dir):
                    print("WARNING: Model path %s not found for model %s. Can't load custom translation model or segmenters."%(model_dir, model_id))
                    model_dir = None
            else:
                print("WARNING: Model path not specified for model %s. Can't load custom translation model or segmenters."%model_id)
                model_dir = None

            #Check conflicting model ids
            if model_id in loaded_models:
                print("WARNING: Overwriting model %s since there are duplicate entries. Make sure you give an 'alt' ids to load alternate models."%model_id)

            #Load model pipeline
            print("Model: %s ("%model_id, end=" ")

            #Load pre/post-processors
            model['preprocessors'] = []
            model['postprocessors'] = []

            # TEMPLATE
            # if 'preprocess' in model_config['pipeline'] and model_config['pipeline']['preprocess']:
            #     model['preprocessors'].append(preprocessor)
            #     print("preprocess", end=" ")
            
            if 'transcribe' in model_config['pipeline'] and model_config['pipeline']['transcribe']:
                print("transcribe", end="")
                if model_config['model_type'] == 'vosk':
                    if not model_dir:
                        print("\nWARNING: Failed to load ctranslate model for %s: model_path not specified. Skipping load."%(model_id))
                        continue

                    # model['model'] = Model(model_dir)
                    model['transcriber'] = get_vosk_transcriber(model_dir)
                    print("-vosk", end=" ") 
            else:
                model['model'] = None

            # TEMPLATE
            # if 'postprocess' in model_config['pipeline'] and model_config['pipeline']['postprocess']:
            #     model['postprocessors'].append(postprocessor)
            #     print("postprocess", end=" ")

            print(")")

            #All good, add model to the list
            loaded_models[model_id] = model
        
    return 1

    
#HTTP operations
class TranslationRequest(BaseModel):
    lang: str = Field(...)
    alt: Optional[str] = None
    # file: UploadFile = File(...)

class TranscriptionResponse(BaseModel):
    results: List
    transcript: str

class LanguagesResponse(BaseModel):
    models: Dict
    languages: Dict

@transcribe.post('/', status_code=200)
async def transcribe_audio(lang: str = Form(...), file: UploadFile = File(...)):
    model_id = get_model_id(lang) #TODO: No alternative model mechanism

    if not model_id in loaded_models:
        raise HTTPException(status_code=404, detail="Language pair %s is not supported."%model_id)
    
    r, t = do_transcribe(model_id, file)

    response = TranscriptionResponse(results=r, transcript=t)
    return response


@transcribe.get('/languages', status_code=200)
async def languages():
    languages_list = {}
    for model_id in loaded_models.keys():
        source, target, alt = parse_model_id(model_id)
        if not source in languages_list:
            languages_list[source] = {}
        if not target in languages_list[source]:
            languages_list[source][target] = []

        languages_list[source][target].append(model_id)

    return LanguagesResponse(languages=language_codes, models=languages_list)


@transcribe.on_event("startup")
async def startup_event():
    load_models(CONFIG_JSON_PATH)


