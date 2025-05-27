import base64
import io
import os
from pathlib import Path
from typing import List, Dict, Any

from PIL import Image
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from pix2text.utils import select_device, box2list
from pix2text.doc_xl_layout import DocXLayoutParser
from pix2text.text_formula_ocr import TextFormulaOCR
from pix2text.table_ocr import TableOCR
from pix2text.layout_parser import ElementType  # Enum for element types


class AdvancedImageProcessor:

    def __init__(self, folder_path: str, openai_api_key: str):
        self.folder_path = Path(folder_path)
        if not self.folder_path.is_dir():
            raise ValueError(f"Folder not found: {folder_path}")

        self.llm = ChatOpenAI(
            model_name="gpt-4o",
            temperature=0,
            max_tokens=4096,
            api_key=openai_api_key
        )

        device = select_device(None)  # Auto-select device ('cpu', 'cuda', etc.)
        self.layout_parser = DocXLayoutParser.from_config(config=None, device=device)

        # TextFormulaOCR is needed for TableOCR dependencies
        # Configure enable_formula=False if formula recognition is not a priority here
        self.text_formula_ocr_instance = TextFormulaOCR.from_config(
            config=None, enable_formula=False, device=device
        )

        self.table_ocr = TableOCR.from_config(
            text_ocr=self.text_formula_ocr_instance.text_ocr,
            spellchecker=self.text_formula_ocr_instance.spellchecker,
            config=None,
            device=device
        )

        self.results: List[Dict[str, Any]] = []

    def _pil_to_base64(self, image_pil: Image.Image, format="PNG") -> str:
        buffered = io.BytesIO()
        image_pil.save(buffered, format=format)
        img_byte = buffered.getvalue()
        img_base64 = base64.b64encode(img_byte).decode('utf-8')
        return img_base64

    def _extract_text_with_llm(self, image_pil: Image.Image) -> str:
        base64_image = self._pil_to_base64(image_pil)
        try:
            response = self.llm.invoke(
                [
                    SystemMessage(content="You are an expert OCR agent. Extract all text accurately."),
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "Extract all text from the following image:"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    )
                ]
            )
            return response.content
        except Exception as e:
            print(f"Error extracting text with LLM: {e}")
            return ""

    def _extract_table_with_llm(self, image_pil: Image.Image) -> str:
        base64_image = self._pil_to_base64(image_pil)
        try:
            response = self.llm.invoke(
                [
                    SystemMessage(content="You are an expert table extraction agent. Convert the table in the image to a Markdown string."),
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "Extract the table from the following image as a Markdown formatted string:"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    )
                ]
            )
            return response.content
        except Exception as e:
            print(f"Error extracting table with LLM: {e}")
            return ""

    def process_folder(self) -> List[Dict[str, Any]]:
        self.results = []
        image_files = sorted([
            p for p in self.folder_path.glob("*") 
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ])

        print(f"Found {len(image_files)} image(s) to process in '{self.folder_path}'.")

        for i, image_path in enumerate(image_files):
            print(f"\nProcessing image {i+1}/{len(image_files)}: {image_path.name}")
            try:
                image_pil = Image.open(image_path).convert("RGB")
            except Exception as e:
                print(f"  Error opening image {image_path.name}: {e}")
                self.results.append({"image_path": str(image_path), "error": str(e), "elements": []})
                continue

            # Perform layout analysis
            # The `parse` method expects the raw image, not a path
            layout_out, _ = self.layout_parser.parse(image_pil.copy()) # Use a copy
            
            print(f"  Layout analysis found {len(layout_out)} elements.")

            extracted_elements_data = []
            for el_idx, element_info in enumerate(layout_out):
                element_type = element_info['type']
                # position is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], convert to [xmin, ymin, xmax, ymax]
                # then to (left, upper, right, lower) for PIL crop
                box_coords_list = box2list(element_info['position'])
                pil_crop_box = (box_coords_list[0], box_coords_list[1], box_coords_list[2], box_coords_list[3])
                
                cropped_image_pil = image_pil.crop(pil_crop_box)
                element_data = {
                    "id": el_idx,
                    "type": element_type.name, # Get the string name of the enum
                    "box_pix2text": box_coords_list, # Raw coordinates from pix2text
                    "content_llm": None,
                    "content_pix2text_table_ocr": None
                }

                if element_type in (ElementType.TEXT, ElementType.TITLE, ElementType.FORMULA):
                    print(f"    Extracting text from element {el_idx} ({element_type.name})...")
                    text_content = self._extract_text_with_llm(cropped_image_pil)
                    element_data["content_llm"] = text_content
                
                elif element_type == ElementType.TABLE:
                    print(f"    Extracting table from element {el_idx} ({element_type.name})...")
                    # Option 1: Use Pix2Text's TableOCR
                    try:
                        table_recognition_result = self.table_ocr.recognize(cropped_image_pil.copy(), out_markdown=True)
                        element_data["content_pix2text_table_ocr"] = table_recognition_result.get('markdown', '')
                    except Exception as e:
                        print(f"      Error with Pix2Text TableOCR: {e}")
                        element_data["content_pix2text_table_ocr"] = f"Error: {e}"

                    # Option 2: Use LLM for table extraction
                    llm_table_content = self._extract_table_with_llm(cropped_image_pil)
                    element_data["content_llm"] = llm_table_content
                
                elif element_type == ElementType.FIGURE:
                    # For figures, you might want to save the crop or get a description
                    print(f"    Element {el_idx} is a FIGURE. Skipping LLM extraction for now.")
                    element_data["content_llm"] = "Figure - no text/table extraction performed."
                
                else:
                    print(f"    Element {el_idx} is of type {element_type.name}. Skipping LLM extraction.")

                extracted_elements_data.append(element_data)
            
            self.results.append({
                "image_path": str(image_path),
                "elements": extracted_elements_data
            })
            print(f"  Finished processing {image_path.name}")
        
        print("\nAll images processed.")
        return self.results   