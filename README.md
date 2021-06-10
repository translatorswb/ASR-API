# ASR-API
TWB's API for serving automatic speech recognition (ASR) models. It currently serves two types of models: Kaldi and Deepspeech. 

## Loading models

### Where to get ASR models?

- **Kaldi-based** models can be found at [Alpha Cepei's website](https://alphacephei.com/vosk/models). 
- **Deepspeech-based** models can be found at [Coqui's website](https://coqui.ai/models/).

### How to integrate models?

1) Place the model you want into a folder under `models` directory
2) Specify it in the configuration file. 

#### Configuration file

Model configurations are specified in a JSON file named `config.json`. An example configuration file looks like this:

```
{
    "languages":{"<lang-code>":"<language-name>", "en":"English", "bn":"Bengali"},
    "models": [
        {
            "lang": "<lang-code>",
            "alt": "<optional-alternative-tag>"
            "model_type": "<vosk or deepspeech>",
            "model_path": "<model-directory>",
            "vocabulary": "<vocabulary-file-path>",
            "load": <true or false for loading at runtime>
        }
     }
}
```

##### Field speficiations:

- **`languages`**: a dictionary used for mapping language codes to language names.
- **`models`**: a list containing specifications of models available in the system. 
- **`lang`**: language code of the model. This will be the main model label used in API calls.
- **`alt`**: an optional extra label for the model. For example, if you have alternative models for a language, you should use this tag for the system to differentiate between them.
- **`model_type`**: type of model. 'vosk' if Kaldi-based 'deepspeech' if Deepspeech based.
- **`model_path`**: directory where the model files are stored. This directory should be put under `models` directory. 
- **`vocabulary`**: an optional text file containing words that the ASR will be conditioned to recognize (_works only with vosk type models_)
- **`load`**: if set to false, model will be skipped during loading

##### Vocabulary restriction

If your application works in a restricted domain, you can specify a vocabulary file. To do that, make a text file containing all the words that you can possibly recognize line by line, place it under `vocabularies` folder and speficy the filename using `vocabulary` field in the model specification. 

##### Example model configuration and vocabulary for recognizing English digits

Let's say we want to build a lightweight API that serves to recognize numbers from 0 to 9. What we should do is: 

1. Download or clone this repository (`git clone https://github.com/translatorswb/ASR-API.git`)
2. Download the [lightweight English model from VOSK](http://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip)
3. Extract its contents to `models` directory. 
4. Create a vocabulary file in `vocabularies/english-digits.txt` with the following content:

```
zero
one
two
three
four
five
six
seven
eight
nine

```

5. Add the model specification to `config.json`

```
{
    "languages":{"en":"English"},
    "models": [
        {
            "lang": "en",
            "alt": "digits"
            "model_type": "vosk",
            "model_path": "vosk-model-small-en-us-0.15",
            "vocabulary": "english-digits.txt"
        }
     }
}
```

## Build and run

### Local running for testing (Tested on Linux)

Set the environment variables:
```
MT_API_CONFIG=config.json
MODELS_ROOT=models
VOCABS_ROOT=vocabularies
```
Install required libraries:
```
pip install -r requirements.txt
```

Run with unicorn:
```
uvicorn app.main:app --reload --port 8010
```

`run_local.sh` script can also be called to run quickly once requirements are installed.

### Run it as a docker-container (recommended)

``` 
docker-compose build
docker-compose up
```

## Sample requests and responses

### Simple transcription request

Transcription requests take in a mono PCM WAVE format file. Note that Deepspeech models usually require a certain sampling rate. 

#### Request with cURL
```
curl -L -X POST 'http://localhost:8010/transcribe/short' -F 'file=@"my_audio.wav"' -F 'lang="en"'
```

#### Transcription response

```
{  "transcript": "good day madam" }
```

### Full transcription request (only with vosk models)

Full transcription request can be used for getting word timing information. 

#### Request with cURL
```
curl -L -X POST 'http://localhost:8010/transcribe/short' -F 'file=@"my_audio.wav"' -F 'lang="en"' -F 'time="True"' -F 'alt="digits"'
```

#### Transcription response

```
{
    "words": [
        {
            "conf": 1.0,
            "end": 1.14,
            "start": 0.6,
            "word": "one"
        },
        {
            "conf": 1.0,
            "end": 1.89,
            "start": 1.35,
            "word": "three"
        },
        {
            "conf": 1.0,
            "end": 2.58,
            "start": 2.1,
            "word": "one"
        },
        {
            "conf": 1.0,
            "end": 3.39,
            "start": 2.97,
            "word": "two"
        }
    ],
    "transcript": "one three one two"
}
```

### Retrieve languages

Retrieves languages supported by the API.

#### cURL

```
curl -L -X GET 'http://localhost:8010/transcribe'
```

### Retrieve languages response

```
{
    "languages": {
        "en": "English",
        "en-digits": "English (digits)"
    }
}
```

