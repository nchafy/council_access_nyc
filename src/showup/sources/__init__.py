"""Source adapters: one module per upstream shape.

Each adapter takes bytes or text that somebody else produced and returns our own
model objects, with all text already passed through `text.strip_tags` and all URLs
through `urls.safe_url`. Nothing downstream of here should ever see upstream
markup.
"""
