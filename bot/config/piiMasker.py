from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

class PIIMasker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PIIMasker, cls).__new__(cls)

            # Correct configuration passed as `nlp_configuration`
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}]
            }

            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()

            registry = RecognizerRegistry()

            cls._instance.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                registry=registry
            )

            cls._instance.anonymizer = AnonymizerEngine()

        return cls._instance

# Usage
presidio = PIIMasker()
analyzer = presidio.analyzer
anonymizer = presidio.anonymizer
