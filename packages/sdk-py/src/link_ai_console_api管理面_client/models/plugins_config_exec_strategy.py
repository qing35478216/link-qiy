from enum import StrEnum


class PluginsConfigExecStrategy(StrEnum):
    KNOWLEDGEFIRST = "knowledgeFirst"
    PARALLEL = "parallel"
    PLUGINFIRST = "pluginFirst"

    def __str__(self) -> str:
        return str(self.value)
