class RedirectException(Exception):
    def __init__(self, canonical_id=None):
        super().__init__("Redirecting to Canonical id")
        self.canonical_id = canonical_id
