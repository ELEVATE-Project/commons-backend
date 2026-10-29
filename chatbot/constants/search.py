from chatbot.models.enums import FileTypeChoices

FILE_TYPE_FIELD = 'file_type'
ORGANIZATION_FIELD = 'organization'

GENERIC_FILE_TYPE_NOUNS = frozenset({
    'document', 'documents', 'doc', 'docs', 'file', 'files',
})
COORDINATION_WORDS = frozenset({'or'})
NEGATION_PLACEHOLDERS = frozenset({'anything', 'nothing', 'neither', 'nor'})
FILTER_SCOPE_WORDS = frozenset({'anyone', 'anywhere', 'only', 'uploaded'})
NEGATION_SCOPE_BREAKERS = (
    'about', 'regarding', 'related to', 'covering', 'from', 'on',
)

# Generic file-type categories that map to multiple canonical types.
# Kept separate from one-to-one aliases; categories are used only as prompt hints.
# Spreadsheet maps to XLS/XLSX/CSV; Excel stays XLS/XLSX, so CSV is reached
# through "spreadsheet"
# PPT/PPTX are not supported because they are not present in FileTypeChoices.
FILE_TYPE_CATEGORIES = {
    'word': [FileTypeChoices.DOC.value, FileTypeChoices.DOCX.value],
    'excel': [FileTypeChoices.XLS.value, FileTypeChoices.XLSX.value],
    'spreadsheet': [
        FileTypeChoices.XLS.value, FileTypeChoices.XLSX.value,
        FileTypeChoices.CSV.value,
    ],
}

# The wordings that count as each category. "word doc(s)" is listed on purpose:
# bare "doc/docs" is the generic document noun and must NOT filter, but the
# "word" qualifier makes it the category term.
FILE_TYPE_CATEGORY_ALIASES = {
    'word': [
        'word', 'word file', 'word files', 'word document', 'word documents',
        'word doc', 'word docs', 'ms word', 'microsoft word',
    ],
    'excel': [
        'excel', 'excel file', 'excel files', 'excel sheet', 'excel sheets',
        'ms excel', 'microsoft excel',
    ],
    'spreadsheet': [
        'spreadsheet', 'spreadsheets', 'spread sheet', 'spread sheets',
    ],
}
