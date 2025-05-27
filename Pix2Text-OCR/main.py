from advanced_image_processor import AdvancedImageProcessor
import os
from pathlib import Path
import json
import shutil

sub_folder_to_process = "images_to_ocr"
current_folder = os.path.dirname(os.path.abspath(__file__))
img_folder = Path(os.path.join(current_folder, sub_folder_to_process))
html_folder = img_folder / "html"
output_file = img_folder / "advanced_ocr_results.json"

title = "La Stratégie des Douze Points Magiques de Dr Tan"

# Clean up any existing HTML folder before processing
if html_folder.exists():
    print(f"Removing existing HTML output folder: {html_folder}")
    shutil.rmtree(html_folder)

if output_file.exists():
    print(f"Removing existing output file: {output_file}")
    output_file.unlink()

if list(img_folder.glob("*.png")) or list(img_folder.glob("*.jpg")) or list(img_folder.glob("*.jpeg")):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("Please set the OPENAI_API_KEY environment variable.")
    processor = AdvancedImageProcessor(folder_path=str(img_folder), openai_api_key=api_key)
    
    # Process the folder to extract text and tables from images
    print("\n=== Processing Images ===\n")
    all_results = processor.process_folder()

    # Save results to JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    print(f"\nResults saved to {output_file}")
    
    # Generate HTML pages from the results
    print("\n=== Generating HTML Pages ===\n")
    html_dir = processor.render_html_pages(title=title)
    viewer_path = html_dir / "viewer.html"
    
    # Print the path to the viewer HTML file
    print(f"\nHTML viewer generated at: {viewer_path}")
    print(f"Open this file in your browser to view the results.")
    
    # Try to open the viewer in the default browser
    try:
        import webbrowser
        print("\nAttempting to open the viewer in your default browser...")
        webbrowser.open(viewer_path.as_uri())
    except Exception as e:
        print(f"Could not automatically open the viewer: {e}")
    
    # Print a summary of the results
    print("\n=== Results Summary ===\n")
    for res_item in all_results:
        print(f"Image: {res_item['image_path']}")
        if res_item.get('error'):
            print(f"  Error: {res_item['error']}")
            continue
        for el in res_item['elements']:
            print(f"  Element ID: {el['id']}, Type: {el['type']}")
            if el.get('content_llm'):
                content = el['content_llm']
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"    LLM Content: {preview}")
            if el.get('content_pix2text_table_ocr'):
                content = el['content_pix2text_table_ocr']
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"    Pix2Text Table OCR: {preview}")
else:
    print(f"No images found in {img_folder} to process for the example.")
