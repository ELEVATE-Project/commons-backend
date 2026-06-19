import logging
from chatbot.models import CompanyBot

logger = logging.getLogger('django')


def get_company_bot(route: str, profile=None) -> CompanyBot | None:
    try:
        if profile:
            return CompanyBot.objects.filter(company=profile.company, route=route).first()
        return CompanyBot.objects.filter(route=route).first()
    except Exception as e:
        logger.error("Error during company bot retrieval: %s", e, exc_info=True)
        return None
    