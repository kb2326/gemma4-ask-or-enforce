"""Code names mentioned in an issue, used as search keys for the graph-vs-grep probe (gate G3).

Preference order: backticked names, then dotted names (a.b.c), then CamelCase or snake_case words.
Within each group, order of first appearance. Plain English words are never returned.
"""

import re

LEADING_NAME = re.compile(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*')
DOTTED = re.compile(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b')
CAMEL = re.compile(r'\b(?:[A-Z][a-z0-9]+[A-Z]\w*|[A-Z]{2,}[a-z]\w*)\b')
SNAKE = re.compile(r'\b[a-z_][a-z0-9]*_[a-z0-9_]+\b')


def issue_symbols(text, k=5):
    backticked = [m.group() for m in (LEADING_NAME.match(t.strip()) for t in re.findall(r'`([^`\n]+)`', text)) if m]
    found = []
    for name in backticked + DOTTED.findall(text) + CAMEL.findall(text) + SNAKE.findall(text):
        if name not in found:
            found.append(name)
    return found[:k]
