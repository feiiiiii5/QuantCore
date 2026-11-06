"""Forward signal adjustment from already identified ex-date events."""

import pandas as pd


def causal_factors(raw: pd.DataFrame, actions: pd.DataFrame) -> pd.Series:
    """Start at one; future cash/split events cannot change an earlier factor."""
    events = {int(event["ex_date"]): event for event in actions.to_dict("records")}
    factor, previous, values = 1.0, None, []
    for row in raw.itertuples(index=False):
        event = events.get(int(row.date))
        if event is not None and previous is not None:
            reference = (previous - float(event["cash_per_share"])) / float(event["split_ratio"])
            if reference <= 0:
                raise ValueError("cash/split event produces a non-positive reference price")
            factor *= previous / reference
        values.append(factor)
        previous = float(row.close)
    return pd.Series(values, index=raw.index, dtype="float64")
