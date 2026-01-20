from functools import lru_cache
from pathlib import Path

# Define the path to the prompts directory relative to this file
# app/core/prompts.py -> app/core/ -> app/ -> root -> prompts/
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def get_prompts_dir() -> Path:
    """Returns the absolute path to the prompts directory."""
    return PROMPTS_DIR


def list_prompts() -> list[str]:
    """Returns a list of all markdown prompt filenames in the prompts directory."""
    if not PROMPTS_DIR.exists():
        return []
    return [f.name for f in PROMPTS_DIR.glob("*.md")]


def get_prompt_content(filename: str) -> str:
    """
    Reads and returns the content of a specific prompt file.
    
    Args:
        filename: The name of the file (e.g., '00-orquestador.md')
        
    Returns:
        The content of the file as a string.
        
    Raises:
        FileNotFoundError: If the file does not exist.
    """
    file_path = PROMPTS_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    
    return file_path.read_text(encoding="utf-8")


# Specific getters for known prompts for easier access and type safety

@lru_cache
def get_orchestrator_prompt() -> str:
    """Returns the content of 00-orquestador.md"""
    return get_prompt_content("00-orquestador.md")


@lru_cache
def get_analysis_prompt() -> str:
    """Returns the content of 01-analisis.md"""
    return get_prompt_content("01-analisis.md")


@lru_cache
def get_backend_prompt() -> str:
    """Returns the content of 02-backend.md"""
    return get_prompt_content("02-backend.md")


@lru_cache
def get_data_analysis_prompt() -> str:
    """Returns the content of 03-analisis_datos.md"""
    return get_prompt_content("03-analisis_datos.md")


@lru_cache
def get_documenter_prompt() -> str:
    """Returns the content of 04-documentador.md"""
    return get_prompt_content("04-documentador.md")


@lru_cache
def get_qa_prompt() -> str:
    """Returns the content of 05-qa.md"""
    return get_prompt_content("05-qa.md")


@lru_cache
def get_php_to_python_prompt() -> str:
    """Returns the content of 06-phpTopython.md"""
    return get_prompt_content("06-phpTopython.md")


@lru_cache
def get_pr_manager_prompt() -> str:
    """Returns the content of 07-pr_manager.md"""
    return get_prompt_content("07-pr_manager.md")


@lru_cache
def get_orchestrator_analysis_prompt() -> str:
    """Returns the content of analisis_orquestador.md"""
    return get_prompt_content("analisis_orquestador.md")


@lru_cache
def get_business_rules_prompt() -> str:
    """Returns the content of reglas_negocio.md"""
    return get_prompt_content("reglas_negocio.md")


@lru_cache
def get_database_tables_prompt() -> str:
    """Returns the content of tablas_cro_database.md"""
    return get_prompt_content("tablas_cro_database.md")
