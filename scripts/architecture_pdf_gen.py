import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DOCS_DIR = os.path.join(REPO_ROOT, 'docs')

MD_FILE = os.path.join(DOCS_DIR, 'architecture.md')
SVG_FILE = os.path.join(DOCS_DIR, 'architecture_diagram.svg')
HTML_FILE = os.path.join(DOCS_DIR, 'architecture_temp.html')
PDF_FILE = os.path.join(DOCS_DIR, 'architecture.pdf')
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def main():
    print("Converting Markdown to HTML...")
    result = subprocess.run(['pandoc', MD_FILE, '-t', 'html'], capture_output=True, text=True, encoding='utf-8', check=True)
    html_fragment = result.stdout
    
    print("Reading SVG...")
    svg_content = read_file(SVG_FILE)
    
    css = """
    <style>
        body { 
            font-family: 'Segoe UI', sans-serif; 
            line-height: 1.6;
            padding: 40px;
            max-width: 1200px;
            margin: 0 auto;
        }
        h1, h2, h3 { color: #2c3e50; margin-top: 1.5em; }
        code { background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }
        pre { background: #f4f4f4; padding: 15px; border-radius: 5px; }
        
        .diagram-container {
            margin: 40px 0;
            text-align: center;
        }
        
        .diagram-container svg {
            transform: scale(2.5);
            transform-origin: center top;
            margin-bottom: 400px;
        }
    </style>
    """
    
    diagram_div = f'<div class="diagram-container">{svg_content}</div>'
    
    # Replace the image reference
    lines = html_fragment.split('\n')
    new_lines = []
    for line in lines:
        if 'architecture.svg' in line:
            new_lines.append(diagram_div)
        else:
            new_lines.append(line)
    processed_html = '\n'.join(new_lines)

    final_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Architecture</title>
{css}
</head>
<body>
{processed_html}
</body>
</html>"""

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print(f"HTML saved: {HTML_FILE}")

    print("Generating PDF...")
    abs_html = os.path.abspath(HTML_FILE)
    abs_pdf = os.path.abspath(PDF_FILE)
    
    subprocess.run([
        EDGE_PATH,
        '--headless',
        '--disable-gpu',
        '--print-to-pdf=' + abs_pdf,
        '--no-pdf-header-footer',
        'file:///' + abs_html.replace('\\', '/')
    ], check=True)
    
    print(f"PDF created: {abs_pdf}")

if __name__ == "__main__":
    main()
