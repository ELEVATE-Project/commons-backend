"""
Custom Import/Export Views for CompanyBot with inline models
Add this to your views.py
"""
import json
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.forms import model_to_dict
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.db import transaction
from chatbot.models import CompanyBot, Voice, CompanyStateMachine, Company, Profile, ProfileType, BotVernacular
import logging

logger = logging.getLogger('django')

def generate_template(format_type):
    """Generate empty template files for import"""
    if format_type == 'json':
        template_data = [{
            "name": "Example Bot",
            "company_slug": "company-slug",
            "context": "Bot context here",
            "max_token": 1000,
            "provider": "openai",
            "bot_type": "qa",
            "voices": [
                {
                    "type": "greeting",
                    "provider": "elevenlabs",
                    "name": "Voice Name",
                    "language": "en"
                }
            ],
            "state_machines": [
                {
                    "name": "Step 1",
                    "step": 1,
                    "bot_question": "What is your name?",
                    "completion_criteria": "User provides name"
                }
            ]
        }]

        response = HttpResponse(
            json.dumps(template_data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="companybot_template.json"'
        return response


@staff_member_required
def export_bots(request):
    """Export CompanyBots with their inline models"""
    user_email = request.user.email
    profile = Profile.objects.filter(email=user_email).first()

    # Check if this is a template request
    is_template = request.GET.get('template', 'false').lower() == 'true'

    # Filter bots based on user permissions
    if request.user.is_superuser:
        bots = CompanyBot.objects.all()
    elif profile and profile.profile_type == ProfileType.MODERATOR:
        bots = CompanyBot.objects.filter(company=profile.company)
    else:
        messages.error(request, "You don't have permission to export bots.")
        return redirect('admin:chatbot_companybot_changelist')

    # Get selected bot IDs if any
    bot_ids = request.GET.get('ids', '').split(',')
    bot_ids = [id for id in bot_ids if id]  # Filter empty strings
    if bot_ids:
        bots = bots.filter(id__in=bot_ids)

    # If no format specified, show format selection page
    export_format = request.GET.get('format')
    if not export_format:
        return render(request, 'admin/export_format.html', {
            'bot_count': bots.count(),
            'selected_ids': ','.join(bot_ids),
        })

    # Generate templates if requested
    if is_template:
        return generate_template(export_format)

    # Export based on format
    if export_format == 'json':
        bots = bots.select_related('company').prefetch_related(
            'voice_set',
            'companystatemachine_set',
            'bot_vernacular'
        )
        return export_bots_json(bots)
    else:
        messages.error(request, "Invalid export format.")
        return redirect('admin:chatbot_companybot_changelist')


def export_bots_json(bots):
    """Export bots as JSON"""
    data = []
    for bot in bots.select_related('company'):

        bot_data = model_to_dict(bot, exclude=['id', 'company', 'created_at', 'updated_at'])
        bot_data['company_slug'] = bot.company.slug
        # Add voices
        voice_data=[]
        voices = bot.voice_set.all()
        for v in voices:
            voice_data.append(model_to_dict(v, exclude=['id', 'company_bot', 'created_at', 'updated_at']))
        bot_data['voices'] = voice_data

        # Add state machines
        state_machine_data=[]
        state_machines = bot.companystatemachine_set.all().order_by('step')
        for sm in state_machines:
            sm_dict = model_to_dict(
                sm, exclude=[
                    'id', 'company_bot', 'preprocess_bot', 'postprocess_bot', 'created_at',
                    'updated_at', 'history'
                ]
            )
            sm_dict['preprocess_bot_route'] = (
                sm.preprocess_bot.route if sm.preprocess_bot else None
            )
            sm_dict['postprocess_bot_route'] = (
                sm.postprocess_bot.route if sm.postprocess_bot else None
            )

            state_machine_data.append(sm_dict)

        bot_data['state_machines'] = state_machine_data

        bot_vernacular_data=[]
        bot_vernaculars = bot.bot_vernacular.all().order_by('language')
        for bv in bot_vernaculars:
            bot_vernacular_data.append(model_to_dict(bv, exclude=[
                'id', 'company_bot', 'created_at', 'updated_at', 'history'
            ]))

        bot_data['bot_vernaculars'] = bot_vernacular_data

        data.append(bot_data)

    response = HttpResponse(
        json.dumps(data, indent=2, default=str),
        content_type='application/json'
    )
    response['Content-Disposition'] = 'attachment; filename="company_bots.json"'
    return response


@staff_member_required
def import_bots(request):
    """Import CompanyBots with their inline models"""
    if request.method == 'POST':
        uploaded_file = request.FILES.get('import_file')
        if not uploaded_file:
            messages.error(request, "Please upload a file.")
            return redirect('admin:chatbot_companybot_changelist')

        file_extension = uploaded_file.name.split('.')[-1].lower()

        try:
            if file_extension == 'json':
                result = import_bots_json(request, uploaded_file)
            else:
                messages.error(request, "Unsupported file format. Use JSON Only.")
                return redirect('admin:chatbot_companybot_changelist')

            messages.success(
                request,
                f"Successfully imported {result['created']} bots and updated {result['updated']} bots."
            )
        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")

        return redirect('admin:chatbot_companybot_changelist')

    # GET request - show import form
    return render(request, "admin/import_form.html")


def import_bots_json(request, uploaded_file):
    """Import from JSON file"""
    try:
        data = json.load(uploaded_file)
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email).first()

        created_count = 0
        updated_count = 0
        bot_import_payloads = []

        with transaction.atomic():
            # Pass 1: Create/update all bots and clear inline records.
            for bot_data in data:
                company_slug = bot_data.pop('company_slug')
                try:
                    company = Company.objects.get(slug=company_slug)
                except Company.DoesNotExist:
                    raise ValueError(f"Company with slug '{company_slug}' not found")

                # Check permissions
                if not request.user.is_superuser:
                    if not profile or profile.profile_type != ProfileType.MODERATOR or profile.company != company:
                        raise PermissionError(f"You don't have permission to import bots for company {company_slug}")

                # Extract inline data
                voices_data = bot_data.pop('voices', [])
                state_machines_data = bot_data.pop('state_machines', [])
                bot_vernacular_data = bot_data.pop('bot_vernaculars', [])

                # Create or update bot
                bots = CompanyBot.objects.filter(
                    route=bot_data['route'],
                    company=company
                )

                if bots.exists():
                    bot = bots.first()
                    for key, value in bot_data.items():
                        setattr(bot, key, value)
                    bot.save()
                    updated_count += 1
                else:
                    bot = CompanyBot.objects.create(
                        company=company,
                        **bot_data
                    )
                    created_count += 1

                # Delete existing inline records
                Voice.objects.filter(company_bot=bot).delete()
                CompanyStateMachine.objects.filter(company_bot=bot).delete()
                BotVernacular.objects.filter(company_bot=bot).delete()

                bot_import_payloads.append(
                    {
                        'bot': bot,
                        'company': company,
                        'voices_data': voices_data,
                        'state_machines_data': state_machines_data,
                        'bot_vernacular_data': bot_vernacular_data,
                    }
                )

            # Pass 2: Create inline records once all bots are available.
            for payload in bot_import_payloads:
                bot = payload['bot']
                company = payload['company']
                voices_data = payload['voices_data']
                state_machines_data = payload['state_machines_data']
                bot_vernacular_data = payload['bot_vernacular_data']

                # Create voices
                for voice_data in voices_data:
                    Voice.objects.create(company_bot=bot, **voice_data)

                # Create state machines
                for sm_data in state_machines_data:
                    sm_payload = sm_data.copy()

                    # Handle bot references
                    preprocess_bot_route = sm_payload.pop('preprocess_bot_route', None)
                    postprocess_bot_route = sm_payload.pop('postprocess_bot_route', None)

                    preprocess_bot = None
                    if preprocess_bot_route:
                        preprocess_bot = CompanyBot.objects.filter(
                            route=preprocess_bot_route, company=company
                        ).first()
                        if not preprocess_bot:
                            raise ValueError(
                                f"Preprocess bot route '{preprocess_bot_route}' not found for "
                                f"company '{company.slug}' while importing bot '{bot.route}'."
                            )

                    postprocess_bot = None
                    if postprocess_bot_route:
                        postprocess_bot = CompanyBot.objects.filter(
                            route=postprocess_bot_route, company=company
                        ).first()
                        if not postprocess_bot:
                            raise ValueError(
                                f"Postprocess bot route '{postprocess_bot_route}' not found for "
                                f"company '{company.slug}' while importing bot '{bot.route}'."
                            )

                    CompanyStateMachine.objects.create(
                        company_bot=bot,
                        preprocess_bot=preprocess_bot,
                        postprocess_bot=postprocess_bot,
                        **sm_payload
                    )
                # Create bot_vernacular
                for bv_data in bot_vernacular_data:
                    BotVernacular.objects.create(company_bot=bot, **bv_data)

        return {'created': created_count, 'updated': updated_count}

    except Exception as e:
        logger.error(f"Error importing bots: {e}", exc_info=True)
        return {'created': 0, 'updated': 0}
