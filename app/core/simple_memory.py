from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ChatMemory:
    """Small in-process message buffer used as a drop-in for LangChain memory."""

    messages: List[Dict[str, str]] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_ai_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        self.messages.clear()


class ConversationBufferMemory:
    """Lightweight replacement for LangChain's ConversationBufferMemory.

    The app only needs a buffer that can store paired user/assistant messages and
    expose a chat_memory object with add_user_message/add_ai_message methods.
    """

    def __init__(self, return_messages: bool = True, memory_key: str = "chat_history", output_key: str | None = None):
        self.return_messages = return_messages
        self.memory_key = memory_key
        self.output_key = output_key
        self.chat_memory = ChatMemory()

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        input_text = next((str(value) for value in inputs.values() if value is not None), "")
        output_text = next((str(value) for value in outputs.values() if value is not None), "")

        if input_text:
            self.chat_memory.add_user_message(input_text)
        if output_text:
            self.chat_memory.add_ai_message(output_text)

    def clear(self) -> None:
        self.chat_memory.clear()
