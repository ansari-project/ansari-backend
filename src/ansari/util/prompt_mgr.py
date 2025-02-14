# This file aims to provide prompt-related functions that can be used across the codebase.
# Specifically, it load prompts (from resources/) and manage them for Ansari agent.

from pathlib import Path

from pydantic import BaseModel


class Prompt(BaseModel):
    file_path: str
    cached: str | None = None
    hot_reload: bool = True

    def render(self, **kwargs) -> str:
        if (self.cached is None) or (self.hot_reload):
            with open(self.file_path) as f:
                self.cached = f.read()
        return self.cached.format(**kwargs)


class PromptMgr:
    def get_resource_path(filename):
        # Get the directory of the current script
        script_dir = Path(__file__).resolve()
        # Construct the path to the resources directory
        resources_dir = script_dir.parent.parent / "resources"
        # Construct the full path to the resource file
        path = resources_dir / filename
        return path

    def __init__(self, hot_reload: bool = True, src_dir: str = str(get_resource_path("prompts"))):
        """Creates a prompt manager.

        Args:
            hot_reload: If true, reloads the prompt every time it is called.
            src_dir: The directory where the prompts are stored.

        """
        self.hot_reload = hot_reload
        self.src_dir = src_dir

    def bind(self, prompt_id: str) -> Prompt:
        return Prompt(
            file_path=f"{self.src_dir}/{prompt_id}.txt",
            hot_reload=self.hot_reload,
        )
