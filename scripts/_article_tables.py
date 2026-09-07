"""Tables emitted by the article pipeline (plain cells, no embedded pipes)."""

import re


def read_table(lines, start):
    if start + 1 >= len(lines) or not lines[start].strip().startswith('|'):
        return None
    def cells(line):
        value = line.strip()
        if value.startswith('|'):
            value = value[1:]
        if value.endswith('|'):
            value = value[:-1]
        return [cell.strip() for cell in value.split('|')]
    header = cells(lines[start])
    separator = cells(lines[start + 1])
    if len(header) != len(separator) or not all(re.fullmatch(r':?-{3,}:?', v) for v in separator):
        return None
    rows = [header]
    index = start + 2
    while index < len(lines) and lines[index].strip().startswith('|'):
        row = cells(lines[index])
        if len(row) != len(header):
            raise ValueError('Article table has inconsistent column counts')
        rows.append(row)
        index += 1
    return rows, index
