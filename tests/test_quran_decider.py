from ..agents.quran_decider import QuranDecider
from hermetic.core.environment import Environment
from hermetic.core.prompt_mgr import PromptMgr


def test_quran_decider():
    e = Environment(prompt_mgr=PromptMgr())
    qd = QuranDecider(e)
    result = qd.process_input('Does the Quran talk about rubies?')
    print(result)
    assert('Yes' in result)
    # Restart the servce
    qd = QuranDecider(e)
    result = qd.process_input('What do modern scholars think about music?')
    print(result)
    assert('No' in result)