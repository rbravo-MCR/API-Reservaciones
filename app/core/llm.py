import google.generativeai as genai

from app.config import get_settings

_configured = False

def _configure_genai():
    global _configured
    if _configured:
        return
    
    settings = get_settings()
    if not settings.google_api_key:
        # Warn or raise depending on strictness. For now, we'll just print a warning.
        print("WARNING: GOOGLE_API_KEY not found in settings. LLM features will fail.")
        return

    genai.configure(api_key=settings.google_api_key)
    _configured = True


def generate_content(
    prompt: str,
    system_instruction: str | None = None,
    model_name: str = "gemini-2.0-flash-exp",
) -> str:
    """
    Generates content using Google Gemini.
    
    Args:
        prompt: The user prompt or input text.
        system_instruction: Optional system instruction (persona).
        model_name: The model to use. Defaults to 'gemini-2.0-flash-exp'.
        
    Returns:
        The generated text response.
    """
    _configure_genai()
    
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # In a real app, you might want to log this properly
        return f"Error generating content: {str(e)}"
