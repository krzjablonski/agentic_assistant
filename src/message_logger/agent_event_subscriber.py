from abc import ABC, abstractmethod


class AgentEventSubscriber(ABC):
    @abstractmethod
    def on_event(self, event: "AgentEvent") -> None:
        pass
