# import secrets
# print(secrets.token_urlsafe(128))
# import os
# print(os.getcwd())
# def list_files_recursive(folder_path):
#     all_files = []
#     for root, dirs, files in os.walk(folder_path):
#         for file in files:
#             all_files.append(os.path.join(root, file))

#     return all_files

# print(list_files_recursive("/mnt/e/Python/TDS_2025/generated-code"))

# import requests
# import pdfplumber
# import json

# # -----------------------------------------------------------
# # Configuration
# # -----------------------------------------------------------

# PDF_URL = "https://tds-llm-analysis.s-anand.net/demo"
# SUBMIT_URL = "https://tds-llm-analysis.s-anand.net/demo"

# EMAIL = "your-email"
# SECRET = "your secret"
# QUIZ_URL = "https://example.com/quiz-834"


# def download_pdf(url, filename="q834.pdf"):
#     """Download the PDF."""
#     response = requests.get(url)
#     response.raise_for_status()
#     with open(filename, "wb") as f:
#         f.write(response.content)
#     return filename


# def extract_value_sum(pdf_path):
#     """Extract table on page 2 and sum 'value' column."""
#     with pdfplumber.open(pdf_path) as pdf:
#         page = pdf.pages[1]   # page index 1 = page 2
#         table = page.extract_table()

#         # Convert rows to dicts based on header
#         header = table[0]
#         rows = table[1:]

#         # Find index of "value" column
#         try:
#             value_idx = header.index("value")
#         except ValueError:
#             raise Exception("No 'value' column found on page 2.")

#         # Sum numeric values
#         total = 0
#         for row in rows:
#             cell = row[value_idx]
#             if cell is not None:
#                 try:
#                     total += float(cell)
#                 except ValueError:
#                     pass  # ignore non-numeric values

#         return total


# def submit_answer(answer):
#     """Submit the computed answer as JSON."""
#     payload = {
#         "email": EMAIL,
#         "secret": SECRET,
#         "url": QUIZ_URL,
#         "answer": answer
#     }
#     print("Submitting:", payload)
#     response = requests.post(SUBMIT_URL, json=payload)
#     print("Server response:", response.status_code, response.text, response.json())


# if __name__ == "__main__":
#     # pdf_path = download_pdf(PDF_URL)
#     # total_value = extract_value_sum(pdf_path)
#     # print("Computed sum:", total_value)
#     submit_answer('adsf')

import requests
import os

result = requests.post(
    "https://zyrobeast-tds-2025-week-8-project.hf.space",
    json={
        "email": f"{os.getenv('EMAIL')}",
        "secret": f"{os.getenv('SECRET')}",
        "url": "https://tds-llm-analysis.s-anand.net/project2"
        }
)

print(result.status_code)
print(result.text)