def inr(value):
    """120000 -> '1,20,000' (Indian digit grouping)."""
    if value is None or value == "":
        return ""
    number = int(value)
    digits = str(abs(number))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts + [tail])
    return ("-" if number < 0 else "") + digits