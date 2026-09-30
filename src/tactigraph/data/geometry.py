"""Keep raw coordinates intact; spatial eligibility is a separate decision."""


def in_pitch(x, y):
    return x is not None and y is not None and 0 <= x <= 120 and 0 <= y <= 80


def location_status(x, y):
    if x is None or y is None:
        return "missing"
    return "valid" if in_pitch(x, y) else "outside_pitch"
