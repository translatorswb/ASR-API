from typing import List, Optional, Dict
from fastapi import File, FastAPI, APIRouter, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field 
from time import perf_counter
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
SUPPORTED_MODEL_TYPES = ['vosk', 'deepspeech']
MODEL_TAG_SEPARATOR = "-"
DEEPSPEECH_SCORER_EXT = '.scorer'
DEEPSPEECH_MODEL_EXT = ['.pb', '.pbmm']
DEFAULT_FRAMERATE = 16000

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

def vosk_transcriber(wf, rec):
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

def update_voskrecognizer(model_id, framerate):
    if loaded_models[model_id]['vocabulary']:
        loaded_models[model_id]['vosk-recognizer'] = vosk.KaldiRecognizer(loaded_models[model_id]['stt-model'], loaded_models[model_id]['framerate'], loaded_models[model_id]['vocabulary'])
    else:
        loaded_models[model_id]['vosk-recognizer'] = vosk.KaldiRecognizer(loaded_models[model_id]['stt-model'], loaded_models[model_id]['framerate'])


def make_runtime_voskrecognizer(model_id, vocabulary_json):
    try:
        vocab_list = json.loads(vocabulary_json)

        vocab_list.append("[unk]")
        vocab_text = json.dumps(vocab_list)

    except:
        raise HTTPException(status_code=400, detail="Cannot parse runtime vocabulary")

    try:
        temp_rec = vosk.KaldiRecognizer(loaded_models[model_id]['stt-model'], loaded_models[model_id]['framerate'], vocab_text)

        print("Runtime vocabulary set: %s"%vocab_list)
        return temp_rec
    except:
        raise HTTPException(status_code=500, detail="Cannot set runtime vocabulary")
    
        

def do_transcribe(model_id, input, runtime_vocab=None):
    #Wav read
    try:
        wf = wave.open(input.file, "rb")
    except:
        raise HTTPException(status_code=400, detail="Broken WAV")
        
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
        raise HTTPException(status_code=400, detail="Audio file not WAV format mono PCM.")

    framerate = wf.getframerate()
    inference_start = perf_counter()

    if loaded_models[model_id]['type'] == 'vosk':
        if framerate != loaded_models[model_id]['framerate']:
            loaded_models[model_id]['framerate'] = framerate
            print("Changing model %s's framerate to %i"%(model_id, framerate))

            update_voskrecognizer(model_id, framerate)

        if runtime_vocab:
            rec = make_runtime_voskrecognizer(model_id, runtime_vocab)
        else:
            rec = loaded_models[model_id]['vosk-recognizer']

        try:
            words = vosk_transcriber(wf, rec)
            transcript = " ".join([w["word"] for w in words])
        except:
            raise HTTPException(status_code=500, detail="Problem occured with vosk transcriber")
            
    elif loaded_models[model_id]['type'] == 'deepspeech':
        if 'framerate' in loaded_models[model_id] and loaded_models[model_id]['framerate'] != framerate:
            raise HTTPException(status_code=400, detail="Audio file not in framerate %i"%loaded_models[model_id]['framerate'])
        
        try:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
        except:
            raise HTTPException(status_code=500, detail="Problem reading audio")

        try:
            transcript = loaded_models[model_id]['stt-model'].stt(audio)
        except:
            raise HTTPException(status_code=500, detail="Problem occured with deepspeech transcriber")

        words = None #coqui stt does not support word alignment?

    inference_time = perf_counter() - inference_start

    #Postprocess (text)
    #...
    
    return words, transcript, inference_time

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
            if model['lang'] in language_codes:
                if alt_id:
                    model['lang-name'] = language_codes[model['lang']] + " (%s)"%alt_id
                else:
                    model['lang-name'] = language_codes[model['lang']]
            else:
                model['lang-name'] = "Unknown"
                print("WARNING: Source language code %s not defined in languages dict. This might break something."%model['lang'])

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

            if 'framerate' in model_config:
                model['framerate'] = model_config['framerate']
            else:
                model['framerate'] = DEFAULT_FRAMERATE



            if model_config['model_type'] == 'vosk':
                global vosk
                import vosk

                model['type'] = 'vosk'
                model['stt-model'] = vosk.Model(model_dir)

                #Load restricted vocabulary (if any)
                if os.path.exists(VOCABS_ROOT_DIR) and 'vocabulary' in model_config and model_config['vocabulary']:
                    vocab_path = os.path.join(VOCABS_ROOT_DIR, model_config['vocabulary'])
                    if not os.path.exists(vocab_path):
                        print("WARNING: Vocabulary path %s not found for model %s. Skipping vocabulary load."%(vocab_path, model_id))
                        continue

                    model['vocabulary'], model['vocabulary-size'] = read_vocabulary(vocab_path)
                    
                else:
                    model['vocabulary'] = None
                    model['vocabulary-size'] = 0

                if model['vocabulary']:
                    model['vosk-recognizer'] = vosk.KaldiRecognizer(model['stt-model'], model['framerate'], model['vocabulary'])
                else:
                    model['vosk-recognizer'] = vosk.KaldiRecognizer(model['stt-model'], model['framerate'])
                print("-vosk", end=" ") 
            elif model_config['model_type'] == 'deepspeech':
                global stt
                import stt
                model['type'] = 'deepspeech'
                model['vocabulary'] = None
                model['vocabulary-size'] = 0

                model_path_candidates = [f for f in os.listdir(model_dir) if os.path.splitext(f)[1] in DEEPSPEECH_MODEL_EXT]
                if len(model_path_candidates) != 1:
                    print("\nERROR: Can't find a unique model with extension .pb or .pbmm under model directory %s"%(model_dir))
                    continue

                model_path = os.path.join(model_dir, model_path_candidates[0])

                model['stt-model'] = stt.Model(model_path)

                print("-deepspeech", end=" ") 

                scorer_path_candidates = [f for f in os.listdir(model_dir) if f.endswith(DEEPSPEECH_SCORER_EXT)]
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

            print("Framerate: %i"%model['framerate'])
            if model['vocabulary']:
                print("Vocabulary size: %i"%model['vocabulary-size'])

            #All good, add model to the list
            loaded_models[model_id] = model
        
    return len(loaded_models)

    
