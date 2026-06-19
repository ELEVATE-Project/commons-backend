# Chatbot Management Commands

## Overview

The chatbot management commands serve two primary purposes to facilitate setup and administration:

### 1. Schema Creation (`create_schemas.py`)

- This command creates PostgreSQL database schemas automatically based on environment variables.
- It avoids manual database login and setup by reading a comma-separated list of schemas from the `POSTGRES_SCHEMAS` env var or command arguments.
- Intended to be run once before initial migrations.
- Validates schema names to prevent SQL injection.

### 2. Initial Database Preparation (`prepare_db.py`)

- Prepares the database for chatbot operations by:
  - Creating missing schemas (reuses create_schemas internally).
  - Creating or updating a primary Company record with id=1 using env-configured name and slug.
  - Creating or updating an admin Profile with id=1 including default admin email.
- Includes additional setup for a "Null User" Profile for system use.

Together, these commands streamline first-time database setup and ensure essential company and admin records exist for the chatbot to function properly.

---
