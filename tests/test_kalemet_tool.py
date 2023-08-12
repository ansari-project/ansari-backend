from ..tools.kalemat import Kalemat


def test_kalemat():
    k = Kalemat()
    result = k.run_as_string('coral')
    print(result)
    assert('55:22' in result)
    assert('55:58' in result)