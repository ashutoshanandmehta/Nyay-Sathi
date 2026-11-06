"""Review decisions are independent of provider and graph implementation."""

import re


class ReviewPolicy:
    @staticmethod
    def simple_intake(message, context):
        return not context.get("relevant_evidence") and bool(
            re.fullmatch(
                r"\s*(?:hi|hello|hey|namaste|my refund has not arrived|yes[, ]+that['’]s right[.!]?|explain in hindi[.!]?|make it shorter[.!]?)\s*",
                message,
                re.I,
            )
        )

    @staticmethod
    def may_revise(calls, limit, attempts):
        # Reserve the independent re-review before starting a revision.
        return attempts < 1 and calls + 2 <= limit
