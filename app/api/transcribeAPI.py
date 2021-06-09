from typing import List, Optional, Dict
from fastapi import File, FastAPI, APIRouter, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field 
import numpy as np
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
SUPPORTED_MODEL_TYPES = ['vosk', 'coqui']
MODEL_TAG_SEPARATOR = "-"
COQUI_SCORER_EXT = '.scorer'
COQUI_MODEL_EXT = '.pb'

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
        rec = vosk.KaldiRecognizer(model, sample_rate, vocabulary_json)
    else:
        rec = vosk.KaldiRecognizer(model, sample_rate)

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
    final_result = json.loads(rec.FinalResult())
    results.append(final_result)
    if 'result' in final_result:
        words.extend(final_result['result'])
    
    return words

# def convert_samplerate(file_like, desired_sample_rate):
#     #create empty file to copy the file_object to
#     temp_dir = tempfile.gettempdir()
#     local_wav_path = os.path.join(temp_dir, file_like.filename)
#     local_wav = open(local_wav_path, 'wb+')
#     shutil.copyfileobj(file_like.file, local_wav)
#     local_wav.close()
#     print(local_wav_path)

#     sox_cmd = "sox {} --type raw --bits 16 --channels 1 --rate {} --encoding signed-integer --endian little --compression 0.0 --no-dither - ".format(
#         local_wav_path, desired_sample_rate
#     )
#     try:
#         output = subprocess.check_output(shlex.split(sox_cmd), stderr=subprocess.PIPE)
#     except subprocess.CalledProcessError as e:
#         raise RuntimeError("SoX returned non-zero status: {}".format(e.stderr))
#     except OSError as e:
#         raise OSError(
#             e.errno,
#             "SoX not found, use {}hz files or install it: {}".format(
#                 desired_sample_rate, e.strerror
#             ),
#         )

#     return np.frombuffer(output, np.int16)

def do_transcribe(model_id, input):
    #Wav read
    try:
        wf = wave.open(input.file, "rb")
    except:
        raise HTTPException(status_code=400, detail="Broken WAV")
        
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
        raise HTTPException(status_code=400, detail="Audio file not WAV format mono PCM.")

    framerate = wf.getframerate()

    if loaded_models[model_id]['type'] == 'vosk':
        words = vosk_transcriber(wf, framerate, loaded_models[model_id]['stt-model'], loaded_models[model_id]['vocabulary'])
        transcript = " ".join([w["word"] for w in words])
    elif loaded_models[model_id]['type'] == 'coqui':
        if 'framerate' in loaded_models[model_id] and loaded_models[model_id]['framerate'] != framerate:
            raise HTTPException(status_code=400, detail="Audio file not in framerate %i"%loaded_models[model_id]['framerate'])
        
        audio = np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
        transcript = loaded_models[model_id]['stt-model'].stt(audio)
        words = []

    #Postprocess (text)
    #...
    
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
                    print("ERROR: Model path %s not found for model %s. Skipping load."%(model_dir, model_id))
                    continue
            else:
                print("ERROR: Model path not specified for model %s. Skipping load."%model_id)
                continue

            #Check conflicting model ids
            if model_id in loaded_models:
                print("WARNING: Overwriting model %s. Make sure you give an 'alt' ids to load alternate models for same language."%model_id)

            #Load model pipeline
            print("Model: %s ("%model_id, end=" ")
            
            print("ASR", end="")
            if model_config['model_type'] == 'vosk':
                global vosk
                import vosk
                model['type'] = 'vosk'
                model['stt-model'] = vosk.Model(model_dir)
                print("-vosk", end=" ") 
            elif model_config['model_type'] == 'coqui':
                global stt
                import stt
                model['type'] = 'coqui'

                model_path_candidates = [f for f in os.listdir(model_dir) if f.endswith(COQUI_MODEL_EXT)]
                if len(model_path_candidates) != 1:
                    print("\nERROR: Can't find a unique model with extension .pb under model directory %s"%(model_dir))
                    continue

                model_path = os.path.join(model_dir, model_path_candidates[0])

                model['stt-model'] = stt.Model(model_path)

                print("-coqui", end=" ") 

                scorer_path_candidates = [f for f in os.listdir(model_dir) if f.endswith(COQUI_SCORER_EXT)]
                if len(scorer_path_candidates) == 0:
                    print("without scorer", end=" ")
                elif len(scorer_path_candidates) == 1:
                    scorer_path = os.path.join(model_dir, scorer_path_candidates[0])
                    model['stt-model'].enableExternalScorer(scorer_path)
                    print("with scorer", end=" ")
                else:
                    print("\nWARNING: More than one scorer under model directory", model_dir)

            else:
                print("\nERROR: Unknown model type", model_config['model_type'])
                continue

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

            if 'framerate' in model_config:
                model['framerate'] = model_config['framerate']
                print("Framerate: %i"%model['framerate'])

            #All good, add model to the list
            loaded_models[model_id] = model
        
    return len(loaded_models)

    
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
    no_models = await load_models(CONFIG_JSON_PATH)
    print("%i models loaded successfully"%no_models)

