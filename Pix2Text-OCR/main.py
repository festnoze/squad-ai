from advanced_image_processor import AdvancedImageProcessor
import os
from pathlib import Path

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Please set the OPENAI_API_KEY environment variable.")

current_folder = os.path.dirname(os.path.abspath(__file__))
img_folder = Path(os.path.join(current_folder, "images"))

if list(img_folder.glob("*.png")) or list(img_folder.glob("*.jpg")):
    processor = AdvancedImageProcessor(folder_path=str(img_folder), openai_api_key=api_key)
    all_results = processor.process_folder()

    # You can now process 'all_results', e.g., print them or save to JSON
    output_file = img_folder / "advanced_ocr_results.json"
    import json
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    print(f"\nResults saved to {output_file}")
    
    # Example: Print summary
    for res_item in all_results:
        print(f"\nImage: {res_item['image_path']}")
        if res_item.get('error'):
            print(f"  Error: {res_item['error']}")
            continue
        for el in res_item['elements']:
            print(f"  Element ID: {el['id']}, Type: {el['type']}")
            if el.get('content_llm'):
                print(f"    LLM Content: {el['content_llm'][:100]}...")
            if el.get('content_pix2text_table_ocr'):
                print(f"    Pix2Text Table OCR: {el['content_pix2text_table_ocr'][:100]}...")
else:
    print(f"No images found in {img_folder} to process for the example.")


# # Create a dummy folder and images for testing if they don't exist
# current_script_dir = Path(__file__).parent
# test_folder = current_script_dir / "test_images_for_processor"
# if not test_folder.exists():
#     test_folder.mkdir(parents=True, exist_ok=True)
#     try:
#         # Create a simple dummy image with text
#         img_text = Image.new('RGB', (400, 100), color = 'white')
#         from PIL import ImageDraw
#         d = ImageDraw.Draw(img_text)
#         d.text((10,10), "Hello World", fill=(0,0,0))
#         d.text((10,50), "This is a test image.", fill=(0,0,0))
#         img_text.save(test_folder / "dummy_text_image.png")

#         # Create a simple dummy image with a table (visual representation)
#         img_table = Image.new('RGB', (400, 150), color = 'white')
#         d = ImageDraw.Draw(img_table)
#         d.text((10,10), "Col1 | Col2", fill=(0,0,0))
#         d.line((0, 30, 400, 30), fill=(0,0,0))
#         d.text((10,40), "A1   | B1", fill=(0,0,0))
#         d.line((0, 60, 400, 60), fill=(0,0,0))
#         d.text((10,70), "A2   | B2", fill=(0,0,0))
#         d.line((100, 0, 100, 150), fill=(0,0,0)) # Vertical line
#         img_table.save(test_folder / "dummy_table_image.png")
#         print(f"Created dummy images in {test_folder}")
#     except ImportError:
#         print("Pillow (PIL) is required to create dummy images for the example. Please install it.")
#     except Exception as e:
