
from pydantic import BaseModel
from typing import Union


class Prompt(BaseModel):
    file_path: str
    cached: Union[str, None] = None
    hot_reload: bool = True

    def render(self, **kwargs) -> str:
        if (self.cached is None) or (self.hot_reload):
            # utf-8 is used to properly display arabic words in the terminal (main_stdio.py)
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.cached = f.read()
        return self.cached.format(**kwargs)
    


class PromptMgr():
    def __init__(self, hot_reload: bool = True, src_dir: str = 'resources/prompts'):
        """ Creates a prompt manager. 

        Args:
            hot_reload: If true, reloads the prompt every time it is called.
            src_dir: The directory where the prompts are stored.

        """
        self.hot_reload = hot_reload
        self.src_dir = src_dir

    def bind(self, prompt_id: str) -> Prompt:
        return Prompt(file_path = f'{self.src_dir}/{prompt_id}.txt', 
                    hot_reload=self.hot_reload)

