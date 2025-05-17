from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine, OperatorConfig, DeanonymizeEngine
from presidio_anonymizer.operators import Operator, OperatorType
from typing import Dict
import stanza
import os
from bot.config.piiMasker import analyzer, anonymizer
import time
import inspect
import re

# Initialize Stanza and configure it for Presidio
def setup_analyzer_with_stanza():
    # Download Stanza models if not already downloaded
    if not os.path.exists(os.path.expanduser('~/stanza_resources')):
        stanza.download('en')
    
    # Create configuration with Stanza
    configuration = {
        "nlp_engine_name": "stanza",
        "models": [{"lang_code": "en", "model_name": "en"}]
    }
    
    # Create NLP engine based on configuration
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()
    
    # Set up analyzer with the Stanza NLP engine
    registry = RecognizerRegistry()
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en"]
    )

# Create analyzer with Stanza
analyzer = setup_analyzer_with_stanza()

class InstanceCounterAnonymizer(Operator):
    """
    Anonymizer which replaces the entity value with an instance counter per entity.
    Uses case-insensitive matching to identify variations of the same name.
    """
    REPLACING_FORMAT = "<{entity_type}_{index}>"

    @staticmethod
    def normalize_name(text):
        """Normalize a name for better matching across variations."""
        # Convert to lowercase
        text = text.lower()
        # Remove leading/trailing whitespace
        text = text.strip()
        # Remove any periods (for abbreviated names)
        text = text.replace('.', '')
        return text

    def operate(self, text: str, params: Dict = None) -> str:
        """Anonymize the input text with context-aware numbering."""
        entity_type: str = params["entity_type"]
        # entity_mapping is a dict of dicts containing mappings per entity type
        entity_mapping: Dict[Dict:str] = params["entity_mapping"]
        
        # Track original occurrences for precise deanonymization
        original_occurrences = params.get("original_occurrences", {})

        # Special handling for PERSON entities
        if entity_type == "PERSON":
            # Normalize the name for better matching
            normalized_text = self.normalize_name(text)
            entity_mapping_for_type = entity_mapping.get(entity_type, {})
            
            # Check if this normalized name matches any existing name
            for original, placeholder in entity_mapping_for_type.items():
                if self.normalize_name(original) == normalized_text:
                    # Add this occurrence to the original_occurrences map for accurate deanonymization
                    if placeholder not in original_occurrences:
                        original_occurrences[placeholder] = []
                    original_occurrences[placeholder].append(text)
                    return placeholder
                # Check if current name is contained in a known full name or vice versa
                # For handling "John" vs "John Doe"
                elif self.normalize_name(original) in normalized_text or normalized_text in self.normalize_name(original):
                    # Check if they are likely the same person (not just coincidental substring)
                    if len(normalized_text) > 2 and len(self.normalize_name(original)) > 2:
                        # Add this occurrence to the original_occurrences map
                        if placeholder not in original_occurrences:
                            original_occurrences[placeholder] = []
                        original_occurrences[placeholder].append(text)
                        return placeholder
            
            # If no match found, create a new entry
            if not entity_mapping_for_type:
                new_text = self.REPLACING_FORMAT.format(
                    entity_type=entity_type,
                    index=1  # Start from 1 for better readability
                )
                entity_mapping[entity_type] = {text: new_text}
                # Initialize in original_occurrences
                original_occurrences[new_text] = [text]
            else:
                previous_index = len(entity_mapping_for_type)
                new_text = self.REPLACING_FORMAT.format(
                    entity_type=entity_type,
                    index=previous_index + 1
                )
                entity_mapping[entity_type][text] = new_text
                # Initialize in original_occurrences
                original_occurrences[new_text] = [text]
            
            return new_text
        
        # For non-PERSON entities, use basic case-insensitive matching
        else:
            # Normalize text for case-insensitive matching
            normalized_text = text.lower()
            entity_mapping_for_type = entity_mapping.get(entity_type, {})
            
            # Check if this text (case-insensitive) has already been mapped
            for original, placeholder in entity_mapping_for_type.items():
                if original.lower() == normalized_text:
                    # Add this occurrence
                    if placeholder not in original_occurrences:
                        original_occurrences[placeholder] = []
                    original_occurrences[placeholder].append(text)
                    return placeholder
            
            if not entity_mapping_for_type:
                new_text = self.REPLACING_FORMAT.format(
                    entity_type=entity_type,
                    index=1  # Start from 1 for better readability
                )
                entity_mapping[entity_type] = {text: new_text}
                original_occurrences[new_text] = [text]
            else:
                previous_index = len(entity_mapping_for_type)
                new_text = self.REPLACING_FORMAT.format(
                    entity_type=entity_type,
                    index=previous_index + 1
                )
                entity_mapping[entity_type][text] = new_text
                original_occurrences[new_text] = [text]
            
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

    # Pre-process text to normalize case variations of names
    # This helps with matching "John" and "john" as the same entity
    text_for_analysis = text
    
    # Analyze text
    results = analyzer.analyze(
        text=text_for_analysis,
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
        
        # Track original text forms for each placeholder
        original_occurrences = {}
        
        # Anonymize with context awareness
        anonymized_result = anonymizer_engine.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("entity_counter", {
                    "entity_mapping": entity_mapping,
                    "original_occurrences": original_occurrences
                })
            }
        )
        
        # Add the original occurrences to the entity_mapping
        entity_mapping["_original_occurrences"] = original_occurrences
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
    
    # Get original occurrences in order
    original_occurrences = entity_mapping.get("_original_occurrences", {})
    
    # Create pattern to match all entity placeholders like <ENTITY_TYPE_INDEX>
    pattern = r"<([A-Z_]+)_(\d+)>"
    
    # Track placeholder positions in the anonymized text
    placeholder_positions = []
    for match in re.finditer(pattern, anonymized_text):
        placeholder = match.group(0)
        position = match.start()
        placeholder_positions.append((placeholder, position))
    
    # Sort by position to maintain the order of appearance
    placeholder_positions.sort(key=lambda x: x[1])
    
    # Prepare a mapping for each placeholder instance to its original text form
    placeholder_to_original = {}
    for placeholder in set(ph for ph, _ in placeholder_positions):
        # Check if we have occurrence data
        if original_occurrences and placeholder in original_occurrences:
            # Get all recorded original forms of this placeholder
            occurrences = original_occurrences[placeholder]
            placeholder_to_original[placeholder] = occurrences
        else:
            # Fall back to the regular entity mapping
            for entity_type, mapping in entity_mapping.items():
                if entity_type == "_original_occurrences":
                    continue
                for original, ph in mapping.items():
                    if ph == placeholder:
                        placeholder_to_original[placeholder] = [original]
                        break
    
    # Replace each placeholder with its corresponding original text form
    result = anonymized_text
    occurrence_counts = {}  # Track how many times we've seen each placeholder
    
    for placeholder, _ in placeholder_positions:
        if placeholder not in placeholder_to_original:
            continue
            
        # Get the original forms and select the appropriate one
        original_forms = placeholder_to_original[placeholder]
        occurrence_idx = occurrence_counts.get(placeholder, 0)
        
        # Use the original form at this occurrence index, or the last one if we've run out
        if occurrence_idx < len(original_forms):
            original_value = original_forms[occurrence_idx]
        else:
            original_value = original_forms[-1]
            
        # Update the occurrence count
        occurrence_counts[placeholder] = occurrence_idx + 1
            
        # Replace just this occurrence of the placeholder
        result = result.replace(placeholder, original_value, 1)
    
    return result

if __name__ == "__main__":
    sample_text = """
    Hi, I am John Doe. My email is john.doe@example.com and phone is 123-456-7890. My friend is Lekhana, she is cute little girl, her email is hanji@gmail.com and her phone is 91-8988888888. john smith owes me a thanks. John sarkar is my new friend.
    """

    # Anonymize text and get entity mapping
    anonymized, entity_map = anonymize_pii(sample_text, context_aware=True)

    print("Original Text:\n", sample_text)
    print("\nAnonymized Text:\n", anonymized)
    
    # Deanonymize using the entity mapping
    deanonymized = de_anonymize_pii(anonymized, entity_map)
    print("\nDeanonymized Text:\n", deanonymized)