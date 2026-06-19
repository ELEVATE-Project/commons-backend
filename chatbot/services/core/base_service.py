from chatbot.models import CompanyChat, Profile, CompanyBot, ChatSession, BotVernacular
import logging

logger = logging.getLogger('django')


class BaseChatService:
    """Common service for shared database operations and utilities"""

    @staticmethod
    def get_session_data(session_id, profile_id, bot_route):
        """Retrieve common session data"""
        company_chats = CompanyChat.objects.filter(session=session_id).order_by('created_at')
        chat_session = ChatSession.objects.filter(session=session_id).first()
        profile = Profile.objects.filter(id=profile_id).first()

        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route=bot_route)
        else:
            company_bot = CompanyBot.objects.get(route=bot_route)

        return {
            'company_chats': company_chats,
            'chat_session': chat_session,
            'profile': profile,
            'company_bot': company_bot
        }

    @staticmethod
    def get_bot_vernacular_and_intro(company_bot, profile):
        """Handle bot vernacular and intro message logic"""
        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot).first()
        intro_mssg = None

        if bot_vernacular:
            if profile and profile.first_name:
                intro_mssg = bot_vernacular.introductory_message
                # Insert first name into intro message
                first_word = intro_mssg.split(" ")[0]
                remaining_message = " ".join(intro_mssg.split(" ")[1:])
                intro_mssg = f"{first_word} {profile.first_name}, {remaining_message}"
            else:
                intro_mssg = getattr(bot_vernacular, 'alt_introductory_message',
                                     bot_vernacular.introductory_message)

        return bot_vernacular, intro_mssg

    @staticmethod
    def get_user_profile_info(profile):
        """Extract user profile information"""
        if not profile or not profile.first_name:
            return None

        profile_addresses = profile.profile_address.all().first()
        address_components = [
            profile_addresses.district if profile_addresses and profile_addresses.district else "",
            profile_addresses.block if profile_addresses and profile_addresses.block else "",
            profile_addresses.state if profile_addresses and profile_addresses.state else ""
        ]
        address_string = ", ".join(filter(None, address_components))

        return {
            "first_name": profile.first_name,
            "user_location": address_string
        }
