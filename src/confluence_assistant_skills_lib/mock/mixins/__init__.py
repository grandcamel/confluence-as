"""Mock client mixins for Confluence API areas."""

from .content import ContentMixin
from .page import PageMixin
from .space import SpaceMixin

__all__ = [
    "PageMixin",
    "SpaceMixin",
    "ContentMixin",
]
