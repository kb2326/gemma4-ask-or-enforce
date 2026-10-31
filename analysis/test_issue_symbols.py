"""Checks for analysis/issue_symbols.py. Run: python analysis/test_issue_symbols.py"""

from issue_symbols import issue_symbols


def test_backticked_first():
    text = 'Calling Console.print fails. The `render_lines` helper drops `Segment` objects.'
    assert issue_symbols(text)[:2] == ['render_lines', 'Segment']


def test_dotted_and_snake_kept_english_dropped():
    text = 'When I use rich.progress.track with a long_description the bar is wrong. Please fix this bug.'
    syms = issue_symbols(text)
    assert 'rich.progress.track' in syms and 'long_description' in syms
    assert not {'When', 'Please', 'bug', 'the'} & set(syms)


def test_camel_case_kept():
    assert 'APIRouter' in issue_symbols('Adding an APIRouter with a prefix breaks OpenAPI.')


def test_dedup_and_limit():
    text = '`a_b` `a_b` `c_d` `e_f` `g_h` `i_j` `k_l`'
    assert issue_symbols(text) == ['a_b', 'c_d', 'e_f', 'g_h', 'i_j']
    assert issue_symbols(text, k=2) == ['a_b', 'c_d']


def test_backtick_code_is_reduced_to_names():
    assert issue_symbols('Run `app.include_router(router)` and see.')[0] == 'app.include_router'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('all issue_symbols tests passed')
