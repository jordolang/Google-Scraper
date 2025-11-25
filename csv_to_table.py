#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

def csv_to_html_table(csv_file):
    """Convert CSV to HTML table with Excel-like formatting"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body { 
                font-family: Calibri, Arial, sans-serif; 
                font-size: 9pt;
                margin: 10px;
            }
            table { 
                border-collapse: collapse; 
                width: 100%; 
                font-size: 8pt;
            }
            th, td { 
                border: 1px solid #d0d0d0; 
                padding: 4px 6px; 
                text-align: left;
                word-wrap: break-word;
                max-width: 150px;
            }
            th { 
                background-color: #4472C4; 
                color: white; 
                font-weight: bold;
            }
            tr:nth-child(even) { 
                background-color: #f2f2f2; 
            }
            h2 {
                margin: 5px 0;
                font-size: 12pt;
            }
        </style>
    </head>
    <body>
    """
    
    html += f"<h2>{Path(csv_file).name}</h2>\n"
    html += "<table>\n"
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        
        # Add header row
        html += "<tr>"
        for header in headers:
            html += f"<th>{header}</th>"
        html += "</tr>\n"
        
        # Add data rows
        for row in reader:
            html += "<tr>"
            for cell in row:
                # Clean up cell content
                cell_clean = cell.replace('\n', ' ').replace('\r', '').strip()
                html += f"<td>{cell_clean}</td>"
            html += "</tr>\n"
    
    html += "</table>\n</body>\n</html>"
    return html

if __name__ == "__main__":
    csv_file = sys.argv[1]
    html_content = csv_to_html_table(csv_file)
    
    output_file = csv_file.replace('.csv', '.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(output_file)
