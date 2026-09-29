def percent_change(previous, current):
    if previous is None or current is None or previous == 0:
        return None
    return ((current - previous) / previous) * 100.0

def classify_position(previous_shares, current_shares):
    if previous_shares in (None, 0) and current_shares not in (None, 0):
        return "new"
    if current_shares in (None, 0) and previous_shares not in (None, 0):
        return "exited"
    if previous_shares is None or current_shares is None:
        return "unknown"
    if current_shares > previous_shares:
        return "increased"
    if current_shares < previous_shares:
        return "reduced"
    return "unchanged"
