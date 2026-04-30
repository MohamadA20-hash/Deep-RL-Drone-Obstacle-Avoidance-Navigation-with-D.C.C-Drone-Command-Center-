from pypdf import PdfReader
r = PdfReader('Capstone_Report_Template (2).pdf')
for i, p in enumerate(r.pages):
    print(f'--- PAGE {i+1} ---')
    print(p.extract_text())
