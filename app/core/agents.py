from app.core.llm import generate_content
from app.core.prompts import (
    get_analysis_prompt,
    get_backend_prompt,
    get_business_rules_prompt,
    get_data_analysis_prompt,
    get_database_tables_prompt,
    get_documenter_prompt,
    get_orchestrator_analysis_prompt,
    get_orchestrator_prompt,
    get_pr_manager_prompt,
    get_qa_prompt,
)


class Agent:
    def __init__(self, name: str, system_prompt: str, model_name: str = "gemini-2.0-flash-exp"):
        self.name = name
        self.system_prompt = system_prompt
        self.model_name = model_name

    def run(self, input_text: str) -> str:
        """
        Runs the agent with the given input text.
        """
        print(f"[{self.name}] Processing...")
        return generate_content(
            prompt=input_text,
            system_instruction=self.system_prompt,
            model_name=self.model_name
        )


# Factory functions to create specific agents

def create_orchestrator_agent() -> Agent:
    return Agent(
        name="Orchestrator",
        system_prompt=get_orchestrator_prompt()
    )

def create_analyst_agent() -> Agent:
    return Agent(
        name="Analyst",
        system_prompt=get_analysis_prompt()
    )

def create_backend_agent() -> Agent:
    return Agent(
        name="Backend Engineer",
        system_prompt=get_backend_prompt()
    )

def create_data_analyst_agent() -> Agent:
    return Agent(
        name="Data Analyst",
        system_prompt=get_data_analysis_prompt()
    )

def create_documenter_agent() -> Agent:
    return Agent(
        name="Documenter",
        system_prompt=get_documenter_prompt()
    )

def create_qa_agent() -> Agent:
    return Agent(
        name="QA Engineer",
        system_prompt=get_qa_prompt()
    )

def create_pr_manager_agent() -> Agent:
    return Agent(
        name="PR Manager",
        system_prompt=get_pr_manager_prompt()
    )

# Specialized Agents based on specific context prompts

def create_orchestrator_analyst_agent() -> Agent:
    """Agent specialized in analyzing the orchestrator role itself."""
    return Agent(
        name="Orchestrator Analyst",
        system_prompt=get_orchestrator_analysis_prompt()
    )

def create_business_rules_agent() -> Agent:
    """Agent specialized in business rules."""
    return Agent(
        name="Business Rules Expert",
        system_prompt=get_business_rules_prompt()
    )

def create_database_expert_agent() -> Agent:
    """Agent specialized in the database schema."""
    return Agent(
        name="Database Expert",
        system_prompt=get_database_tables_prompt()
    )
