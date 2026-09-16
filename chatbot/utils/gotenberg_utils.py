import os
import requests


gotenberg_url = os.getenv("GOTENBERG_URL")


def generate_pdf_with_gotenberg(html_content):

    files = {
        "files": ("index.html", html_content, "text/html"),
    }

    data = {
        "marginTop": "0cm",
        "marginBottom": "0cm",
        "marginLeft": "0cm",
        "marginRight": "0cm",
        "paperWidth": "210mm",
        "paperHeight": "297mm",
        "printBackground": "true",
    }

    try:
        response = requests.post(gotenberg_url, files=files, data=data)

        if response.status_code == 200:
            pdf = response.content
            return pdf
        else:
            return None
    except Exception as e:
        print("Error: ", e)
        return None
