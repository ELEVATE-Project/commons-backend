"""
Django management command to automatically create PostgreSQL schemas if they don't exist.

Usage:
    python manage.py create_schemas

Environment Variables:
    POSTGRES_SCHEMAS: Comma-separated list of schema names to create (e.g., "schema1,schema2,schema3")
"""

import os
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Creates PostgreSQL schemas if they do not exist'

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
        Main command handler to create schemas
        """
        # Get schemas from command argument or environment variable
        schemas_str = options.get('schemas') or os.getenv('POSTGRES_SCHEMAS', '') or ["shikshalokam"]
        
        if not schemas_str:
            self.stdout.write(
                self.style.WARNING(
                    'No schemas specified. Please set POSTGRES_SCHEMAS environment variable '
                    'or use --schemas argument.'
                )
            )
            return

        # Parse schema names
        schemas = [s.strip() for s in schemas_str.split(',') if s.strip()]
        
        if not schemas:
            self.stdout.write(
                self.style.WARNING('No valid schema names found.')
            )
            return

        self.stdout.write(f'Attempting to create {len(schemas)} schema(s)...\n')

        # Create each schema
        created_count = 0
        skipped_count = 0
        error_count = 0

        with connection.cursor() as cursor:
            for schema_name in schemas:
                try:
                    # Validate schema name (basic SQL injection prevention)
                    if not self._is_valid_schema_name(schema_name):
                        self.stdout.write(
                            self.style.ERROR(
                                f'  ✗ Invalid schema name: {schema_name}'
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
                                f'  ⊙ Schema already exists: {schema_name}'
                            )
                        )
                        skipped_count += 1
                    else:
                        # Create schema
                        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Created schema: {schema_name}'
                            )
                        )
                        created_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ✗ Error creating schema {schema_name}: {str(e)}'
                        )
                    )
                    error_count += 1

        # Summary
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS(f'Created: {created_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped (already exist): {skipped_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        self.stdout.write('=' * 50)

        if error_count > 0:
            raise CommandError(f'Failed to create {error_count} schema(s)')

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
        
        import re
        # Allow alphanumeric, underscores, and hyphens only
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', schema_name))

