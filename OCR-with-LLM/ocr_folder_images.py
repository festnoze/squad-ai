from pathlib import Path
import json, base64, os, shutil, tempfile
from PIL import Image
from jinja2 import Template
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

class OCRFolderImages:
        def __init__(self, folder: str) -> None:
                self.counter: int = 1
                self.pages: list[str] = []
                self.folder: Path = Path(folder)
                self.out: Path = self.folder / "html"
                self.out.mkdir(exist_ok=True)
                self.page_img_out_dir = self.out / "page_images"
                self.page_img_out_dir.mkdir(exist_ok=True)
                self.tmp: Path = Path(tempfile.mkdtemp())
                
                openai_api_key = os.getenv("OPENAI_API_KEY", None)
                if not openai_api_key:
                        raise ValueError("'OPENAI_API_KEY' environment variable is nowhere to be found.")
                self.llm: ChatOpenAI = ChatOpenAI(model_name="gpt-4o", temperature=0, max_tokens=4096, api_key=openai_api_key)

        def process_all_folder_images(self, title_backup: str) -> None:
                imgs: list[Path] = sorted([p for p in self.folder.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}])
                print(f"\rFound {len(imgs)} image(s) to process in '{self.folder}'.", end="")
                title = title_backup

                # Try to extract title from first image
                if imgs and any(imgs):
                        try:
                            extracted_title = self._extract_image(0, imgs[0])
                            if extracted_title:
                                    title = extracted_title
                        except Exception as e:
                                print(f"\n\n\n/!\\ Error parsing LLM response for title: {e}")
                
                # Process images
                print("\r\nProcessing images...", end="")
                for index, image_path in enumerate(imgs, 1):
                        self._extract_image(index, image_path)
                print("\rBuilding index page...", end="")
                self._build_index(title)
                print("\rBuilding viewer page...", end="")
                self._build_viewer(title)
                shutil.rmtree(self.tmp, ignore_errors=True)
                print("\rAll processing complete. Temporary files cleaned up.")

        def _extract_image(self, index: int, image_path: Path) -> None:
                print(f"\r[Image {index}/{sum(1 for _ in self.folder.glob('*'))}] Processing: {image_path.name}", end="")
                elements: list[dict[str, any]] = self._get_elements(image_path)
                print(f"\r  - Detected {len(elements)} element(s) in {image_path.name}", end="")
                pages_by_image: list[tuple[Path, list[dict[str, any]]]] = self._split_by_pages_in_image(elements, image_path)
                for page_path_and_items in pages_by_image:
                        html_name: str = f"{self.counter}.html"
                        self._render_page(page_path_and_items[0], page_path_and_items[1], html_name)
                        print(f"\r    - Rendered page to: \"{html_name}\".", end="")
                        self.pages.append(html_name)
                        self.counter += 1
                print(f"\r[Image {index}/{sum(1 for _ in self.folder.glob('*'))}] Finished processing {image_path.name}\n", end="")

        def _get_elements(self, image_path: Path) -> list[dict[str, any]]:
                img_content = base64.b64encode(image_path.read_bytes()).decode('utf-8')
                msg: list[any] = [
                        SystemMessage(content="You are a vision model"),
                        HumanMessage(content=[
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_content}"}},
                            {"type": "text", "text": "Analyze this image and extract all elements. Transcribe text exactly as it appears, letter by letter without corrections. For diagrams, charts, illustrations or any non-textual elements, identify them as 'image' type with precise bounding boxes.\n\nReturn a JSON array `elements` where each element has:\n- type: 'text', 'table', or 'image'\n- bbox: [x1,y1,x2,y2] with precise coordinates\n- text: transcribed content (for text elements only)\n\nIMPORTANT: Be very careful with non-textual elements like diagrams, illustrations, or charts - mark them as 'image' type with accurate bounding boxes. Even small diagrams or figures must be identified.\n\nDo not include any document title or external context in the transcribed output."}
                        ])
                ]
                resp: str = self.llm.invoke(msg, response_format={"type": "json_object"}).content
                return json.loads(resp)["elements"]

        def _split_by_pages_in_image(self, elements: list[dict[str, any]], img_path: Path) -> list[tuple[Path, list[dict[str, any]]]]:
                img: Image.Image = Image.open(img_path)
                w, h = img.size
                centers = sorted([(e["bbox"][0] + e["bbox"][2]) / 2 for e in elements])
                gaps = [b - a for a, b in zip(centers, centers[1:])]
                split_x = None
                if not gaps:
                    return [(img_path, elements)] # Should be caught by len(centers) < 2, but defensive

                gmax = max(gaps)
                split_x = None

                # Determine dynamic threshold percentage based on image width
                if w > 2500:  # Likely a wide two-page scan
                    threshold_percentage = 0.04  # 4%
                else:  # Narrower image, potentially single page or less wide two-page scan
                    threshold_percentage = 0.075  # 7.5%

                # Conditions for a valid split:
                # 1. The largest gap (gmax) must exceed the dynamic percentage of image width.
                # 2. The largest gap must be of a reasonable absolute minimum size (e.g., > 30px).
                # 3. The largest gap should not be excessively large relative to image width (e.g., < 60% of width),
                #    which might indicate one side is almost empty or not a typical page gutter.
                if (gmax > w * threshold_percentage and 
                    gmax > 30 and 
                    gmax < w * 0.60):
                        idx = gaps.index(gmax)
                        split_x = (centers[idx] + centers[idx + 1]) / 2
                
                if not split_x:
                        return [(img_path, elements)]
                left_el = [e for e in elements if (e["bbox"][0] + e["bbox"][2]) / 2 < split_x]
                right_el = [e for e in elements if e not in left_el]
                return [
                        self._crop_group(left_el, img, "L"),
                        self._crop_group(right_el, img, "R")
                ]

        def _crop_group(self, group: list[dict[str, any]], img: Image.Image, tag: str) -> tuple[Path, list[dict[str, any]]]:
                xs = [e["bbox"][0] for e in group] + [e["bbox"][2] for e in group]
                ys = [e["bbox"][1] for e in group] + [e["bbox"][3] for e in group]
                x1, y1, x2, y2 = max(min(xs) - 5, 0), max(min(ys) - 5, 0), min(max(xs) + 5, img.width), min(max(ys) + 5, img.height)
                crop = img.crop((x1, y1, x2, y2))
                tmp_path: Path = self.tmp / f"page_{self.counter}_{tag}.png"
                crop.save(tmp_path)
                for e in group:
                        e["bbox"] = [e["bbox"][0] - x1, e["bbox"][1] - y1, e["bbox"][2] - x1, e["bbox"][3] - y1]
                return (tmp_path, group)

        def _render_page(self, img_path: Path, elements: list[dict[str, any]], html_name: str) -> None:
                img: Image.Image = Image.open(img_path)
                w0, h0 = img.size
                blocks: list[str] = []
                img_counter_for_page = 0
                for el in elements:
                    x1, y1, x2, y2 = el["bbox"]
                    w, h = x2 - x1, y2 - y1
                    if el["type"] == "image":
                        # Validate that the bounding box has reasonable dimensions (minimum size check)
                        min_dimension_pixels = 50  # Minimum image dimension threshold
                        if (x2 - x1) >= min_dimension_pixels and (y2 - y1) >= min_dimension_pixels:
                            # Ensure coordinates are within image bounds
                            x1, y1 = max(0, x1), max(0, y1)
                            x2, y2 = min(w0, x2), min(h0, y2)
                            
                            crop = img.crop((x1, y1, x2, y2))
                            page_number_str = Path(html_name).stem
                            img_filename = f"page{page_number_str}_img{img_counter_for_page}.png"
                            img_save_path = self.page_img_out_dir / img_filename
                            crop.save(img_save_path)
                            img_src_relative_path = f"page_images/{img_filename}" # Relative to html file in self.out
                            blocks.append(f'<div class="element" style="margin-bottom:10px;"><img src="{img_src_relative_path}" style="max-width:100%;"></div>')
                            img_counter_for_page += 1
                        else:
                            print(f"\r  - Skipping too small image element: {x1},{y1},{x2},{y2}", end="")
                    else:
                        lines = ''.join(f'<p>{l}</p>' for l in el["text"].splitlines() if l.strip())
                        blocks.append(f'<div class="element" style="margin-bottom:10px;">{lines}</div>')
                tpl = Template("""<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;font-family:Arial;padding:20px;} .content{max-width:100%;}</style></head><body><div class="content">{{b|safe}}</div></body></html>""")
                (self.out / html_name).write_text(tpl.render(b=''.join(blocks), w=w0, h=h0), encoding="utf-8")

        def _build_index(self, title: str) -> None:
                # Links in 0.html should still allow viewer.html to load page X
                # So, href="viewer.html?p=..." is correct, or simply make them load page X directly in current viewer
                links = ''.join(f'<li><a href="javascript:void(0);" onclick="window.parent.loadPage(\'{Path(n).stem}\')">Page {Path(n).stem}</a></li>' for n in self.pages)
                summary_html_content = f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{{font-family:Arial,sans-serif;padding:20px;}} ul{{list-style-type:none;padding:0;}} li a{{text-decoration:none;color:#007bff;display:block;padding:8px 0;}} li a:hover{{color:#0056b3;}} h1{{margin-top:0;}}</style></head><body><h1>{title}</h1><ul>{links}</ul></body></html>'
                (self.out / "0.html").write_text(summary_html_content, encoding="utf-8")

        def _build_viewer(self, title: str) -> None:
                # Determine max_page_number by scanning the output directory for N.html files (N > 0)
                content_page_numbers: list[int] = []
                if self.out.exists():
                    for f_path in self.out.glob("*.html"):
                        if f_path.stem.isdigit() and f_path.stem != "0": # Exclude 0.html (summary)
                            try:
                                content_page_numbers.append(int(f_path.stem))
                            except ValueError:
                                pass # Not a simple number, ignore
                
                max_page_number = max(content_page_numbers) if content_page_numbers else 0

                viewer_html = f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\"><style>
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
                            // frame.contentWindow.focus(); // Optional: if focus is needed for keyboard nav
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
                        console.log('adjustFontSize called with delta:', delta);
                        currentFontSizePx += delta;
                        if (currentFontSizePx < minFontSizePx) currentFontSizePx = minFontSizePx;
                        if (currentFontSizePx > maxFontSizePx) currentFontSizePx = maxFontSizePx;
                        console.log('New currentFontSizePx:', currentFontSizePx);
                        applyFontSizeToIframe();
                    }}

                    function applyFontSizeToIframe() {{
                        console.log('applyFontSizeToIframe called. Target font size:', currentFontSizePx + 'px');
                        const iframe = document.getElementById('frame');
                        if (iframe && iframe.contentWindow && iframe.contentWindow.document && iframe.contentWindow.document.body) {{
                            iframe.contentWindow.document.body.style.fontSize = currentFontSizePx + 'px';
                            console.log('Successfully applied font size to iframe body.');
                        }} else {{
                            console.error('Failed to apply font size: iframe or its document/body not accessible.');
                            if (iframe && iframe.contentWindow) {{
                                console.log('iframe.contentWindow.document:', iframe.contentWindow.document);
                                if (iframe.contentWindow.document) {{
                                    console.log('iframe.contentWindow.document.body:', iframe.contentWindow.document.body);
                                }}
                            }}
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
                        <button onclick="loadPage(0)" title="Home">🏠</button>
                        <button onclick=\"navigatePage(-1)\" title=\"Previous\">◀</button>
                        <button onclick=\"navigatePage(1)\" title=\"Next\">▶</button>
                        <button onclick=\"adjustWidth(-widthStepPercent)\" title=\"Narrower\">➖</button>
                        <button onclick=\"adjustWidth(widthStepPercent)\" title=\"Wider\">➕</button>
                        <button onclick=\"adjustFontSize(-1)\" style=\"font-size: 18px; padding: 5px 8px;\">A-</button>
                        <button onclick=\"adjustFontSize(1)\" style=\"font-size: 18px; padding: 5px 8px;\">A+</button>
                    </div>
                    <div id=\"container\"><iframe id=\"frame\"></iframe></div>
                </body></html>"""
                (self.out / "viewer.html").write_text(viewer_html, encoding="utf-8")
