"""Keep OASIS 0.2.5 interviews compatible with the pinned CAMEL runtime."""

from functools import wraps
import inspect


def apply_oasis_camel_compat(agent_type=None):
    """Discard the removed token-count hint only on OASIS's agent class.

    Modern CAMEL calculates model usage itself. OASIS's interview and group
    test methods still pass the old ``num_tokens`` keyword to its inherited
    private method. Ordinary simulation calls keep all their current options.
    """
    if agent_type is None:
        from oasis.social_agent.agent import SocialAgent
        agent_type = SocialAgent

    original = agent_type._aget_model_response
    if getattr(original, '_mirofish_token_compat', False):
        return False
    if 'num_tokens' in inspect.signature(original).parameters:
        return False

    @wraps(original)
    async def compatible(self, *args, num_tokens=None, **kwargs):
        return await original(self, *args, **kwargs)

    compatible._mirofish_token_compat = True
    agent_type._aget_model_response = compatible
    return True
