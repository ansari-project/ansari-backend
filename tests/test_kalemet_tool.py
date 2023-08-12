from ..tools.kalemat import Kalemat
from hermetic.core.environment import Environment
from hermetic.core.prompt_mgr import PromptMgr  


def test_kalemat():
    e = Environment(prompt_mgr=PromptMgr())
    k = Kalemat(e)
    result = k.run_as_string('coral')
    print(result)
    assert('55:22' in result)
    assert('55:58' in result)