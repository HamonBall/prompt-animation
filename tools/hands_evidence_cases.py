"""Complete required evidence matrix, including supplemental curve ranges."""
from elbows_wrists_hands_cases import cases as primary
from hands_trace_range_cases import cases as supplemental

def cases():
    yield from primary()
    yield from supplemental()


def detail_cases():
    return [row for row in cases() if row[0].endswith('.default') or 'palms' in row[0] or
            row[1].startswith('wrist.') and row[0].endswith(('.min','.max','.overhead')) or
            row[0].endswith(('.near-straight','.chest-forward-elbows')) or row[0] in ('hand.trace.arc','hand.trace.circle') or
            row[0].startswith(('hand.trace.arc.','hand.trace.circle.'))]
