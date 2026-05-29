"""Risk engine: gates that can deny strategy signals before they become
orders. Each gate is independently testable and has a stable reason tag
so analytics / alerts can attribute denials.
"""
