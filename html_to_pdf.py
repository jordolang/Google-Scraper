#!/usr/bin/env python3
import sys
from weasyprint import HTML

if __name__ == "__main__":
    html_file = sys.argv[1]
    pdf_file = html_file.replace('.html', '.pdf')
    
    HTML(html_file).write_pdf(pdf_file, stylesheets=None, 
                               presentational_hints=True)
    
    print(f"Created {pdf_file}")
