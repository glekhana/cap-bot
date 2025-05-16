from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine, OperatorConfig
from bot.config.piiMasker import analyzer,anonymizer

def anonymize_pii(text, entity_types=None):
    """
    Anonymize PII in text using Presidio.

    Args:
        text (str): Text to anonymize
        entity_types (list, optional): Specific entity types to anonymize.
                                     If None, anonymizes all detected entities.

    Returns:
        str: Anonymized text
    """


    # Define entity types to look for (or use default if None)
    if entity_types is None:
        entity_types = [
            "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
            "CREDIT_CARD", "US_SSN", "US_PASSPORT",
            "LOCATION", "IP_ADDRESS", "URL", "DOMAIN_NAME"
        ]

    # Analyze text
    results = analyzer.analyze(
        text=text,
        language="en",
        entities=entity_types,
        score_threshold=0.5
    )

    # Define anonymization operators
    operators = {
        "PERSON": OperatorConfig("replace", {"new_value": "<PERSON>"}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL>"}),
        "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE>"}),
        "CREDIT_CARD": OperatorConfig("replace", {"new_value": "<CREDIT_CARD>"}),
        "US_SSN": OperatorConfig("replace", {"new_value": "<SSN>"}),
        "US_PASSPORT": OperatorConfig("replace", {"new_value": "<PASSPORT>"}),
        "LOCATION": OperatorConfig("replace", {"new_value": "<LOCATION>"}),
        "IP_ADDRESS": OperatorConfig("replace", {"new_value": "<IP>"}),
        "URL": OperatorConfig("replace", {"new_value": "<URL>"}),
        "DOMAIN_NAME": OperatorConfig("replace", {"new_value": "<DOMAIN>"}),
    }

    # Anonymize identified entities
    anonymized_result = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators
    )

    return anonymized_result.text

# if __name__ == "__main__":
#     sample_text = """
#     Hi, I am John Doe. My email is john.doe@example.com and phone is 123-456-7890.
#     """
#
#     anonymized = anonymize_pii(sample_text)
#
#     print("Original Text:\n", sample_text)
#     print("\nAnonymized Text:\n", anonymized)