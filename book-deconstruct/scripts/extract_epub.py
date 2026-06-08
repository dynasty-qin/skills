"""Extract text from EPUB files"""
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import sys, os

epub_path = sys.argv[1]
output_path = sys.argv[2]

if not os.path.exists(epub_path):
    print(f"ERROR: File not found: {epub_path}")
    sys.exit(1)

book = epub.read_epub(epub_path)

all_text = []
for item in book.get_items():
    if item.get_type() == ebooklib.ITEM_DOCUMENT:
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        text = soup.get_text(separator='\n', strip=True)
        all_text.append(text)

with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n\n'.join(all_text))

print(f"Extracted {len(all_text)} sections to {output_path}")
