from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
import os
import stanza
class PIIMasker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PIIMasker, cls).__new__(cls)

            # Use Stanza for better NLP capabilities including coreference resolution
            configuration = {
                "nlp_engine_name": "stanza",
                "models": [{"lang_code": "en", "model_name": "en"}]
            }

            # Ensure Stanza is installed and model is downloaded
            try:
                # Download the English model if not already downloaded
                if not os.path.exists(os.path.expanduser('~/stanza_resources')):
                    stanza.download('en', processors='tokenize,mwt,pos,lemma,depparse,ner')
            except ImportError:
                print("Stanza not found. Please install it with 'pip install stanza'.")
                # Fall back to spaCy if Stanza installation fails
                configuration = {
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}]
                }

            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()

            registry = RecognizerRegistry()

            cls._instance.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                registry=registry,
                supported_languages=["en"]
            )

            cls._instance.anonymizer = AnonymizerEngine()

        return cls._instance

# Usage
presidio = PIIMasker()
analyzer = presidio.analyzer
anonymizer = presidio.anonymizer
