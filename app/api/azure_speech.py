import requests, os
from .settings import *
from datetime import datetime
import azure.cognitiveservices.speech as speechsdk
from moviepy.editor import *


# Creates an instance of a speech config with specified subscription key and service region.
# Replace with your own subscription key and service region (e.g., "westus").
speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SERVICE_REGION)



def convert_to_wav(path):
    # try:
    filename, file_extension = os.path.splitext(path.split('?')[0])
    filename = filename.split(os.path.sep)[-1]
    audio_file = f'{STATIC_FOLDER}/{filename}.wav'

    if os.path.exists(audio_file):
        return None, None

    audioclip = AudioFileClip(path)
    audioclip.write_audiofile(audio_file)
    return audio_file, f"{filename}.wav"
    # except:
    #     return False


def speech_to_text(path, lang):
    # audio_file, filename = convert_to_wav(path)

    # import pdb; pdb.set_trace()
    langs_map = {
        'swh': 'sw-KE',
        'eng': 'en-KE'
    }

    audio_file = path
    if audio_file:
        audio_config = speechsdk.audio.AudioConfig(filename=audio_file)

        # Creates a recognizer with the given settings
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config,language=langs_map[lang] ,audio_config=audio_config)


        # Starts speech recognition, and returns after a single utterance is recognized. The end of a
        # single utterance is determined by listening for silence at the end or until a maximum of 15
        # seconds of audio is processed.  The task returns the recognition text as result. 
        # Note: Since recognize_once() returns only a single utterance, it is suitable only for single
        # shot recognition like command or query. 
        # For long-running multi-utterance recognition, use start_continuous_recognition() instead.
        result = speech_recognizer.recognize_once()

        # Checks result.
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print("Recognized: {}".format(result.text))
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            print("No speech could be recognized: {}".format(result.no_match_details))
            return result.no_match_details
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print("Speech Recognition canceled: {}".format(cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                print("Error details: {}".format(cancellation_details.error_details))

            return cancellation_details.error_details

    

    
    return None

        



def text_to_speech(path,text,lang):

    langs_map = {
        'swh': 'sw-KE',
        'eng': 'en-KE'
    }

    filename, file_extension = os.path.splitext(path)
    output_file = f"{filename}_response.wav"
    audio_file = f'{STATIC_FOLDER}/{output_file}'
    # Creates a speech synthesizer using the default speaker as audio output.
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

    # Synthesizes the received text to speech.
    # The synthesized speech is expected to be heard on the speaker with this line executed.
    result = speech_synthesizer.speak_text_async(text).get()

    response = {
        "message":"",
        "file": "",
        "status": 400
    }

    with open(audio_file, 'wb') as f_:
        f_.write(result.audio_data)

    # Checks result.
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print("Speech synthesized to speaker for text [{}]".format(text))
        response = {
                "message":"synthesized",
                "file": output_file,
                "status": 200
            }
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        response = {
                "message":cancellation_details.reason,
                "text": "",
                "status": 400
            }
    
    return response