#HTTP operations
class TranscriptionResponse(BaseModel):
    transcript: str
    time: float

class FullTranscriptionResponse(BaseModel):
    words: List
    transcript: str
    time: float

class LanguagesResponse(BaseModel):
    languages: Dict

@transcribe.post('/short', status_code=200)
async def transcribe_short_audio(lang: str = Form(...), file: UploadFile = File(...), alt: Optional[str] = Form(None), word_times:Optional[bool] = Form(False), vocabulary:Optional[str] = Form(None)) :
    model_id = get_model_id(lang, alt) 
    
    if not model_id in loaded_models:
        raise HTTPException(status_code=400, detail="Language %s is not supported."%model_id)

    if word_times and loaded_models[model_id]['type'] != 'vosk':
        raise HTTPException(status_code=400, detail="Model %s cannot give word timing information. Remove word_times flag."%model_id)

    if vocabulary and loaded_models[model_id]['type'] != 'vosk':
        raise HTTPException(status_code=400, detail="Model %s cannot take runtime vocabulary. Remove vocabulary specification."%model_id)
    
    words, transcript, time = do_transcribe(model_id, file, vocabulary)

    if word_times:
        response = FullTranscriptionResponse(words=words, transcript=transcript, time="%.3f"%time)
    else:
        response = TranscriptionResponse(transcript=transcript, time="%.3f"%time)

    return response


@transcribe.get('/', status_code=200)
async def languages():
    languages = {lang_code:loaded_models[lang_code]['lang-name'] for lang_code in loaded_models}
    return LanguagesResponse(languages=languages)


@transcribe.on_event("startup")
async def startup_event():
    no_models = await load_models(CONFIG_JSON_PATH)
    print("%i models loaded successfully"%no_models)

