
import joblib
import re, pdb
import spacy
from spacy_langdetect import LanguageDetector
from spacy.language import Language
    


langiso2iso = {
    'swa': 'swh',
    'eng': 'eng'
}

eng_pattern = re.compile('^((okay|y|yes|no way|hi)([,?.!-=:;*]*?))$',re.I)
swh_pattern = re.compile('^((jambo|fiti|do ivo|habari|asanti|asante|ahsanti|ahsante|bora|eeh)([,?.!-=:;*]*?))$',re.I)

model = joblib.load("/app/app/api/lidentifier-eng-swa.sav")


def regex_classifier(message):

    if re.search(pattern=eng_pattern, string=message):
        return 'eng'
    if re.search(pattern=swh_pattern, string=message):
        return 'swh'

    return None

def chooser(message):

    # obj = regex_classifier(message)
    # if obj:
    #     detected_lang = obj
    # else:
    detected_lang = model.predict([message])[0]
    # detected_lang = langiso2iso[detected_lang]

    print('detected_lang ==================', detected_lang)
    
    return detected_lang


def get_lang_detector(nlp, name):
    return LanguageDetector()


def chooser_spacy(message):
    nlp = spacy.load('en_core_web_sm')
    Language.factory("language_detector", func=get_lang_detector)
    nlp.add_pipe('language_detector', last=True)
    doc = nlp(message)
    # document level language detection. Think of it like average language of the document!

    

    score = doc._.language['score']
    detected_lang = 'eng'

    print(doc._.language)

    if score < 0.95:
        detected_lang = 'swh'


    print('detected_lang ==================', detected_lang)

    return  detected_lang



