from langfuse import Langfuse 
from datetime import datetime
from config.settings import settings
from config.logging_config import logger
from langfuse.langchain import CallbackHandler

class AgentPrompt_Library:
    def __init__(self):
        """
        Manages the strict agent instructions to incorporate the agent capabilities 
        with the intended task for which the agent is designed.
        """
        self.langfuse_handler = CallbackHandler()

        self.langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_BASE_URL
        )

        # 1. Fetch the prompt from the registry (letting it default to production)

        cached_prompt = self.langfuse.get_prompt("erpnext_entity_mapping_prompt_version_2")
        
        # 2. Get the actual current year from the system clock
        active_year = str(datetime.now().year)
        
        # 3. Compile the prompt by passing the variable into the template
        self.orchestrator_prompt = cached_prompt.compile(current_year=active_year)


   
