from unittest import TestCase

from chatbot.services.search.filter_blocks import (
    FilterBlock,
    carry_shared_positive_qualifiers,
)


class SharedAlternativeQualifierTests(TestCase):
    def test_carries_leading_file_type_to_organization_alternatives(self):
        blocks = carry_shared_positive_qualifiers([
            FilterBlock(organizations=["a"], media_types=["application/pdf"]),
            FilterBlock(organizations=["b"]),
        ])

        self.assertEqual([
            block.as_payload() for block in blocks
        ], [
            {"organizations": ["a"], "file_type": ["application/pdf"]},
            {"organizations": ["b"], "file_type": ["application/pdf"]},
        ])

    def test_carries_trailing_file_type_to_organization_alternatives(self):
        blocks = carry_shared_positive_qualifiers([
            FilterBlock(organizations=["a"]),
            FilterBlock(organizations=["b"], media_types=["application/pdf"]),
        ])

        self.assertEqual(
            [block.media_types for block in blocks],
            [["application/pdf"], ["application/pdf"]],
        )

    def test_carries_shared_organization_to_format_alternatives(self):
        blocks = carry_shared_positive_qualifiers([
            FilterBlock(media_types=["application/pdf"]),
            FilterBlock(organizations=["a"], media_types=["text/plain"]),
        ])

        self.assertEqual(
            [block.organizations for block in blocks],
            [["a"], ["a"]],
        )

    def test_does_not_cross_product_unrelated_single_axis_branches(self):
        blocks = carry_shared_positive_qualifiers([
            FilterBlock(organizations=["a"]),
            FilterBlock(media_types=["application/pdf"]),
        ])

        self.assertEqual(
            [block.as_payload() for block in blocks],
            [
                {"organizations": ["a"]},
                {"file_type": ["application/pdf"]},
            ],
        )

    def test_carries_positive_but_not_exclusion_between_branches(self):
        blocks = carry_shared_positive_qualifiers([
            FilterBlock(
                organizations=["a"],
                media_types=["application/pdf"],
                exclude_media_types=["text/plain"],
            ),
            FilterBlock(organizations=["b"]),
        ])

        self.assertEqual(blocks[1].exclude_media_types, [])
        self.assertEqual(blocks[1].media_types, ["application/pdf"])

    def test_exclusion_wins_over_duplicate_positive_value(self):
        block = FilterBlock(
            organizations=["a", "b"],
            media_types=["application/pdf", "text/plain"],
            exclude_organizations=["a"],
            exclude_media_types=["application/pdf"],
        )

        self.assertEqual(block.organizations, ["b"])
        self.assertEqual(block.media_types, ["text/plain"])
        self.assertEqual(block.as_payload(), {
            "organizations": ["b"],
            "file_type": ["text/plain"],
            "exclude_organizations": ["a"],
            "exclude_file_type": ["application/pdf"],
        })
