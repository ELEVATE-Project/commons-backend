import json
import os
from unittest import TestCase
from unittest.mock import patch

from chatbot.utils.search_filter_resolver import count_negation_cues, resolve_query_exact


DOC_MIME = "application/msword"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"

FILE_TYPE_VOCABULARY = {
    DOC_MIME: ["DOC", "doc", ".doc", "DOCs", "docs"],
    DOCX_MIME: ["DOCX", "docx", ".docx", "DOCXs", "docxs"],
    PDF_MIME: ["PDF", "pdf", ".pdf", "PDFs", "pdfs"],
}

SEARCH_ENV = {
    "SEARCH_FILTER_EXCLUDED_FILE_TYPE_ALIASES": json.dumps([
        "doc", "docs", "document", "documents", "file", "files",
    ]),
    "SEARCH_FILTER_NOISE_WORDS": json.dumps([
        "all", "doc", "docs", "document", "documents", "file", "files",
    ]),
    "SEARCH_FILTER_STOPWORDS": json.dumps([
        "all", "doc", "docs", "document", "documents", "file", "files",
    ]),
    "SEARCH_FILTER_NEGATION_WORDS": json.dumps(["not", "except", "without"]),
    "SEARCH_FILTER_NEGATION_WINDOW_WORDS": "5",
    "SEARCH_FILTER_MIN_FUZZY_LENGTH": "4",
}


class SearchFilterResolverFileTypeTests(TestCase):
    def resolve(self, query):
        with patch.dict(os.environ, SEARCH_ENV, clear=False):
            return resolve_query_exact(
                query,
                organization_vocabulary={},
                file_type_vocabulary=FILE_TYPE_VOCABULARY,
            )

    def test_generic_document_nouns_do_not_become_doc_filters(self):
        for noun in ("document", "documents", "doc", "docs", "file", "files"):
            with self.subTest(noun=noun):
                resolved = self.resolve(f"all {noun} except PDF")

                self.assertEqual(
                    [(match.slug, match.negated) for match in resolved.file_type],
                    [(PDF_MIME, True)],
                )

    def test_generic_nouns_are_protected_without_env_exclusions(self):
        env_without_exclusions = dict(SEARCH_ENV)
        env_without_exclusions.pop("SEARCH_FILTER_EXCLUDED_FILE_TYPE_ALIASES")
        with patch.dict(os.environ, env_without_exclusions, clear=True):
            resolved = resolve_query_exact(
                "all documents except PDF",
                organization_vocabulary={},
                file_type_vocabulary=FILE_TYPE_VOCABULARY,
            )

        self.assertEqual(
            [(match.slug, match.negated) for match in resolved.file_type],
            [(PDF_MIME, True)],
        )

    def test_dotted_doc_extension_is_an_explicit_doc_filter(self):
        resolved = self.resolve("find .doc files")

        self.assertEqual(
            [(match.slug, match.matched_span) for match in resolved.file_type],
            [(DOC_MIME, ".doc")],
        )

    def test_doc_format_is_an_explicit_doc_filter(self):
        resolved = self.resolve("find DOC format files")

        self.assertEqual(
            [(match.slug, match.matched_span) for match in resolved.file_type],
            [(DOC_MIME, "DOC format")],
        )

    def test_counts_exclusion_phrases_without_partial_word_matches(self):
        with patch.dict(os.environ, SEARCH_ENV, clear=False):
            self.assertEqual(
                count_negation_cues("PDF except DOCX and without CSV"),
                2,
            )
            self.assertEqual(count_negation_cues("notable PDF resources"), 0)

    def test_punctuation_does_not_hide_an_exclusion(self):
        resolved = self.resolve("PDF files except, DOCX files")

        self.assertEqual(
            [(match.slug, match.negated) for match in resolved.file_type],
            [(PDF_MIME, False), (DOCX_MIME, True)],
        )

    def test_exclusion_wins_over_the_same_positive_value(self):
        resolved = self.resolve("PDF files except PDF")

        self.assertEqual(
            [(match.slug, match.negated) for match in resolved.file_type],
            [(PDF_MIME, True)],
        )

    def test_double_file_type_exclusion_keeps_both_values(self):
        resolved = self.resolve("files except PDF and without DOCX")

        self.assertEqual(
            {(match.slug, match.negated) for match in resolved.file_type},
            {(PDF_MIME, True), (DOCX_MIME, True)},
        )

    def test_not_from_marks_the_organization_as_excluded(self):
        with patch.dict(os.environ, SEARCH_ENV, clear=False):
            resolved = resolve_query_exact(
                "PDF files not from Alpha Foundation",
                organization_vocabulary={"alpha": ["Alpha Foundation"]},
                file_type_vocabulary=FILE_TYPE_VOCABULARY,
            )

        self.assertEqual(
            [(match.slug, match.negated) for match in resolved.organization],
            [("alpha", True)],
        )
        self.assertEqual(
            [(match.slug, match.negated) for match in resolved.file_type],
            [(PDF_MIME, False)],
        )
