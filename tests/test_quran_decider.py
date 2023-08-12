from ..agents.quran_decider import QuranDecider


def test_quran_decider():
    qd = QuranDecider()
    result = qd.process_input('Does the Quran talk about rubies?')
    print(result)
    assert('Yes' in result)
    # Restart the servce
    qd = QuranDecider()
    result = qd.process_input('What do modern scholars think about music?')
    print(result)
    assert('No' in result)