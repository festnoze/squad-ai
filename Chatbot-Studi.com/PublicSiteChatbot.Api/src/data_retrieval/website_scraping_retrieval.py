from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file
from selenium import webdriver
from selenium.webdriver.common.by import By
from common_tools.models.file_already_exists_policy import FileAlreadyExistsPolicy
from common_tools.helpers.ressource_helper import Ressource

class WebsiteScrapingRetrieval:
    def __init__(self):
        pass

    def scrape_all_trainings(self, max_pagination=17, batch_size=5):
        txt.activate_print = True
        total_start_time = time.time()
        all_trainings_links_filename = "outputs/all_trainings_links.json"
        txt.print_with_spinner("Start scraping all trainings links:")
        
        # Load or retrieve all training links
        all_trainings_urls = self.scrape_or_load_all_trainings_links(max_pagination, all_trainings_links_filename)
        
        pages_out_dir = "outputs/scraped-full/"
        sections_out_dir = 'outputs/scraped/'

        self.parallel_scrape_content_missing_webpages(all_trainings_urls, pages_out_dir, batch_size, only_missing_webpages_to_scrape= True)
        self.save_sections_from_scraped_pages(pages_out_dir, sections_out_dir)

        elapsed = txt.get_elapsed_str(txt.get_elapsed_seconds(total_start_time, time.time()))
        txt.print(f"Scraping all trainings contents completed and saved in {elapsed}") 

    def scrape_or_load_all_trainings_links(self, max_pagination, all_trainings_links_filename):
        all_trainings_urls = []
        if file.exists(all_trainings_links_filename):
            links_str = file.read_file(all_trainings_links_filename)
            all_trainings_urls = json.loads(links_str)
            txt.stop_spinner_replace_text(f"Loaded {len(all_trainings_urls)} trainings links.")
        else:
            all_trainings_urls = self.scrape_all_trainings_links(max_pagination)
            file.write_file(all_trainings_urls, all_trainings_links_filename)
            txt.stop_spinner_replace_text(f"Retrieved {len(all_trainings_urls)} trainings links completed.")
        return all_trainings_urls

    def scrape_all_trainings_links(self, max_pagination=17, batch_size=5):
        all_outputs = []

        for i in range(1, max_pagination + 1, batch_size):
            batch = list(range(i, i + batch_size))

            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = [
                    executor.submit(self.get_training_links_one_page, page)
                    for page in batch
                ]

                # Collect the results as each future completes
                for future in as_completed(futures):
                    try:
                        results = future.result()
                        if results and any(results):  # Ensure the result is not None
                            all_outputs.extend(results)
                    except Exception as e:
                        print(f"An error occurred: {e}")
        return all_outputs

    def get_training_links_one_page(self, page):        
        base_url = "https://www.studi.com/fr/formations?training%5Bpage%5D="
        training_links = []
        options = webdriver.ChromeOptions()
        options.add_argument("--log-level=3")  # Suppress logging
        driver = webdriver.Chrome(options=options)
        url = base_url + str(page)
        driver.get(url)
        time.sleep(2)
        html: str = driver.page_source
        soup: BeautifulSoup = BeautifulSoup(html, 'html.parser')
        hits_list = soup.find('ol', class_='ais-Hits-list')
        if hits_list:
            for item in hits_list.find_all('a', href=True):
                href: str = item['href']
                if href.startswith("/fr/formation/"):
                    training_links.append("https://www.studi.com" + href)
        else:
            print(f"No content found on page {page}")
        driver.quit()
        return training_links

    def get_training_links_all_pages_by_soup(self, max_pagination = 17):
        training_links = []
        base_url = "https://www.studi.com/fr/formations?training%5Bpage%5D="
        for page in range(1, max_pagination + 1):
            url = base_url + str(page)
            response = requests.get(url)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find all links to training programs (update the class or tag based on actual HTML structure)
                cards = soup.find_all('div', class_='card__content')
                for div in cards:
                    link = div.find('a', href=True)
                    if not link or not link.has_attr('href'):
                        continue
                    href = link['href']
                    card__content = link.find
                    if href.startswith("/fr/formation/"):
                        training_links.append("https://www.studi.com" + href)
            else:
                print(f"Failed to retrieve page {page}")
        
        return training_links
    
    def parallel_scrape_content_missing_webpages(self, pages_urls:list[str], out_dir:str, batch_size:int = 10, only_missing_webpages_to_scrape= True):        
        # Remove already scraped webpages
        if only_missing_webpages_to_scrape:
            links_to_process = [
                link for link in pages_urls
                if not file.exists(f"{out_dir}{link.split('/')[-1]}.json")
            ]
        else:
            links_to_process = pages_urls

        # scrape pages in parallel batches
        for i in range(0, len(links_to_process), batch_size):
            batch = links_to_process[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                executor.map(self.scrape_and_save_webpage_content, batch)    

    def scrape_and_save_webpage_content(self, training_url):
        training_name = training_url.split("/")[-1]
        txt.print(f"Scraping training content of: '{training_name}'")
        start_time = time.time()
        page_content = self.retrieve_page_content(training_url)
        file.write_file({ 'name': training_name, 'url': training_url, 'content': page_content }, f"outputs/scraped-full/{training_name}.json")
    
    def retrieve_page_content(self, url):
        driver = webdriver.Chrome()
        driver.get(url)
        time.sleep(2)

        result = None
        if "Ce contenu n'existe pas ou plus." in driver.page_source:
            txt.print(f">>>>> Page not found: '{url}'")
        else:
            result = driver.page_source
        driver.quit()
        return result
    
    def save_sections_from_scraped_pages(self, pages_out_dir, sections_out_dir):
        webpages_json = file.get_files_contents(pages_out_dir, 'json')
        for webpage_json_str in webpages_json:
            webpage_json = json.loads(webpage_json_str)
            sections = self.extract_sections_from_content(webpage_json['name'], webpage_json['url'], webpage_json['content'])
            self.check_for_html_tags(sections)
            out_filename = f"{sections_out_dir}{webpage_json['name']}.json"
            file.write_file(sections, out_filename, FileAlreadyExistsPolicy.Override)

    def check_for_html_tags(self, sections):
        inline_html_tags = [
            "a", "abbr", "b", "bdi", "bdo", "big", "br", "cite", "code", "dfn", "em", 
            "i", "img", "input", "kbd", "label", "mark", "q", "s", "samp", "small", 
            "span", "strong", "sub", "sup", "time", "u", "var", "wbr"
        ]
        # count then display the count of each tag in each section
        for tag in inline_html_tags:
            count = 0
            for key, value in sections.items():
                count += value.count(f"<{tag}>")
                count += value.count(f"</{tag}>")
            if count > 0:
                txt.print(f"Found {count} '{tag}' tags in sections.")

    def extract_sections_from_content(self, webpage_name: str, webpage_url: str, webpage_content: str, section_classes=['lame-header-training', 'lame-bref', 'lame-programme', 'lame-cards-diploma', 'lame-methode', 'lame-modalites', 'lame-financement', 'lame-simulation'], section_ids=['jobs']):
        sections = {}
        soup = BeautifulSoup(webpage_content, 'html.parser')
        title_content_div = soup.find('div', class_='title-content')
        
        # Extract the title from the h1 tag
        if title_content_div:             
            h1 = title_content_div.find('h1')
            if h1:
                title = h1.get_text(strip=True)
                sections['title'] = Ressource.remove_curly_brackets(title)
            else:
                sections['title'] = Ressource.remove_curly_brackets(webpage_name)
                txt.print(f"/!\\ Title not found in 'title-content' div. Use the one from url instead: '{webpage_name}'.")

            # Extract the academic level from 'tag-w' ul
            tag_w_ul = title_content_div.find('ul', class_='tag-w')
            if tag_w_ul:
                # Find 'li' elements with class 'tag' inside 'tag-w' ul
                li_tags = tag_w_ul.find_all('li', class_='tag')
                if li_tags and any(li_tags):
                    academic_levels = [li_tag.get_text(strip=True) for li_tag in li_tags]
                    if len(academic_levels) != 1:
                        txt.print(f"Found {len(academic_levels)} academic levels for '{webpage_name}'.")
                    sections['academic_level'] = academic_levels[0]

        # Extract content from the specified sections by their classes
        for section_class in section_classes:
            section = soup.find('section', class_=section_class)
            if section:
                key = section_class.replace('lame-', '')
                processed_section = self.process_section(section)
                sections[key] = self._build_bullet_lists_str_from_nested_lists(processed_section)

        # Extract content from the specified sections by their IDs
        for section_id in section_ids:
            section = soup.find('section', id=section_id)
            if section:
                key = section_id.replace('jobs', 'metiers')
                processed_section = self.process_section(section)
                sections[key] = self._build_bullet_lists_str_from_nested_lists(processed_section)

        sections['url'] = webpage_url
        return sections

    def process_section(self, section):
        content_list = []

        # Replace <br> tags with newline characters
        for br in section.find_all('br'):
            br.replace_with("\n")         

        # Find all accordion items
        accordion_items = section.find_all('div', class_='accordion__item')
        if accordion_items:
            for item in accordion_items:
                # Extract title from accordion-head
                accordion_head = item.find('div', class_='accordion-head')
                if accordion_head:
                    title_span = accordion_head.find('span', class_='title')
                    title = Ressource.remove_curly_brackets(title_span.get_text(strip=True)) if title_span else ''
                else:
                    title = ''

                # Initialize a dict to hold this item's content
                item_content = {'title': title, 'content': []}

                # Extract content from accordion-content
                accordion_content = item.find('div', class_='accordion-content')
                if accordion_content:
                    # Collect content under this item
                    sub_content = []

                    # Extract spans with class 'accordion-content__title'
                    spans = accordion_content.find_all('span', class_='accordion-content__title')
                    for span in spans:
                        bp_text = span.get_text(strip=True)
                        if bp_text:
                            sub_content.append(Ressource.remove_curly_brackets(bp_text))

                    # Extract bullet points from divs with class 'tag-w' and spans with class 'tag'
                    tag_w_divs = accordion_content.find_all('div', class_='tag-w')
                    for tag_w in tag_w_divs:
                        # Get the label before the tags
                        label = tag_w.get_text(separator=' ', strip=True).split(':')[0]
                        tags = tag_w.find_all('span', class_='tag')
                        tags_text = self._build_bullet_lists_str_from_nested_lists([tag.get_text(strip=True) for tag in tags])
                        if label and tags_text:
                            sub_content.append(f"{label}: {tags_text}")

                    # Extract list items from unordered lists
                    ul_lists = accordion_content.find_all('ul')
                    for ul in ul_lists:
                        li_items = ul.find_all('li')
                        li_sublist = []
                        for li in li_items:
                            li_text = Ressource.remove_curly_brackets(li.get_text(strip=True))
                            if li_text:
                                li_sublist.append(li_text)
                        if li_sublist:
                            sub_content.append(li_sublist)  # Append the list as a sublist

                    # Extract any remaining text paragraphs
                    paragraphs = accordion_content.find_all('p')
                    for p in paragraphs:
                        p_text = Ressource.remove_curly_brackets(p.get_text(strip=True))
                        if p_text and p_text not in sub_content:
                            sub_content.append(p_text)

                    # Set the content
                    item_content['content'] = sub_content

                else:
                    raise Exception(f"Accordion item '{title}' has no content.")

                # Append this item to the content list
                content_list.append(item_content)
        else:
            # No accordion items, process the section differently (using section's 'strings' or 'text' property)
            if section.strings:
                section_strs = list(section.strings)
                cleaned_section_strs = [Ressource.remove_curly_brackets(section_str.strip()) for section_str in section_strs if section_str.strip()]
                if any(cleaned_section_strs):
                    content_list = cleaned_section_strs
                else: # Extract text content                
                    content_text = Ressource.remove_curly_brackets(section.get_text(separator=' ', strip=True))
                    content_list.append(content_text)

        return content_list
    
    def _build_bullet_lists_str_from_nested_lists(self, content, depth=0, indent_with_tabs = False, indent_count=4)-> str:
        output = ''
        bullets = ['•', '◦', '▪']
        bullet = bullets[depth % len(bullets)]
        
        if indent_with_tabs: indent = '\t' * depth
        else: indent = ' ' * indent_count * depth

        if isinstance(content, dict):
            # Handle dictionaries with 'title' and 'content'
            title = content.get('title', '')
            if title:
                output += Ressource.remove_curly_brackets(f"##{title}##\n")
            if 'content' in content:
                output += self._build_bullet_lists_str_from_nested_lists(content.get('content', []), depth, indent_with_tabs, indent_count)
            else: # Handle other dictionaries
                output += self._build_bullet_lists_str_from_nested_lists(list(content.items()), depth, indent_with_tabs, indent_count)
        elif isinstance(content, list):
            for i, content_item in enumerate(content):
                list_depth = depth if i == 0 else depth + 1 # Increase depth for nested lists with previous item (as a sub-list needs a prior title to justify extra-indentation)
                output += self._build_bullet_lists_str_from_nested_lists(content_item, list_depth, indent_with_tabs, indent_count)
        elif isinstance(content, str):
            output += Ressource.remove_curly_brackets(f"{indent}{bullet} {content}\n")
        else:            
            pass # Handle other types here if needed
        return output

