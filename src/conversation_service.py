"""
Public compatibility entry point for the modular conversation package.

Recommended placement:
    src/conversation_service.py

Existing UI code can continue using:
    from conversation_service import handle_followup_message
"""

from conversation.service import handle_followup_message

__all__ = ["handle_followup_message"]
