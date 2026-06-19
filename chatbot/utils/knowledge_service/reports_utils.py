from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Alignment
import logging

logger = logging.getLogger("django")

def generate_xlsx_from_json(data, sheet_name="Project Report"):
    """
    Excel structure aligned with PDF sections.
    Sources are rendered as plain text with visible URLs.
    """

    try:
        if isinstance(data, dict):
            data = [data]

        if not data or not isinstance(data, list):
            raise ValueError("Invalid or empty data for Excel generation")

        item = data[0]

        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name

        headers = [
            "Project Title",
            "Problem Statement",
            "Objective",
            "Timeline",
            "Action Steps",
            "Sources",
        ]

        ws.append(headers)

        row = []

        for header in headers:
            value = item.get(header, "")
            if isinstance(value, list):
                value = "\n".join(
                    f"{idx + 1}. {str(v)}"
                    for idx, v in enumerate(value)
                )
            elif isinstance(value, dict):
                value = ""

            row.append(value)

        ws.append(row)
        
        for column_cells in ws.columns:
            max_length = 0
            col_letter = column_cells[0].column_letter

            for cell in column_cells:
                cell.alignment = Alignment(
                    wrap_text=True,
                    vertical="top"
                )

                if cell.value:
                    max_length = min(max(len(str(cell.value)), max_length), 50)

            ws.column_dimensions[col_letter].width = max_length + 2

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return output

    except Exception as e:
        logger.error("Error generating Excel: %s", e, exc_info=True)
        raise
