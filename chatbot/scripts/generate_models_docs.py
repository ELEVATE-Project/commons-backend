import os
import inspect
from django.apps import apps
from django.db.models import (
    ForeignKey,
    ManyToManyField,
    OneToOneField,
    TextChoices,
    IntegerChoices
)

import chatbot.models.enums as enums_module


DEFAULT_MODELS_DOCS_PATH = "docs/backend/models.md"
DEFAULT_ENUM_DOCS_PATH = "docs/backend/enums.md"


# =====================================================
# MODELS DOCUMENTATION GENERATOR (SCHEMA AWARE)
# =====================================================

def generate_models_docs(schema_name=None, output_path=None):
    """
    Generates documentation for Django models.

    Args:
        schema_name (str, optional):
            App label to filter models.
            Example: "chatbot", "accounts", "billing".
            If None → defaults to chatbot.models filter.

        output_path (str, optional):
            Output file path.
            Defaults to DEFAULT_MODELS_DOCS_PATH.
    """

    output_path = output_path or DEFAULT_MODELS_DOCS_PATH
    output = []

    # ---------------------------------------------------
    # HEADER (DYNAMIC)
    # ---------------------------------------------------

    output.append("# Django Models\n\n")

    if schema_name:
        output.append(f"`{schema_name}/models/`\n\n")
        output.append(
            f"This layer defines the complete database schema for the `{schema_name}` application.\n\n"
        )
    else:
        output.append("`chatbot/models/`\n\n")
        output.append(
            "This layer defines the complete database schema for the chatbot platform.\n\n"
        )

    output.append(
        "It manages persistence, relationships, constraints, indexing, and "
        "domain-level behavior across domain entities and system configuration.\n\n"
    )

    output.append("---\n\n")

    output.append("## Responsibilities of this Layer\n\n")
    output.append("- Define core domain entities\n")
    output.append("- Maintain relational integrity using ForeignKeys and constraints\n")
    output.append("- Enforce validation rules and uniqueness constraints\n")
    output.append("- Manage state and lifecycle tracking\n")
    output.append("- Support indexing and optimized querying\n")
    output.append("- Provide model-level helper methods for business logic\n")
    output.append("- Use enums for consistent state definitions\n")

    output.append("\n---\n")

    # ---------------------------------------------------
    # MODEL FILTERING
    # ---------------------------------------------------

    all_models = apps.get_models()

    if schema_name:
        models = [
            model for model in all_models
            if model._meta.app_label == schema_name
               and not model.__name__.startswith("Historical")
               and not model._meta.abstract
        ]
    else:
        models = [
            model for model in all_models
            if model.__module__.startswith("chatbot.models")
               and not model.__name__.startswith("Historical")
               and not model._meta.abstract
        ]

    models.sort(key=lambda m: m.__name__)

    # ---------------------------------------------------
    # MODEL DOCUMENTATION
    # ---------------------------------------------------

    for index, model in enumerate(models, start=1):

        meta = model._meta
        model_name = model.__name__
        module_path = model.__module__.replace(".", "/") + ".py"

        output.append(f"\n## {index}. {model_name}\n\n")
        output.append(f"`{module_path}`\n\n")

        # Purpose from docstring
        if model.__doc__:
            output.append("### Purpose\n\n")
            output.append(model.__doc__.strip() + "\n\n")

        output.append("### Fields\n\n")
        output.append("| Field | Type & Constraints | Description |\n")
        output.append("|-------|-------------------|-------------|\n")

        for field in meta.get_fields():

            if field.auto_created and not field.concrete:
                continue

            field_name = field.name
            field_type = field.__class__.__name__
            constraints = []

            if getattr(field, "unique", False):
                constraints.append("unique=True")

            if not getattr(field, "null", True):
                constraints.append("required")

            if hasattr(field, "max_length") and field.max_length:
                constraints.append(f"max_length={field.max_length}")

            if hasattr(field, "choices") and field.choices:
                constraints.append("choices")

            if isinstance(field, ForeignKey):
                constraints.append(f"ForeignKey → {field.related_model.__name__}")

            if isinstance(field, ManyToManyField):
                constraints.append(f"ManyToMany → {field.related_model.__name__}")

            if isinstance(field, OneToOneField):
                constraints.append(f"OneToOne → {field.related_model.__name__}")

            constraint_str = ", ".join(constraints)
            description = field.help_text if field.help_text else ""

            output.append(
                f"| {field_name} | {field_type} ({constraint_str}) | {description} |\n"
            )

        # Public methods
        methods = [
            func for func in dir(model)
            if callable(getattr(model, func))
            and not func.startswith("_")
            and func not in ["save", "delete"]
        ]

        if methods:
            output.append("\n### Methods\n\n")
            for method in methods:
                output.append(f"- `{method}()`\n")

        output.append("\n---\n")

    # ---------------------------------------------------
    # WRITE FILE
    # ---------------------------------------------------

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(output)

    print(f"Models documentation generated at {output_path}")


# =====================================================
# ENUMS DOCUMENTATION GENERATOR (UNCHANGED)
# =====================================================

def generate_enums_docs(output_path=None):

    output_path = output_path or DEFAULT_ENUM_DOCS_PATH
    output = []

    output.append("# Django Enums\n\n")
    output.append("`chatbot/models/enums.py`\n\n")
    output.append(
        "This document defines all enumeration classes used across the platform.\n\n"
    )
    output.append(
        "Enums ensure consistency, validation, and type safety for status fields, "
        "providers, configuration types, and workflow definitions.\n\n"
    )

    output.append("---\n")

    enum_classes = [
        (name, obj)
        for name, obj in inspect.getmembers(enums_module)
        if inspect.isclass(obj)
        and issubclass(obj, (TextChoices, IntegerChoices))
        and obj not in (TextChoices, IntegerChoices)
    ]

    enum_classes.sort(key=lambda x: x[0])

    for index, (name, obj) in enumerate(enum_classes, start=1):

        output.append(f"\n## {index}. {name}\n\n")

        if obj.__doc__:
            output.append("### Purpose\n\n")
            output.append(obj.__doc__.strip() + "\n\n")

        output.append("### Values\n\n")
        output.append("| Name | Value |\n")
        output.append("|------|-------|\n")

        for choice in obj:
            output.append(f"| {choice.name} | {choice.value} |\n")

        output.append("\n---\n")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(output)

    print(f"Enums documentation generated at {output_path}")


# =====================================================
# USAGE EXAMPLES
# =====================================================

# Default chatbot models
# generate_models_docs()

# Specific schema
# generate_models_docs(schema_name="accounts")

# Specific schema + custom output
# generate_models_docs(
#     schema_name="observability",
#     output_path="docs/apps/observability/models.md"
# )

# Enums (unchanged)
# generate_enums_docs()
