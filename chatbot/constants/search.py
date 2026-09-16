from chatbot.models.enums import FileTypeChoices

# Generic file-type categories that map to multiple canonical types.
# Kept separate from one-to-one aliases; categories are used only as prompt hints.
# Spreadsheet maps to XLS/XLSX, while CSV is matched only when explicitly requested.
# PPT/PPTX are not supported because they are not present in FileTypeChoices.
FILE_TYPE_CATEGORIES = {
    'word': [FileTypeChoices.DOC.value, FileTypeChoices.DOCX.value],
    'excel': [FileTypeChoices.XLS.value, FileTypeChoices.XLSX.value],
    'spreadsheet': [FileTypeChoices.XLS.value, FileTypeChoices.XLSX.value],
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
