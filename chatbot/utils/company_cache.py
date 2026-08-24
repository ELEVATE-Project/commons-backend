from django.conf import settings
from django.core.cache import cache

from chatbot.models import Company

CACHE_TIMEOUT = settings.COMPANY_CACHE_TTL
CACHE_ENABLED = settings.REDIS_CACHE_ENABLED
ORG_KEY_PREFIX = "ORG_"
ORG_KEY_PATTERN = f"{ORG_KEY_PREFIX}*"


def _org_key(slug):
    return f"{ORG_KEY_PREFIX}{slug}"


def get_all_companies():
    if not CACHE_ENABLED:
        return list(Company.objects.order_by("name"))

    keys = cache.keys(ORG_KEY_PATTERN) or []
    companies = list(cache.get_many(keys).values()) if keys else []
    if not keys or len(companies) != len(keys):
        companies = list(Company.objects.order_by("name"))
        for company in companies:
            cache.set(_org_key(company.slug), company, CACHE_TIMEOUT)
        return companies

    return sorted(companies, key=lambda company: company.name)


def get_company_by_slug(slug):
    if not CACHE_ENABLED:
        return Company.objects.filter(slug=slug).first()

    company = cache.get(_org_key(slug))
    if company is None:
        company = Company.objects.filter(slug=slug).first()
        if company is not None:
            cache.set(_org_key(slug), company, CACHE_TIMEOUT)
    return company


def sync_company_cache(company):
    if not CACHE_ENABLED:
        return
    cache.set(_org_key(company.slug), company, CACHE_TIMEOUT)


def evict_company_cache(slug):
    if not CACHE_ENABLED:
        return
    cache.delete(_org_key(slug))
