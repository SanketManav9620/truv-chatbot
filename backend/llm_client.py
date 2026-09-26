import os
import logging
from typing import Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger("regulatory_llm_client")

def call_gemini(prompt: str, system: Optional[str] = None, client: Optional[genai.Client] = None) -> str:
    """
    Thin wrapper around the Google Gemini API to execute prompt completions.
    
    Args:
        prompt (str): User prompt string.
        system (str, optional): System prompt string.
        client (genai.Client, optional): Gemini client instance override.
        
    Returns:
        str: Response text from Gemini API, or empty string if key is missing/invalid.
    """
    try:
        if client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key or api_key == "your_gemini_api_key_here":
                logger.warning("GEMINI_API_KEY is missing from environment/backend/.env.")
                return ""
            client = genai.Client(api_key=api_key)
            
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        config = None
        if system:
            config = types.GenerateContentConfig(system_instruction=system)

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

        if response and response.text:
            return response.text.strip()
        return ""
    except Exception as err:
        logger.error(f"Gemini API call failed: {err}")
        return ""

# Alias call_claude to call_gemini for backwards compatibility
call_claude = call_gemini
