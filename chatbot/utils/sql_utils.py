import re
from django.db import connection
import json_repair
from chatbot.models import CompanyBotDynamicContextType
from datetime import datetime, date, timedelta
import logging


logger = logging.getLogger('django')


def run_sql_from_string(string):
    matches = re.findall(r'\{\{\s*(.*?)\s*\}\}', string)

    if not matches:
        return string

    replacements = []

    for sql in matches:
        with connection.cursor() as cursor:
            cursor.execute(sql)

            fetched_results = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            result_str = str([dict(zip(columns, row)) for row in fetched_results])

            replacements.append(result_str)

    for i, sql in enumerate(matches):
        string = string.replace(f"{{{{ {sql} }}}}", replacements[i])

    logger.info(f"Resultant string: %s", string)
    return string


def get_todays_date(company_bot):
    today_date = ""
    try:
        if company_bot and company_bot.dynamic_context_type == CompanyBotDynamicContextType.SQL_QUERY:
            dynamic_context = company_bot.dynamic_context
            if isinstance(dynamic_context, str):
                dynamic_context = json_repair.repair_json(dynamic_context, return_objects=True)
            sql_result = run_sql_from_string(dynamic_context.get('date'))
            logger.info(f"Resultant string: %s", sql_result)

            parsed_date = None
            if isinstance(sql_result, str):
                match = re.search(r"datetime\.date\((\d+), (\d+), (\d+)\)", sql_result)
                if match:
                    year, month, day = map(int, match.groups())
                    parsed_date = date(year, month, day)

            elif isinstance(sql_result, list) and len(sql_result) > 0:
                val = sql_result[0].get('current_date')
                if isinstance(val, date):
                    parsed_date = val
                elif isinstance(val, str):
                    parsed_date = datetime.strptime(val, "%d %B %Y").date()
            logger.info(f"parsed_date: %s", parsed_date)
            if parsed_date:
                today_weekday = parsed_date.strftime('%A')

                today_date = f"{parsed_date.strftime('%d %B %Y')} ({today_weekday}), "
                logger.info(f"parsed today_date: %s", today_date)

    except Exception as e:
        logger.error("Error while parsing today's date: %s", e, exc_info=True)
    logger.info(f"DATE: %s", today_date)
    return today_date
