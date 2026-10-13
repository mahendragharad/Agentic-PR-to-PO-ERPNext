from langchain_groq import ChatGroq
from config.settings import settings

class LLMProvider :
    """
    Production-grade LLM Service Factory Provider.
    Exposes stateless, isolated client engines configured by task profiles.
    """

    @staticmethod
    def get_extraction_engine() -> ChatGroq :
        """
        Returns a low-temperature, highly deterministic engine optimized 
        for structured tool schema parsing, entity extraction, and self-healing.
        """

        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.model_name,
            temperature=0.0,
            max_retries=3
        )

    @staticmethod
    def get_conversational_engine() -> ChatGroq :
        """
        Returns a warmer engine optimized for synthesis, conversational dialogue, 
        and text explanations.
        """

        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.model_name,
            temperature=0.5                # Allows normal fluid speech synthesis patterns
        )