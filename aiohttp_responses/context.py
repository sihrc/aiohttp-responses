import typing as t

ValueType = t.TypeVar("ValueType")


class Context(t.Generic[ValueType]):
    prev_value: ValueType
    current_value: ValueType

    def __init__(self, value: ValueType):
        self.current_value = value

    def set(self, value: ValueType):
        if hasattr(self, "prev_value"):
            raise ValueError("Context already activated")
        self.prev_value, self.current_value = self.current_value, value

    def reset(self):
        self.current_value = self.prev_value
        if hasattr(self, "prev_value"):
            del self.prev_value

    @property
    def value(self) -> ValueType:
        return self.current_value
