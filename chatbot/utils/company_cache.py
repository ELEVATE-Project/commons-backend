from django.conf import settings
from django.core.cache import cache

from chatbot.models import Company

CACHE_TIMEOUT = settings.COMPANY_CACHE_TTL
CACHE_ENABLED = settings.REDIS_CACHE_ENABLED
ALL_COMPANIES_KEY = "company:all"
COMPANY_BY_ID_KEY = "company:id:{}"
COMPANY_BY_SLUG_KEY = "company:slug:{}"


def get_all_companies():
    if not CACHE_ENABLED:
        return list(Company.objects.order_by("name"))

    companies = cache.get(ALL_COMPANIES_KEY)
    if companies is None:
        companies = list(Company.objects.order_by("name"))
        cache.set(ALL_COMPANIES_KEY, companies, CACHE_TIMEOUT)
    return companies


def get_company_by_id(company_id):
    if not CACHE_ENABLED:
        return Company.objects.filter(pk=company_id).first()

    key = COMPANY_BY_ID_KEY.format(company_id)
    company = cache.get(key)
    if company is None:
        company = Company.objects.filter(pk=company_id).first()
        if company is not None:
            cache.set(key, company, CACHE_TIMEOUT)
    return company


def get_company_by_slug(slug):
    if not CACHE_ENABLED:
        return Company.objects.filter(slug=slug).first()

    key = COMPANY_BY_SLUG_KEY.format(slug)
    company = cache.get(key)
    if company is None:
        company = Company.objects.filter(slug=slug).first()
        if company is not None:
            cache.set(key, company, CACHE_TIMEOUT)
    return company


def sync_company_cache(company):
    if not CACHE_ENABLED:
        return
    cache.set(COMPANY_BY_ID_KEY.format(company.pk), company, CACHE_TIMEOUT)
    cache.set(COMPANY_BY_SLUG_KEY.format(company.slug), company, CACHE_TIMEOUT)
    cache.delete(ALL_COMPANIES_KEY)


def evict_company_cache(company):
    if not CACHE_ENABLED:
        return
    cache.delete(COMPANY_BY_ID_KEY.format(company.pk))
    cache.delete(COMPANY_BY_SLUG_KEY.format(company.slug))
    cache.delete(ALL_COMPANIES_KEY)


def evict_company_slug(slug):
    if not CACHE_ENABLED:
        return
    cache.delete(COMPANY_BY_SLUG_KEY.format(slug))
