import base64
import io
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Coroutine

from PIL import Image
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from jinja2 import Template

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
        
        # HTML output related attributes
        self.html_out_dir: Path = self.folder_path / "html"
        self.page_img_out_dir: Path = None
        self.html_pages: List[str] = []

    def _pil_to_base64(self, image_pil: Image.Image, format="PNG") -> str:
        buffered = io.BytesIO()
        image_pil.save(buffered, format=format)
        img_byte = buffered.getvalue()
        img_base64 = base64.b64encode(img_byte).decode('utf-8')
        return img_base64

    async def _extract_text_with_llm(self, image_pil: Image.Image) -> str:
        base64_image = self._pil_to_base64(image_pil)
        try:
            response = await self.llm.ainvoke(
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

    async def _extract_table_with_llm(self, image_pil: Image.Image) -> str:
        base64_image = self._pil_to_base64(image_pil)
        try:
            response = await self.llm.ainvoke(
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

    async def _extract_whole_image_with_llm(self, image_pil: Image.Image) -> str:
        base64_image = self._pil_to_base64(image_pil)
        try:
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content="You are an expert OCR agent. Extract all text accurately and extract tables from the image to a Markdown string."),
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "Extract all text and tables from the following image:"},
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
            return response.content.replace("```markdown\n", "").replace("```plaintext\n", "").replace("```", "")
        except Exception as e:
            print(f"Error extracting text with LLM: {e}")
            return ""

    async def process_folder_async(self) -> List[Dict[str, Any]]:
        self.results = []
        image_files = sorted([
            p for p in self.folder_path.glob("*") 
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ], key=lambda p: p.name)

        print(f"Found {len(image_files)} image(s) to process in '{self.folder_path}'.")

        # First, analyze all images and prepare the element data
        all_extraction_tasks = []
        all_elements_mapping = []

        for i, image_path in enumerate(image_files):
            print(f"\nProcessing image {i+1}/{len(image_files)}: {image_path.name}")
            try:
                image_pil = Image.open(image_path).convert("RGB")
            except Exception as e:
                print(f"  Error opening image {image_path.name}: {e}")
                self.results.append({"image_path": str(image_path), "error": str(e), "elements": []})
                continue

            # Extract directly all text and tables from the full image
            # Add a tuple with: (task coroutine, image index, target type, field name)
            #to activate to add whole image OCR : analysis all_extraction_tasks.append((self._extract_whole_image_with_llm(image_pil.copy()), len(self.results), "whole", "content"))

            # Perform layout analysis
            layout_out, _ = self.layout_parser.parse(image_pil.copy())
            
            print(f"  Layout analysis found {len(layout_out)} elements.")

            # Prepare elements data and extraction tasks
            image_elements_data = []
            for el_idx, element_info in enumerate(layout_out):
                element_type = element_info['type']
                box_coords_list = box2list(element_info['position'])
                pil_crop_box = (box_coords_list[0], box_coords_list[1], box_coords_list[2], box_coords_list[3])
                
                cropped_image_pil = image_pil.crop(pil_crop_box)
                element_data = {
                    "id": el_idx,
                    "type": element_type.name, 
                    "box_pix2text": box_coords_list,
                    "content_llm": None,
                    "content_pix2text_table_ocr": None
                }

                # Create extraction tasks based on element type
                if element_type in (ElementType.TEXT, ElementType.TITLE, ElementType.FORMULA):
                    print(f"    Preparing text extraction for element {el_idx} ({element_type.name})...")
                    # Add to extraction tasks list without awaiting
                    # Add a tuple with: (task coroutine, mapping index, target type, field name)
                    all_extraction_tasks.append((self._extract_text_with_llm(cropped_image_pil), len(all_elements_mapping), "element", "content_llm"))
                
                elif element_type == ElementType.TABLE:
                    print(f"    Preparing table extraction for element {el_idx} ({element_type.name})...")
                    # Process TableOCR (synchronous) immediately
                    try:
                        table_recognition_result = self.table_ocr.recognize(cropped_image_pil.copy(), out_markdown=True)
                        element_data["content_pix2text_table_ocr"] = table_recognition_result.get('markdown', '')
                    except Exception as e:
                        print(f"      Error with Pix2Text TableOCR: {e}")
                        element_data["content_pix2text_table_ocr"] = f"Error: {e}"

                    # Add LLM table extraction to tasks list
                    # Add a tuple with: (task coroutine, mapping index, target type, field name)
                    all_extraction_tasks.append((self._extract_table_with_llm(cropped_image_pil), len(all_elements_mapping), "element", "content_llm"))
                
                elif element_type == ElementType.FIGURE:
                    print(f"    Element {el_idx} is a FIGURE. Skipping LLM extraction for now.")
                    element_data["content_llm"] = "Figure - no text/table extraction performed."
                
                else:
                    print(f"    Element {el_idx} is of type {element_type.name}. Skipping LLM extraction.")

                image_elements_data.append(element_data)
                all_elements_mapping.append((len(self.results), len(image_elements_data) - 1))
            
            self.results.append({
                "image_path": str(image_path),
                "elements": image_elements_data,
                "whole": None  # Will be populated later with whole-image extraction results
            })

        # Execute extraction tasks in batches
        print(f"\nPrepared {len(all_extraction_tasks)} LLM extraction tasks. Processing in batches...")
        batch_size = 50  # Maximum number of parallel calls
        
        # Process all extraction tasks in batches
        batch_start = time.time()
        for i in range(0, len(all_extraction_tasks), batch_size):
            batch = all_extraction_tasks[i:i+batch_size]
            print(f"Processing batch {i//batch_size + 1}/{(len(all_extraction_tasks) + batch_size - 1)//batch_size} ({len(batch)} tasks)...")
            
            # Run the batch of tasks concurrently
            batch_tasks = [task[0] for task in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            
            # Update element data with results
            for j, result in enumerate(batch_results):
                task_info = batch[j]
                idx = task_info[1]  # This is either a mapping index or an image index
                target_type = task_info[2]  # "element" or "whole"
                field_name = task_info[3]  # The field to update
                
                if target_type == "element":
                    # This is an element extraction task
                    image_idx, element_idx = all_elements_mapping[idx]
                    self.results[image_idx]["elements"][element_idx][field_name] = result
                elif target_type == "whole":
                    # This is a whole-image extraction task
                    image_idx = idx
                    self.results[image_idx]["whole"] = result
            batch_end = time.time()
            print(f"Batch {i//batch_size + 1}/{(len(all_extraction_tasks) + batch_size - 1)//batch_size} processed in {batch_end - batch_start:.2f}s.")
        
        print("\nAll images and elements processed.")
        return self.results

    def process_folder(self) -> List[Dict[str, Any]]:
        """Synchronous wrapper for process_folder_async"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.process_folder_async())
        
    def render_html_pages(self, title: str = None) -> Path:
        """Generate HTML pages from the results of process_folder()
        
        Args:
            title: Optional title for the HTML pages. If None, uses the folder name.
            
        Returns:
            Path to the HTML output directory
        """
        if not self.results:
            print("No results to render. Run process_folder() first.")
            return None
            
        # Create output directories
        self.html_out_dir.mkdir(exist_ok=True)
        self.page_img_out_dir = self.html_out_dir / "page_images"
        self.page_img_out_dir.mkdir(exist_ok=True)
        
        # Clean any previous contents
        for f in self.html_out_dir.glob("*.html"):
            f.unlink()
        for f in self.page_img_out_dir.glob("*.*"):
            f.unlink()
            
        self.html_pages = []
        
        # Use folder name as title if none provided
        if title is None:
            title = self.folder_path.name
            
        # Process each image result
        for i, result in enumerate(self.results):
            image_path = Path(result["image_path"])
            html_name = f"{i+1}.html"  # Start with page 1
            self.html_pages.append(html_name)
            self._render_page(image_path, html_name, result["elements"], None, mode="elements")
            print(f"Rendered HTML page {i+1}/{len(self.results)}: {html_name}")
            
        # Build index and viewer pages
        self._build_index(title)
        self._build_viewer(title)
        
        print(f"\nAll HTML pages generated in: {self.html_out_dir}")
        print(f"View the results by opening: {self.html_out_dir / 'viewer.html'}")
        
        return self.html_out_dir
        
    def _render_page(self, img_path: Path, html_name: str, elements: List[Dict[str, Any]] = None, whole: str = None, mode: str = "elements") -> None:
        """Render a single HTML page for an image with its elements
        
        Args:
            img_path: Path to the source image
            html_name: Name of the HTML file to create
            elements: List of elements from the image analysis
            whole: Text extracted from the whole image
            mode: Rendering mode - 'elements', 'whole', or 'both'
        """
        try:
            # For 'both' mode, process each mode separately and then merge the results
            if mode == "both" and elements is not None and whole is not None:
                print(f"  Rendering in 'both' mode for {html_name} - combining element and whole image extractions")
                
                # Create temporary files for each mode
                elements_html = self.html_out_dir / f"temp_elements_{html_name}"
                whole_html = self.html_out_dir / f"temp_whole_{html_name}"
                
                # Render each mode to a temporary file
                self._render_page(img_path, f"temp_elements_{html_name}", elements, None, mode="elements")
                self._render_page(img_path, f"temp_whole_{html_name}", None, whole, mode="whole")
                
                # Merge the results and write to the final file
                self._merge_html(elements_html, whole_html, self.html_out_dir / html_name)
                
                # Clean up temporary files
                if elements_html.exists():
                    elements_html.unlink()
                if whole_html.exists():
                    whole_html.unlink()
                    
                print(f"  Merged HTML content written to {html_name}")
                return
            
            img = Image.open(img_path)
            w0, h0 = img.size
            blocks = []
            
            if mode == "whole" and whole:
                # Render the whole image extraction result
                print(f"  Rendering whole image extraction for {html_name}")
                
                # Process markdown tables if present
                if "\n|" in whole:
                    # Extract tables and text separately
                    sections = []
                    current_text = []
                    in_table = False
                    table_lines = []
                    
                    for line in whole.splitlines():
                        if line.startswith('|') or (in_table and line.strip().startswith('|')):
                            if not in_table:
                                # If we have text before the table, add it
                                if current_text:
                                    sections.append({'type': 'text', 'content': '\n'.join(current_text)})
                                    current_text = []
                                in_table = True
                            table_lines.append(line)
                        else:
                            if in_table:
                                # Table ended, process it
                                if table_lines:
                                    sections.append({'type': 'table', 'content': '\n'.join(table_lines)})
                                    table_lines = []
                                in_table = False
                            current_text.append(line)
                    
                    # Add any remaining content
                    if in_table and table_lines:
                        sections.append({'type': 'table', 'content': '\n'.join(table_lines)})
                    elif current_text:
                        sections.append({'type': 'text', 'content': '\n'.join(current_text)})
                    
                    # Render each section
                    for section in sections:
                        if section['type'] == 'table':
                            # Render markdown table to HTML
                            table_html = '<div class="table-container" style="overflow-x:auto;"><table border="1" cellpadding="5" style="border-collapse:collapse;">'
                            lines = section['content'].strip().split('\n')
                            in_header = True
                            for line in lines:
                                if line.startswith('|'):
                                    cells = line.split('|')[1:-1]  # Remove first and last empty cells
                                    if all(c.strip().startswith(':--') or c.strip() == '--' for c in cells):
                                        in_header = False
                                        continue
                                    
                                    row_tag = 'th' if in_header else 'td'
                                    table_html += '<tr>'
                                    for cell in cells:
                                        table_html += f'<{row_tag}>{cell.strip()}</{row_tag}>'
                                    table_html += '</tr>'
                                    if in_header:
                                        in_header = False
                            table_html += '</table></div>'
                            blocks.append(f'<div class="element" style="margin-bottom:20px;">{table_html}</div>')
                        else:
                            # Regular text content
                            lines = ''.join(f'<p>{l}</p>' for l in section['content'].splitlines() if l.strip())
                            blocks.append(f'<div class="element" style="margin-bottom:20px;">{lines}</div>')
                else:
                    # Just text content, no tables
                    lines = ''.join(f'<p>{l}</p>' for l in whole.splitlines() if l.strip())
                    blocks.append(f'<div class="element" style="margin-bottom:10px;">{lines}</div>')
            
            elif mode == "elements" and elements:
                # Original element-by-element rendering
                img_counter_for_page = 0
                
                for el in elements:
                    # Skip elements with errors
                    if "error" in el:
                        continue
                        
                    element_type = el["type"]
                    box_coords = el["box_pix2text"]
                    x1, y1, x2, y2 = box_coords
                    
                    # Handle different element types
                    if element_type in ("FIGURE"):
                        # Ensure coordinates are within image bounds
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w0, x2), min(h0, y2)
                        
                        # Only process if dimensions are reasonable
                        min_dimension_pixels = 50
                        if (x2 - x1) >= min_dimension_pixels and (y2 - y1) >= min_dimension_pixels:
                            crop = img.crop((x1, y1, x2, y2))
                            page_number_str = Path(html_name).stem
                            img_filename = f"page{page_number_str}_img{img_counter_for_page}.png"
                            img_save_path = self.page_img_out_dir / img_filename
                            crop.save(img_save_path)
                            img_src_relative_path = f"page_images/{img_filename}"
                            blocks.append(f'<div class="element" style="margin-bottom:10px;"><img src="{img_src_relative_path}" style="max-width:100%;"></div>')
                            img_counter_for_page += 1
                    else:
                        # For text, title, table, etc.
                        content = el.get("content_llm", "")
                        if not content and "content_pix2text_table_ocr" in el:
                            content = el.get("content_pix2text_table_ocr", "")
                            
                        if content:
                            # For tables in markdown format, use a special rendering
                            if element_type == "TABLE" and "\n|" in content:
                                # Simple conversion of markdown table to HTML
                                table_html = '<div class="table-container" style="overflow-x:auto;"><table border="1" cellpadding="5" style="border-collapse:collapse;">'
                                lines = content.strip().split('\n')
                                in_header = True
                                for line in lines:
                                    if line.startswith('|'):
                                        cells = line.split('|')[1:-1]  # Remove first and last empty cells
                                        if all(c.strip().startswith(':--') or c.strip() == '--' for c in cells):
                                            in_header = False
                                            continue
                                        
                                        row_tag = 'th' if in_header else 'td'
                                        table_html += '<tr>'
                                        for cell in cells:
                                            table_html += f'<{row_tag}>{cell.strip()}</{row_tag}>'
                                        table_html += '</tr>'
                                        if in_header:
                                            in_header = False
                                table_html += '</table></div>'
                                blocks.append(f'<div class="element" style="margin-bottom:10px;">{table_html}</div>')
                            else:
                                # Regular text content
                                lines = ''.join(f'<p>{l}</p>' for l in content.splitlines() if l.strip())
                                blocks.append(f'<div class="element" style="margin-bottom:10px;">{lines}</div>')
            
            # Create the HTML page using template
            tpl = Template("""<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;font-family:Arial;padding:20px;} .content{max-width:100%;}</style></head><body><div class="content">{{b|safe}}</div></body></html>""")
            (self.html_out_dir / html_name).write_text(tpl.render(b=''.join(blocks), w=w0, h=h0), encoding="utf-8")
            
        except Exception as e:
            print(f"Error rendering page {html_name}: {e}")
            # Create a minimal error page
            error_html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{{margin:0;font-family:Arial;padding:20px;}} .error{{color:red;}}</style></head><body><h1 class="error">Error rendering page</h1><p>{str(e)}</p></body></html>'''
            try:
                (self.html_out_dir / html_name).write_text(error_html, encoding="utf-8")
            except Exception as e2:
                print(f"Could not even create error page: {e2}")
    
    def _build_index(self, title: str) -> None:
        """Build the index page (0.html) with links to all pages
        
        Args:
            title: Title for the index page
        """
        # Links to allow viewer.html to load the pages
        links = ''.join(f'<li><a href="javascript:void(0);" onclick="window.parent.loadPage(\'{Path(n).stem}\')">{Path(n).stem}</a></li>' for n in self.html_pages)
        summary_html_content = f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{{font-family:Arial,sans-serif;padding:20px;}} ul{{list-style-type:none;padding:0;}} li a{{text-decoration:none;color:#007bff;display:block;padding:8px 0;}} li a:hover{{color:#0056b3;}} h1{{margin-top:0;}}</style></head><body><h1>{title}</h1><ul>{links}</ul></body></html>'
        (self.html_out_dir / "0.html").write_text(summary_html_content, encoding="utf-8")
    
    def _merge_html(self, elements_html: Path, whole_html: Path, output_html: Path) -> None:
        """Merge the contents of two HTML files, intelligently choosing the best content
        
        Args:
            elements_html: Path to the HTML file from elements mode
            whole_html: Path to the HTML file from whole mode
            output_html: Path to write the merged HTML file
        """
        try:
            if not elements_html.exists() or not whole_html.exists():
                print(f"  Warning: One or both source HTML files don't exist, cannot merge")
                return
                
            # Extract content divs from each HTML file
            elements_content = ""
            whole_content = ""
            
            # Read both HTML files
            elements_html_text = elements_html.read_text(encoding="utf-8")
            whole_html_text = whole_html.read_text(encoding="utf-8")
            
            # Extract the content between <div class="content"> and </div>
            import re
            elements_match = re.search(r'<div class="content">(.*?)</div></body></html>', elements_html_text, re.DOTALL)
            whole_match = re.search(r'<div class="content">(.*?)</div></body></html>', whole_html_text, re.DOTALL)
            
            if elements_match and whole_match:
                elements_content = elements_match.group(1)
                whole_content = whole_match.group(1)
                
                # Extract individual div elements from both contents
                elements_divs = re.findall(r'<div class="element".*?>(.*?)</div>', elements_content, re.DOTALL)
                whole_divs = re.findall(r'<div class="element".*?>(.*?)</div>', whole_content, re.DOTALL)
                
                # Intelligent merging based on content length and completeness
                # For tables: prefer whole mode if present (usually more accurate for table structure)
                # For text: compare and take the longer/more complete version
                
                # First, extract tables from whole mode (they're more reliable there)
                whole_tables = []
                non_table_whole_divs = []
                for div in whole_divs:
                    if '<div class="table-container"' in div:
                        whole_tables.append(f'<div class="element" style="margin-bottom:20px;">{div}</div>')
                    else:
                        non_table_whole_divs.append(div)
                
                # Next, process text content by comparing for completeness
                merged_text_divs = []
                elements_text_content = "\n".join(div for div in elements_divs if '<div class="table-container"' not in div)
                whole_text_content = "\n".join(non_table_whole_divs)
                
                # If one source is significantly longer, prefer it
                if len(whole_text_content) > len(elements_text_content) * 1.2:
                    for div in non_table_whole_divs:
                        merged_text_divs.append(f'<div class="element" style="margin-bottom:20px;">{div}</div>')
                elif len(elements_text_content) > len(whole_text_content) * 1.2:
                    for div in elements_divs:
                        if '<div class="table-container"' not in div:
                            merged_text_divs.append(f'<div class="element" style="margin-bottom:10px;">{div}</div>')
                else:
                    # If lengths are comparable, check for specific patterns and choose the better one
                    # This is a simple heuristic - take the text that has fewer breaks for the same content
                    # Extract just the text without HTML tags for comparison
                    elements_plain_text = re.sub(r'<.*?>', '', elements_text_content)
                    whole_plain_text = re.sub(r'<.*?>', '', whole_text_content)
                    
                    # Count words as a heuristic for text completeness
                    elements_words = len(elements_plain_text.split())
                    whole_words = len(whole_plain_text.split())
                    
                    if whole_words >= elements_words * 0.9:  # If whole is at least 90% as complete
                        for div in non_table_whole_divs:
                            merged_text_divs.append(f'<div class="element" style="margin-bottom:20px;">{div}</div>')
                    else:
                        for div in elements_divs:
                            if '<div class="table-container"' not in div:
                                merged_text_divs.append(f'<div class="element" style="margin-bottom:10px;">{div}</div>')
                
                # Now combine tables from whole mode with the best text content
                merged_blocks = whole_tables + merged_text_divs
                
                # Create the final HTML page
                tpl = Template("""<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;font-family:Arial;padding:20px;} .content{max-width:100%;}</style></head><body><div class="content">{{b|safe}}</div></body></html>""")
                output_html.write_text(tpl.render(b=''.join(merged_blocks)), encoding="utf-8")
                
            else:
                print(f"  Warning: Could not extract content from HTML files, copying whole mode file")
                # If extraction failed, just use the whole file
                if whole_html.exists():
                    import shutil
                    shutil.copy(whole_html, output_html)
                    
        except Exception as e:
            print(f"Error merging HTML files: {e}")
            # Create a minimal error page
            error_html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{{margin:0;font-family:Arial;padding:20px;}} .error{{color:red;}}</style></head><body><h1 class="error">Error merging HTML</h1><p>{str(e)}</p></body></html>'''
            output_html.write_text(error_html, encoding="utf-8")
    
    def _build_viewer(self, title: str) -> None:
        """Build the viewer.html page that displays all pages
        
        Args:
            title: Title for the viewer
        """
        # Determine max_page_number by scanning the output directory for N.html files (N > 0)
        content_page_numbers: List[int] = []
        if self.html_out_dir.exists():
            for f_path in self.html_out_dir.glob("*.html"):
                if f_path.stem.isdigit() and f_path.stem != "0":  # Exclude 0.html (summary)
                    try:
                        content_page_numbers.append(int(f_path.stem))
                    except ValueError:
                        pass  # Not a simple number, ignore
        
        max_page_number = max(content_page_numbers) if content_page_numbers else 0

        viewer_html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            html, body {{
                margin: 0; padding: 0; height: 100%;
                background-color: #f8f8f8; font-family: Arial, sans-serif;
            }}
            #container {{
                display: flex; justify-content: center; align-items: flex-start;
                height: 100vh; padding-top: 40px; padding-bottom: 20px; box-sizing: border-box;
            }}
            iframe {{
                border: 1px solid #cccccc; width: 50%; /* Initial width, controlled by JS */
                height: 100%; box-sizing: border-box; background-color: #ffffff;
            }}
            #bar {{
                position: fixed; top: 20px; left: 20px;
                background-color: rgba(240, 240, 240, 0.95); padding: 8px; border-radius: 6px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 1000; display: flex; gap: 6px;
            }}
            #bar button {{
                background-color: #f9f9f9; border: 1px solid #bbb; border-radius: 4px;
                padding: 6px 10px; cursor: pointer; font-size: 14px; min-width: 30px; text-align: center;
            }}
            #bar button:hover {{ background-color: #e7e7e7; }}
            @media (max-width: 768px) {{
                #container {{ padding-top: 70px; padding-left: 10px; padding-right: 10px; padding-bottom: 10px; }}
                iframe {{ width: 95% !important; /* Mobile fixed width */ }}
                #bar {{ top: 10px; left: 10px; padding: 6px; gap: 4px; }}
                #bar button {{ padding: 5px 8px; font-size: 12px; }}
            }}
        </style>
        <script>
            let currentWidthPercent = 50;
            const minWidthPercent = 20;
            const maxWidthPercent = 100;
            const widthStepPercent = 5;

            let currentFontSizePx = 16; // Default font size in pixels
            const minFontSizePx = 8;
            const maxFontSizePx = 30;

            const maxPage = {max_page_number};

            function loadPage(pageNumStr) {{
                const u = new URLSearchParams(location.search);
                const currentPage = u.get('p');
                if (currentPage === pageNumStr) return; // Avoid reloading same page

                const frame = document.getElementById('frame');
                
                frame.onload = function() {{
                    // This function is called AFTER the new content is loaded into the iframe
                    // Apply width for mobile if necessary, or restore percentage width
                    if (!(window.innerWidth <= 768 && getComputedStyle(frame).width === '95%')) {{
                       frame.style.width = currentWidthPercent + '%';
                    }}
                    applyFontSizeToIframe(); // Now it's safe to apply font size
                }};
                
                frame.src = pageNumStr + '.html';
                document.title = pageNumStr + '.html';
                history.pushState({{page: pageNumStr}}, '', '?p=' + pageNumStr);
            }}

            function navigatePage(delta) {{
                const u = new URLSearchParams(location.search);
                let currentPageNum = parseInt(u.get('p') || '0');
                let newPageNum = currentPageNum + delta;

                if (newPageNum < 0) newPageNum = 0;
                else if (newPageNum > maxPage) newPageNum = maxPage; // Cap at maxPage
                
                loadPage(newPageNum);
            }}

            function adjustWidth(deltaPercent) {{
                const iframe = document.getElementById('frame');
                if (window.innerWidth <= 768 && getComputedStyle(iframe).width === '95%') {{
                    return; // Mobile width is fixed by CSS
                }}
                currentWidthPercent += deltaPercent;
                if (currentWidthPercent < minWidthPercent) currentWidthPercent = minWidthPercent;
                if (currentWidthPercent > maxWidthPercent) currentWidthPercent = maxWidthPercent;
                iframe.style.width = currentWidthPercent + '%';
            }}

            function adjustFontSize(delta) {{
                currentFontSizePx += delta;
                if (currentFontSizePx < minFontSizePx) currentFontSizePx = minFontSizePx;
                if (currentFontSizePx > maxFontSizePx) currentFontSizePx = maxFontSizePx;
                applyFontSizeToIframe();
            }}

            function applyFontSizeToIframe() {{
                const iframe = document.getElementById('frame');
                if (iframe && iframe.contentWindow && iframe.contentWindow.document && iframe.contentWindow.document.body) {{
                    iframe.contentWindow.document.body.style.fontSize = currentFontSizePx + 'px';
                }}
            }}

            window.onload = () => {{
                const u = new URLSearchParams(location.search);
                const initialPage = u.get('p') || '0'; // Default to page '0'
                loadPage(initialPage);
            }};
        </script></head>
        <body>
            <h1 style="text-align: center; margin-top: 10px; margin-bottom: 0; font-size: 28px;">{title}</h1>
            <div id="bar">
                <button onclick="loadPage('0')" title="Home">🏠</button>
                <button onclick="navigatePage(-1)" title="Previous">◀</button>
                <button onclick="navigatePage(1)" title="Next">▶</button>
                <button onclick="adjustWidth(-widthStepPercent)" title="Narrower">➖</button>
                <button onclick="adjustWidth(widthStepPercent)" title="Wider">➕</button>
                <button onclick="adjustFontSize(-1)" style="font-size: 18px; padding: 5px 8px;">A-</button>
                <button onclick="adjustFontSize(1)" style="font-size: 18px; padding: 5px 8px;">A+</button>
            </div>
            <div id="container"><iframe id="frame"></iframe></div>
        </body></html>'''
        (self.html_out_dir / "viewer.html").write_text(viewer_html, encoding="utf-8")