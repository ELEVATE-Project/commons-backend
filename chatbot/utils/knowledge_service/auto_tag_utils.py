import json
import os
from chatbot.celery_tasks.knowledge_service.tag_tasks import get_auto_extracted_data
from chatbot.models import Tag, TagChoices, TagSourceChoices

S3_BASE_URL = os.getenv('S3_MEDIA_URL')
BOT_PROFILE_ID = 1


def save_auto_tags(media):
    """
    Generate and save auto tags for the given media.
    """
    auto_tag_names = get_auto_extracted_data(media)  # currently returns []
    tag_objs = []
    company = getattr(media.company_bot, 'company', None)

    for name in auto_tag_names:
        tag_obj, created = Tag.objects.get_or_create(
            name=name,
            company=company,
            defaults = {
                'created_by_id': 1,
                'status': TagChoices.APPROVED
            }
        )
        if not created and not tag_obj.status:
            tag_obj.status = TagChoices.APPROVED
            tag_obj.save()

        tag_objs.append(tag_obj)

    if tag_objs:
        # Add auto tags to the media, keeping existing tags
        media.tags.add(*tag_objs)
        print(f"Saved auto tags for media {media.id}: {[t.name for t in tag_objs]}")
    else:
        print(f"No auto tags generated for media {media.id}")


class TagProcessor:

    @staticmethod
    def get_master_tags(company=None, other_params=None, include_description=False):
        try:
            if other_params:
                try:
                    if isinstance(other_params, str):
                        params = json.loads(other_params)
                    else:
                        params = other_params

                    include_description = params.get('include_description', include_description)
                except (json.JSONDecodeError, TypeError):
                    pass

            query = Tag.objects.filter(
                source_type__in=[TagSourceChoices.MANUAL, TagSourceChoices.AI_EXTRACTED],
                status=TagChoices.APPROVED
            )

            # if company:
            #     query = query.filter(company=company)

            if include_description:
                return [
                    {
                        'name': tag['name'],
                        'description': tag['description'] or ''
                    }
                    for tag in query.values('name', 'description').distinct()
                ]
            else:
                return list(query.values_list('name', flat=True).distinct())

        except Exception as e:
            print(f"Error getting master tags: {e}")
            return []

    @staticmethod
    def process_tags_for_media(tag_names, tag_source, user_profile, company, is_manual=True):
        """Process tags and create/update tag objects"""
        tags = []

        for tag_name in tag_names:
            if isinstance(tag_name, dict):
                tag_text = tag_name.get('text', '')
                source = tag_name.get('source', tag_source)
                description = tag_name.get('description', '')
            else:
                tag_text = tag_name
                source = tag_source
                description = ''

            # Clean tag name
            if tag_text.startswith('auto-'):
                clean_tag_name = tag_text.replace('auto-', '')
            else:
                clean_tag_name = tag_text

            if is_manual:
                tag, created = Tag.objects.get_or_create(
                    name=clean_tag_name,
                    defaults={
                        'created_by': user_profile,
                        'company': company,
                        'status': TagChoices.APPROVED,
                        'source_type': TagSourceChoices.MANUAL,
                        'description': ''
                    }
                )
                if not created and tag.source_type == TagSourceChoices.MANUAL:
                    tag.status = TagChoices.APPROVED
                    tag.save()
            else:
                # Auto tags
                if source == 'extracted':
                    source_type = TagSourceChoices.AI_EXTRACTED
                    status = TagChoices.APPROVED
                    desc_to_save = ''
                else:
                    source_type = TagSourceChoices.AI_GENERATED
                    status = TagChoices.PENDING
                    desc_to_save = description

                tag, created = Tag.objects.get_or_create(
                    name=clean_tag_name,
                    defaults={
                        'created_by_id': BOT_PROFILE_ID,
                        'company': company,
                        'status': status,
                        'source_type': source_type,
                        'description': desc_to_save
                    }
                )

            tags.append(tag)

        return tags

    @staticmethod
    def extract_tag_texts(tags_data):
        """Extract just the text from tags for subdocuments"""
        texts = []
        for tag in tags_data:
            if isinstance(tag, dict) and 'text' in tag:
                texts.append(tag['text'])
            elif isinstance(tag, str):
                texts.append(tag)
        return texts

    @staticmethod
    def process_tags(tags_data):
        """Process tags into consistent format"""
        processed_tags = []
        for tag in tags_data:
            if isinstance(tag, dict):
                processed_tags.append(tag)
            else:
                processed_tags.append({'text': tag, 'source': 'extracted'})
        return processed_tags

