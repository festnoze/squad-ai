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

class ScrapeService:
    def __init__(self):
        pass

    def scrape_all_trainings_links_and_contents(self, max_pagination=17, batch_size=5):
        txt.activate_print = True
        total_start_time = time.time()
        all_trainings_links_filename = "outputs/all_trainings_links.json"
        txt.print_with_spinner("Start scraping all trainings links:")
        all_trainings_links = []
        if file.file_exists(all_trainings_links_filename):
            links_str = file.read_file(all_trainings_links_filename)
            all_trainings_links = json.loads(links_str)
            txt.stop_spinner_replace_text(f"Loaded {len(all_trainings_links)} trainings links.")
        else:
            all_trainings_links = self.get_training_links_all_pages(max_pagination)
            file.write_file(all_trainings_links, all_trainings_links_filename)
            txt.stop_spinner_replace_text(f"Retrieved {len(all_trainings_links)} trainings links completed.")
        
        links_to_process = [
            link for link in all_trainings_links
            if not file.file_exists(f"outputs/scraped/{link.split('/')[-1]}.json")
        ]
        for i in range(0, len(links_to_process), batch_size):
            batch = links_to_process[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                executor.map(self.scrape_and_save_webpage_content, batch)

        #not parallel version
        # for i, link in enumerate(all_tainings_links):
        #     if not file.file_exists(f"outputs/scraped/{link.split('/')[-1]}.json"):
        #         contents = self.scrape_and_save_webpage_content(link)

        elapsed = txt.get_elapsed_seconds(total_start_time, time.time())
        txt.print(f"Scraping all trainings contents completed and saved in {elapsed}s.")        
    
    def get_training_links_all_pages(self, max_pagination=17, batch_size=5):
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
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        hits_list = soup.find('ol', class_='ais-Hits-list')

        if hits_list:
                # Find all links in the hits list
            for item in hits_list.find_all('a', href=True):
                href = item['href']
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
    
    def scrape_and_save_webpage_content(self, training_url):
        training_name = training_url.split("/")[-1]
        txt.print(f"Scraping training content of: '{training_name}'")
        start_time = time.time()
        contents = self.scrape_webpage_content(training_url)
        file.write_file(contents, f"outputs/scraped/{training_name}.json")
        elapsed_str = txt.get_elapsed_str(txt.get_elapsed_seconds(start_time, time.time()))
        txt.print(f"Scraped {len(contents)} sections completed and saved in {elapsed_str}")
    
    def scrape_webpage_content(self, url, section_classes= ['lame-header-training', 'lame-bref', 'lame-programme', 'lame-cards-diploma', 'lame-methode', 'lame-modalites', 'lame-financement', 'lame-simulation'], section_ids= ['jobs']):
        sections = {}

        # Setup Selenium WebDriver
        driver = webdriver.Chrome()
        driver.get(url)
        time.sleep(2)
        if "Ce contenu n'existe pas ou plus." in driver.page_source:
            txt.print(f">>>>> Page not found: '{url}'")
            driver.quit()
            return None
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        title_content_div = soup.find('div', class_='title-content')
        
        if title_content_div:
            # Extract the title from the h1 tag
            h1 = title_content_div.find('h1')
            if h1:
                title = h1.get_text(strip=True)
                sections['title'] = title
            else:
                txt.print(">>> Title not found in 'title-content' div.")

            # Extract the academic level from 'tag-w' ul
            tag_w_ul = title_content_div.find('ul', class_='tag-w')
            if tag_w_ul:
                # Find 'li' elements with class 'tag' inside 'tag-w' ul
                li_tags = tag_w_ul.find_all('li', class_='tag')
                if li_tags and any(li_tags):
                    academic_levels = []
                    for li_tag in li_tags:
                        academic_levels.append(li_tag.get_text(strip=True))
                    sections['academic_level'] = ', '.join(academic_levels)

        # Extract content from the specified sections by their classes
        for section_class in section_classes:
            section = soup.find('section', class_=section_class)
            if section:
                key = section_class.replace('lame-', '')
                sections[key] = self.render_nested_list_as_bullet_lists_str(self.process_section(section))

        # Extract content from the specified sections by their IDs
        for section_id in section_ids:
            section = soup.find('section', id=section_id)
            if section:
                key = section_id.replace('jobs', 'metiers')
                sections[key] = self.render_nested_list_as_bullet_lists_str(self.process_section(section))

        driver.quit()
        sections['url'] = url
        return sections

    def process_section(self, section):
        # Build a nested data structure
        content_list = []

        # Find all accordion items
        accordion_items = section.find_all('div', class_='accordion__item')
        if accordion_items:
            for item in accordion_items:
                # Extract title from accordion-head
                accordion_head = item.find('div', class_='accordion-head')
                if accordion_head:
                    title_span = accordion_head.find('span', class_='title')
                    title = title_span.get_text(strip=True) if title_span else ''
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
                            sub_content.append(bp_text)

                    # Extract bullet points from divs with class 'tag-w' and spans with class 'tag'
                    tag_w_divs = accordion_content.find_all('div', class_='tag-w')
                    for tag_w in tag_w_divs:
                        # Get the label before the tags
                        label = tag_w.get_text(separator=' ', strip=True).split(':')[0]
                        tags = tag_w.find_all('span', class_='tag')
                        tags_text = ', '.join([tag.get_text(strip=True) for tag in tags])
                        if label and tags_text:
                            sub_content.append(f"{label}: {tags_text}")

                    # Extract list items from unordered lists
                    ul_lists = accordion_content.find_all('ul')
                    for ul in ul_lists:
                        li_items = ul.find_all('li')
                        li_sublist = []
                        for li in li_items:
                            li_text = li.get_text(strip=True)
                            if li_text:
                                li_sublist.append(li_text)
                        if li_sublist:
                            sub_content.append(li_sublist)  # Append the list as a sublist

                    # Extract any remaining text paragraphs
                    paragraphs = accordion_content.find_all('p')
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and p_text not in sub_content:
                            sub_content.append(p_text)

                    # Set the content
                    item_content['content'] = sub_content

                else:
                    # Fallback to extracting all text from item
                    item_text = item.get_text(separator=' ', strip=True)
                    item_content['content'].append(item_text)

                # Append this item to the content list
                content_list.append(item_content)
        else:
            # No accordion items, process the section differently
            # Extract text content
            content_text = section.get_text(separator=' ', strip=True)
            content_list.append(content_text)

        return content_list
    
    def render_nested_list_as_bullet_lists_str(self, content, depth=0, indent_count=4)-> str:
        output = ''
        indent = ' ' * (indent_count * depth)
        bullets = ['•', '◦', '▪']
        bullet = bullets[depth % len(bullets)]

        if isinstance(content, dict):
            # Handle dictionary with 'title' and 'content'
            title = content.get('title', '')
            output += f"{indent}{bullet} {title}\n"
            output += self.render_nested_list_as_bullet_lists_str(content.get('content', []), depth + 1, indent_count)
        elif isinstance(content, list):
            for item in content:
                output += self.render_nested_list_as_bullet_lists_str(item, depth, indent_count)
        elif isinstance(content, str):
            output += f"{indent}{bullet} {content}\n"
        else:
            # Handle other types if necessary
            pass

        return output

