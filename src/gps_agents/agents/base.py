"""Base agent class for GPS genealogy agents."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Configuration for an agent."""

    name: str
    llm_provider: str = "anthropic"  # "anthropic" or "openai"
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.1
    max_tokens: int = 4096


class BaseAgent(ABC):
    """Abstract base class for all GPS agents."""

    name: str = "base"
    prompt_file: str = ""
    default_provider: str = "anthropic"  # Override in subclasses

    def __init__(self, config: AgentConfig | None = None) -> None:
        """Initialize the agent.

        Args:
            config: Agent configuration
        """
        self.config = config or AgentConfig(
            name=self.name,
            llm_provider=self.default_provider,
        )
        self._llm = None
        self._system_prompt: str | None = None

    def _get_llm(self):
        """Get the LLM instance, creating if needed."""
        if self._llm is not None:
            return self._llm

        if self.config.llm_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            self._llm = ChatAnthropic(
                model=self.config.model or "claude-sonnet-4-20250514",
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        else:
            from langchain_openai import ChatOpenAI

            self._llm = ChatOpenAI(
                model=self.config.model or "gpt-4-turbo-preview",
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

        return self._llm

    def _load_prompt(self) -> str:
        """Load the agent's system prompt from file."""
        if self._system_prompt is not None:
            return self._system_prompt

        # Find prompts directory
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"

        # Load root system prompt
        root_prompt = ""
        root_file = prompts_dir / "system_root.txt"
        if root_file.exists():
            root_prompt = root_file.read_text()

        # Load agent-specific prompt
        agent_prompt = ""
        if self.prompt_file:
            agent_file = prompts_dir / self.prompt_file
            if agent_file.exists():
                agent_prompt = agent_file.read_text()

        self._system_prompt = f"{root_prompt}\n\n{agent_prompt}".strip()
        return self._system_prompt

    async def invoke(self, message: str, context: dict[str, Any] | None = None) -> str:
        """Invoke the agent with a message.

        Args:
            message: The input message
            context: Optional context dict

        Returns:
            Agent's response
        """
        llm = self._get_llm()
        system_prompt = self._load_prompt()

        # Add context to message if provided
        if context:
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            message = f"Context:\n{context_str}\n\nTask:\n{message}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=message),
        ]

        response = await llm.ainvoke(messages)
        return response.content

    @abstractmethod
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process the agent's task within the workflow.

        Args:
            state: Current workflow state

        Returns:
            Updated state
        """
        pass
