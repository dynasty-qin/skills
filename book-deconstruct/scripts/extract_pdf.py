"""Extract text from PDF files using PyMuPDF"""
import fitz  # PyMuPDF
import sys, os

pdf_path = sys.argv[1]
output_path = sys.argv[2]

if not os.path.exists(pdf_path):
    print(f"ERROR: File not found: {pdf_path}")
    sys.exit(1)

doc = fitz.open(pdf_path)
all_text = []

for page in doc:
    text = page.get_text()
    if text.strip():
        all_text.append(text.strip())

doc.close()

with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n\n'.join(all_text))

print(f"Extracted {len(all_text)} pages to {output_path}")
