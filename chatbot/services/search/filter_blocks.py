"""
One alternative in an ``any_of`` search filter.

A search normally resolves to a single set of filters — organizations AND media
types AND exclusions — which covers everything except an OR that joins two
*different* fields: "PDFs from Shikshalokam, or DOCX from CSF". That needs
alternatives, and a FilterBlock is one of them.

The alternatives are OR'ed with each other and AND'ed with the flat fields
resolved alongside them, which keep their meaning and are never ignored:

    keep if  FLAT FIELDS  AND  (block0 OR block1 OR ...)

Its own module because llm_extractor builds these and must not import from
media_api_views. Both the alias widening and the translation to the vector
service's field names live here, so callers stay one line long.
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
