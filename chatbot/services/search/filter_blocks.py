"""
One branch of an ``any_of`` (OR) search filter.

Normal search: all conditions must match (AND across fields).
``any_of`` is for cross-field ORs like:
    "PDFs from Shikshalokam OR DOCX from CSF"

Each FilterBlock is one branch of that OR. Branches are OR'd together,
then AND'd with the regular flat filters:

    keep if  (flat filters)  AND  (block0 OR block1 OR ...)

Extracted into its own module so llm_extractor can build these without
importing media_api_views. Alias widening and field-name translation live
here — callers stay one-liners.
"""

from dataclasses import dataclass, field

from chatbot.services.search.vocabularies import expand_aliases


@dataclass
class FilterBlock:
    """
    One alternative: the same filter axes a flat search resolves to.

    Read exactly like the flat fields — OR within a list, AND between the
    fields, ``exclude_*`` dropping matches. What differs is only how blocks
    combine with each other.
    """
    organizations: list = field(default_factory=list)
    media_types: list = field(default_factory=list)
    exclude_organizations: list = field(default_factory=list)
    exclude_media_types: list = field(default_factory=list)

    def is_empty(self):
        """
        True when this block filters on nothing.

        An empty block matches every document, which would make the whole
        ``any_of`` a no-op, so callers drop these rather than send them.
        """
        return not (self.organizations or self.media_types
                    or self.exclude_organizations or self.exclude_media_types)

    def expanded(self, type_vocabulary):
        """
        The same block with its media types widened to every stored spelling.

        Qdrant's ``metadata.type`` holds both 'application/pdf' and a bare
        'pdf' depending on how a document was ingested, so a block asking for
        one would silently miss the other. The flat fields already get this
        treatment in media_api_views; blocks need it just as much.
        """
        return FilterBlock(
            organizations=list(self.organizations),
            media_types=expand_aliases(self.media_types, type_vocabulary),
            exclude_organizations=list(self.exclude_organizations),
            exclude_media_types=expand_aliases(
                self.exclude_media_types, type_vocabulary),
        )

    def as_payload(self):
        """
        This block in the vector service's field names, empty keys omitted.

        The one place ``media_types`` becomes ``file_type`` — the two services
        spell the same concept differently, and that translation should exist
        exactly once.
        """
        payload = {}
        for key, values in (
            ('organizations', self.organizations),
            ('file_type', self.media_types),
            ('exclude_organizations', self.exclude_organizations),
            ('exclude_file_type', self.exclude_media_types),
        ):
            if values:
                payload[key] = list(values)
        return payload
