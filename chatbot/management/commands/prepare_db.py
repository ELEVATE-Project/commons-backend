"""
Django management command to prepare the database:
- Create PostgreSQL schemas if they don't exist
- Create/update Company record with id=1
- Create/update Profile record with id=1

Usage:
    python manage.py prepare_db

Environment Variables:
    POSTGRES_SCHEMAS: Comma-separated list of schema names to create (e.g., "schema1,schema2,schema3")
    COMPANY_NAME: Company name (default: "Shikshalokam")
    COMPANY_SLUG: Company slug (default: "shikshalokam")
    ADMIN_EMAIL: Admin email (default: "accounts@gritworks.ai")
"""

import os
import re
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection
from chatbot.models.company_models import Company
from chatbot.models.profile_models import Profile
from chatbot.models.enums import EntityStatus, ProfileType


class Command(BaseCommand):
    help = 'Prepares database by creating schemas, company, and admin profile'

    def add_arguments(self, parser):
        """
        Add custom command arguments
        """
        parser.add_argument(
            '--schemas',
            type=str,
            help='Comma-separated list of schema names to create (overrides POSTGRES_SCHEMAS env variable)',
        )

    def handle(self, *args, **options):
        """
        Main command handler to prepare database
        """
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('Starting Database Preparation'))
        self.stdout.write(self.style.SUCCESS('=' * 60 + '\n'))

        # Track overall status
        total_errors = 0

        # Step 1: Create schemas
        schema_errors = self._create_schemas(options)
        total_errors += schema_errors

        migration_errors = self._migrate_database()
        total_errors += migration_errors


        # Step 2: Create/update Company
        company_errors = self._setup_company()
        total_errors += company_errors

        # Step 3: Create/update Profile
        profile_errors = self._setup_profile()
        total_errors += profile_errors

        self._setup_profile_null_user()

        # Final summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('Database Preparation Complete'))
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f'Total Errors: {total_errors}'))
        else:
            self.stdout.write(self.style.SUCCESS('All operations completed successfully!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        if total_errors > 0:
            raise CommandError(f'Database preparation completed with {total_errors} error(s)')

    def _create_schemas(self, options):
        """
        Create PostgreSQL schemas if they don't exist
        
        Returns:
            int: Number of errors encountered
        """
        self.stdout.write(self.style.HTTP_INFO('\n[1/4] Creating PostgreSQL Schemas'))
        self.stdout.write('-' * 60)

        # Get schemas from command argument or environment variable
        schemas_str = options.get('schemas') or os.environ.get('POSTGRES_SCHEMAS', '') or ['shikshalokam']
        
        if not schemas_str:
            self.stdout.write(
                self.style.WARNING(
                    '  ⊙ No schemas specified (POSTGRES_SCHEMAS not set). Skipping...'
                )
            )
            return 0

        # Parse schema names
        schemas = [s.strip() for s in schemas_str.split(',') if s.strip()]
        
        if not schemas:
            self.stdout.write(
                self.style.WARNING('  ⊙ No valid schema names found. Skipping...')
            )
            return 0

        self.stdout.write(f'  Attempting to create {len(schemas)} schema(s)...\n')

        # Create each schema
        created_count = 0
        skipped_count = 0
        error_count = 0

        with connection.cursor() as cursor:
            for schema_name in schemas:
                try:
                    # Validate schema name
                    if not self._is_valid_schema_name(schema_name):
                        self.stdout.write(
                            self.style.ERROR(
                                f'    ✗ Invalid schema name: {schema_name}'
                            )
                        )
                        error_count += 1
                        continue

                    # Check if schema exists
                    cursor.execute(
                        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
                        [schema_name]
                    )
                    exists = cursor.fetchone()

                    if exists:
                        self.stdout.write(
                            self.style.WARNING(
                                f'    ⊙ Schema already exists: {schema_name}'
                            )
                        )
                        skipped_count += 1
                    else:
                        # Create schema
                        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'    ✓ Created schema: {schema_name}'
                            )
                        )
                        created_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'    ✗ Error creating schema {schema_name}: {str(e)}'
                        )
                    )
                    error_count += 1

        # Schema summary
        self.stdout.write(f'\n  Summary: Created: {created_count}, Skipped: {skipped_count}, Errors: {error_count}')
        return error_count

    def _migrate_database(self):
        """
        Migrate the database by running Django's migrate command programmatically.

        Returns:
            int: Number of errors encountered (0 or 1)
        """
        self.stdout.write(self.style.HTTP_INFO('\n[2/4] Migrating the database'))
        self.stdout.write('-' * 60)

        try:
            self.stdout.write('  Running migrations...\n')

            call_command('migrate', interactive=False, verbosity=1)

            self.stdout.write(
                self.style.SUCCESS(
                    '  ✓ Database migrations applied successfully'
                )
            )
            return 0

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  ✗ Error migrating database: {str(e)}'
                )
            )
            return 1

    def _setup_company(self):
        """
        Create or update Company record with id=1
        
        Returns:
            int: Number of errors encountered (0 or 1)
        """
        self.stdout.write(self.style.HTTP_INFO('\n[3/4] Setting up Company Record'))
        self.stdout.write('-' * 60)

        try:
            # Get environment variables
            company_name = os.environ.get('COMPANY_NAME', 'Shikshalokam')
            company_slug = os.environ.get('COMPANY_SLUG', 'shikshalokam')

            self.stdout.write(f'  Company Name: {company_name}')
            self.stdout.write(f'  Company Slug: {company_slug}\n')

            # Check if Company with id=1 exists
            try:
                company = Company.objects.get(id=1)
                # Update existing company
                company.name = company_name
                company.slug = company_slug
                company.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Updated Company (id=1): {company_name}'
                    )
                )
            except Company.DoesNotExist:
                # Create new company with id=1
                company = Company.objects.create(
                    id=1,
                    name=company_name,
                    slug=company_slug,
                    status=EntityStatus.ACTIVE,
                    logo=None,
                    url=None
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Created Company (id=1): {company_name}'
                    )
                )

            return 0

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  ✗ Error setting up Company: {str(e)}'
                )
            )
            return 1

    def _setup_profile(self):
        """
        Create or update Profile record with id=1
        
        Returns:
            int: Number of errors encountered (0 or 1)
        """
        self.stdout.write(self.style.HTTP_INFO('\n[4/4] Setting up Admin Profile'))
        self.stdout.write('-' * 60)

        try:
            # Get environment variable
            admin_email = os.environ.get('ADMIN_EMAIL', 'admin@shikshalokam.org')
            admin_first_name = 'AI'

            self.stdout.write(f'  Admin Email: {admin_email}')
            self.stdout.write(f'  Admin First Name: {admin_first_name}\n')

            # Ensure Company with id=1 exists
            try:
                company = Company.objects.get(id=1)
            except Company.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        '  ✗ Company with id=1 does not exist. Cannot create Profile.'
                    )
                )
                return 1

            # Check if Profile with id=1 exists
            try:
                profile = Profile.objects.get(id=1)
                # Update existing profile
                profile.first_name = admin_first_name
                profile.email = admin_email
                profile.company = company
                profile.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Updated Profile (id=1): {admin_email}'
                    )
                )
            except Profile.DoesNotExist:
                # Create new profile with id=1
                profile = Profile.objects.create(
                    id=1,
                    first_name=admin_first_name,
                    email=admin_email,
                    company=company,
                    status=EntityStatus.ACTIVE,
                    profile_type=ProfileType.USER,
                    last_name=None,
                    phone=None,
                    alternate_phone=None,
                    country=None,
                    password=None,
                    profile_code=None,
                    location=None,
                    caste=None,
                    gender=None,
                    designation='',
                    org_associated=None,
                    product_interested=None,
                    company_spoc=None,
                    other_params=None,
                    source=None,
                    preferred_route=None,
                    userid=None,
                    latest_flow_used=None
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Created Profile (id=1): {admin_email}'
                    )
                )

            return 0

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  ✗ Error setting up Profile: {str(e)}'
                )
            )
            return 1

    def _setup_profile_null_user(self):
        """
        Create or update Profile record with id=1
        
        Returns:
            int: Number of errors encountered (0 or 1)
        """
        self.stdout.write(self.style.HTTP_INFO('\n[4/4] Setting up Null User Profile'))
        self.stdout.write('-' * 60)

        try:
            # Get environment variable
            null_user_email = "null@shikshalokam.org"
            null_user_first_name = 'Null User'
            company_name = os.environ.get('COMPANY_SLUG', 'shikshalokamstaging')

            self.stdout.write(f'  Null User Email: {null_user_email}')
            self.stdout.write(f'  Null User First Name: {null_user_first_name}\n')

            # Ensure Company with id=1 exists
            try:
                company = Company.objects.get(slug=company_name)
            except Company.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        '  ✗ Company with id=1 does not exist. Cannot create Profile.'
                    )
                )
                return 1

            # Check if Profile with id=1 exists
            try:
                profile = Profile.objects.get(email=null_user_email)
                # Update existing profile
                profile.first_name = null_user_first_name
                profile.email = null_user_email
                profile.company = company
                profile.password = "grit@123"
                profile.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Updated Profile ({null_user_email}): {null_user_email}'
                    )
                )
            except Profile.DoesNotExist:
                profile = Profile.objects.create(
                    first_name=null_user_first_name,
                    email=null_user_email,
                    company=company,
                    status=EntityStatus.ACTIVE,
                    profile_type=ProfileType.USER,
                    last_name=None,
                    phone=None,
                    alternate_phone=None,
                    country=None,
                    password="grit@123",
                    profile_code=None,
                    location=None,
                    caste=None,
                    gender=None,
                    designation='',
                    org_associated=None,
                    product_interested=None,
                    company_spoc=None,
                    other_params=None,
                    source=None,
                    preferred_route=None,
                    userid=None,
                    latest_flow_used=None
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Created Profile : {null_user_email}'
                    )
                )

            return 0

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  ✗ Error setting up Profile: {str(e)}'
                )
            )
            return 1


    def _is_valid_schema_name(self, schema_name):
        """
        Validate schema name to prevent SQL injection
        
        Args:
            schema_name (str): Schema name to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Schema names should only contain alphanumeric characters, underscores, and hyphens
        # and should not be empty or exceed reasonable length
        if not schema_name or len(schema_name) > 63:  # PostgreSQL identifier length limit
            return False
        
        # Allow alphanumeric, underscores, and hyphens only
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', schema_name))

