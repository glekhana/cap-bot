from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine, OperatorConfig, DeanonymizeEngine
from presidio_anonymizer.operators import Operator, OperatorType
from typing import Dict
from bot.config.piiMasker import analyzer, anonymizer
import time
import inspect
import re

class InstanceCounterAnonymizer(Operator):
    """
    Anonymizer which replaces the entity value with an instance counter per entity.
    """
    REPLACING_FORMAT = "<{entity_type}_{index}>"

    def operate(self, text: str, params: Dict = None) -> str:
        """Anonymize the input text with context-aware numbering."""
        entity_type: str = params["entity_type"]
        # entity_mapping is a dict of dicts containing mappings per entity type
        entity_mapping: Dict[Dict:str] = params["entity_mapping"]

        entity_mapping_for_type = entity_mapping.get(entity_type, {})
        
        if not entity_mapping_for_type:
            new_text = self.REPLACING_FORMAT.format(
                entity_type=entity_type,
                index=1  # Start from 1 for better readability
            )
            entity_mapping[entity_type] = {text: new_text}
        else:
            if text in entity_mapping_for_type:
                return entity_mapping_for_type[text]
            
            previous_index = len(entity_mapping_for_type)
            new_text = self.REPLACING_FORMAT.format(
                entity_type=entity_type,
                index=previous_index + 1
            )
            entity_mapping[entity_type][text] = new_text
        
        return new_text

    def validate(self, params: Dict = None) -> None:
        """Validate operator parameters."""
        if "entity_mapping" not in params:
            raise ValueError("An input Dict called `entity_mapping` is required.")
        if "entity_type" not in params:
            raise ValueError("An entity_type param is required.")

    def operator_name(self) -> str:
        return "entity_counter"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize

class InstanceCounterDeanonymizer(Operator):
    """
    Deanonymizer which replaces the unique identifier with the original text.
    """
    def operate(self, text: str, params: Dict = None) -> str:
        """Deanonymize the input text."""
        entity_type: str = params["entity_type"]
        # entity_mapping is a dict of dicts containing mappings per entity type
        entity_mapping: Dict[Dict:str] = params["entity_mapping"]

        if entity_type not in entity_mapping:
            raise ValueError(f"Entity type {entity_type} not found in entity mapping!")
            
        for original_value, placeholder in entity_mapping[entity_type].items():
            if placeholder == text:
                return original_value
                
        return text  # Return original if no mapping found

    def validate(self, params: Dict = None) -> None:
        """Validate operator parameters."""
        if "entity_mapping" not in params:
            raise ValueError("An input Dict called `entity_mapping` is required.")
        if "entity_type" not in params:
            raise ValueError("An entity_type param is required.")

    def operator_name(self) -> str:
        return "entity_counter_deanonymizer"

    def operator_type(self) -> OperatorType:
        return OperatorType.Deanonymize

def anonymize_pii(text, entity_types=None, context_aware=True):
    """
    Anonymize PII in text using Presidio.

    Args:
        text (str): Text to anonymize
        entity_types (list, optional): Specific entity types to anonymize.
                                     If None, anonymizes all detected entities.
        context_aware (bool): If True, maintains context by numbering instances
                             of the same entity type differently.

    Returns:
        tuple: (anonymized_text, entity_mapping) where entity_mapping can be used for deanonymization
    """

    start_time = time.time()
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

    if context_aware:
        # Create a custom anonymizer engine with the context-aware operator
        anonymizer_engine = AnonymizerEngine()
        anonymizer_engine.add_anonymizer(InstanceCounterAnonymizer)
        
        # Create a mapping between entity types and values
        entity_mapping = {}
        
        # Anonymize with context awareness
        anonymized_result = anonymizer_engine.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("entity_counter", {"entity_mapping": entity_mapping})
            }
        )
    else:
        # Define simple anonymization operators (original behavior)
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
        entity_mapping = {}  # No mapping for simple anonymization
    
    end_time = time.time() - start_time
    curframe = inspect.currentframe()
    calframe = inspect.getouterframes(curframe, 2)

    print('caller name:', calframe[1][3])
    print("--- %s conversation seconds ---" % (time.time() - start_time))
    
    # Return both the anonymized text and the entity mapping for potential deanonymization
    return anonymized_result.text, entity_mapping

def de_anonymize_pii(anonymized_text, entity_mapping):
    """
    Deanonymize text that was previously anonymized with context-aware anonymization.
    
    Args:
        anonymized_text (str): The anonymized text to restore
        entity_mapping (dict): Mapping from original values to anonymized placeholders
                              created during anonymization
    
    Returns:
        str: Deanonymized text with original values restored
    """
    if not entity_mapping:
        return anonymized_text  # Nothing to deanonymize
    
    # Create pattern to match all entity placeholders like <ENTITY_TYPE_INDEX>
    pattern = r"<([A-Z_]+)_(\d+)>"
    
    # Function to replace each matched placeholder with its original value
    def replace_with_original(match):
        entity_type = match.group(1)
        placeholder = match.group(0)  # The full match: <ENTITY_TYPE_INDEX>
        
        if entity_type not in entity_mapping:
            return placeholder  # Keep as is if entity type not in mapping
        
        # Find the original value for this placeholder
        for original_value, mapped_placeholder in entity_mapping[entity_type].items():
            if mapped_placeholder == placeholder:
                return original_value
        
        # If no mapping found, keep the placeholder
        return placeholder
    
    # Replace all placeholders with their original values
    deanonymized_text = re.sub(pattern, replace_with_original, anonymized_text)
    return deanonymized_text

if __name__ == "__main__":
    sample_text = """
    Hi, I am John Doe. My email is john.doe@example.com and phone is 123-456-7890. My friend is Lekhana, she is cute little girl, her email is hanji@gmail.com and her phone is 91-8988888888. Lekhana owes me a thanks.
    """

    # Anonymize text and get entity mapping
    anonymized, entity_map = anonymize_pii(sample_text, context_aware=True)

    print("Original Text:\n", sample_text)
    print("\nAnonymized Text:\n", anonymized)
    
    # Deanonymize using the entity mapping
    deanonymized = de_anonymize_pii(anonymized, entity_map)
    print("\nDeanonymized Text:\n", deanonymized)