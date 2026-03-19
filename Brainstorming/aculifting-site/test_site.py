"""Tests structurels et fonctionnels pour le site Aculifting one-page."""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


HTML_PATH = Path(__file__).parent / "index.html"
CSS_PATH = Path(__file__).parent / "style.css"


class HTMLStructureParser(HTMLParser):
    """Parse HTML and collect structural info."""

    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.classes = set()
        self.links = []
        self.meta_tags = []
        self.aria_labels = []
        self.scripts = 0
        self.styles = 0
        self.forms = []
        self.current_form_inputs = []
        self._in_form = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.tags.append(tag)
        if "id" in attrs_dict:
            self.ids.add(attrs_dict["id"])
        if "class" in attrs_dict:
            for cls in attrs_dict["class"].split():
                self.classes.add(cls)
        if tag == "a" and "href" in attrs_dict:
            self.links.append(attrs_dict["href"])
        if tag == "meta":
            self.meta_tags.append(attrs_dict)
        if "aria-label" in attrs_dict:
            self.aria_labels.append(attrs_dict["aria-label"])
        if tag == "script":
            self.scripts += 1
        if tag == "style":
            self.styles += 1
        if tag == "form":
            self._in_form = True
            self.current_form_inputs = []
            self.forms.append({"action": attrs_dict.get("action", ""), "inputs": self.current_form_inputs})
        if self._in_form and tag == "input":
            self.current_form_inputs.append(attrs_dict)
        if self._in_form and tag == "textarea":
            self.current_form_inputs.append(attrs_dict)

    def handle_endtag(self, tag):
        if tag == "form":
            self._in_form = False


def load_html():
    return HTML_PATH.read_text(encoding="utf-8")


def load_css():
    return CSS_PATH.read_text(encoding="utf-8")


def parse_html(html_content):
    parser = HTMLStructureParser()
    parser.feed(html_content)
    return parser


class TestHTMLValidity(unittest.TestCase):
    """Basic HTML structure validation."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.parser = parse_html(cls.html)

    def test_file_exists(self):
        self.assertTrue(HTML_PATH.exists(), "index.html doit exister")

    def test_doctype(self):
        self.assertTrue(self.html.strip().startswith("<!DOCTYPE html>"), "Doit commencer par <!DOCTYPE html>")

    def test_lang_attribute(self):
        self.assertIn('lang="fr"', self.html, "L'attribut lang='fr' doit être présent")

    def test_charset(self):
        self.assertIn('charset="UTF-8"', self.html, "Le charset UTF-8 doit être défini")

    def test_viewport_meta(self):
        self.assertIn("viewport", self.html, "La meta viewport doit être présente")

    def test_title_tag(self):
        self.assertIn("<title>", self.html, "La balise <title> doit être présente")
        self.assertIn("Yamina Heinrich", self.html)


class TestRequiredSections(unittest.TestCase):
    """Verify all PRD-required sections exist."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.parser = parse_html(cls.html)

    def test_navigation(self):
        self.assertIn("navbar", self.parser.ids, "La navigation (id=navbar) doit exister")

    def test_hero_section(self):
        self.assertIn("hero", self.parser.ids, "La section hero doit exister")

    def test_about_section(self):
        self.assertIn("about", self.parser.ids, "La section à propos doit exister")

    def test_aculifting_section(self):
        self.assertIn("aculifting", self.parser.ids, "La section aculifting doit exister")

    def test_deroulement_section(self):
        self.assertIn("deroulement", self.parser.ids, "La section déroulement doit exister")

    def test_tarifs_section(self):
        self.assertIn("tarifs", self.parser.ids, "La section tarifs doit exister")

    def test_testimonials_section(self):
        self.assertIn("testimonials", self.parser.ids, "La section témoignages doit exister")

    def test_faq_section(self):
        self.assertIn("faq", self.parser.ids, "La section FAQ doit exister")

    def test_contact_section(self):
        self.assertIn("contact", self.parser.ids, "La section contact doit exister")

    def test_footer(self):
        self.assertIn("footer", self.parser.tags, "Le footer doit exister")


class TestSiteConfig(unittest.TestCase):
    """Verify SITE_CONFIG is present and contains required data."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()

    def test_site_config_defined(self):
        self.assertIn("SITE_CONFIG", self.html, "SITE_CONFIG doit être défini")

    def test_practitioner_name(self):
        self.assertIn('"Yamina Heinrich"', self.html, "Le nom de la praticienne doit être dans SITE_CONFIG")

    def test_practitioner_phone(self):
        self.assertIn("06 13 23 86 81", self.html, "Le téléphone doit être présent")

    def test_practitioner_email(self):
        self.assertIn("yaminahinrich@yahoo.fr", self.html, "L'email doit être présent")

    def test_practitioner_address(self):
        self.assertIn("622 avenue Xavier de Ricard", self.html, "L'adresse doit être présente")

    def test_slogan(self):
        self.assertIn("Redonnez éclat et jeunesse à votre visage naturellement", self.html)

    def test_navigation_links(self):
        for section in ["#hero", "#about", "#aculifting", "#tarifs", "#testimonials", "#contact"]:
            self.assertIn(section, self.html, f"Le lien de navigation {section} doit exister")

    def test_benefits_count(self):
        count = len(re.findall(r'icon:\s*"', self.html))
        self.assertEqual(count, 6, f"Il doit y avoir 6 bénéfices dans SITE_CONFIG (trouvé {count})")


class TestVisualIdentity(unittest.TestCase):
    """Verify color palette and typography from business card."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.css = load_css()
        cls.all_content = cls.html + cls.css

    def test_color_rose_powder(self):
        self.assertIn("#F5E6E0", self.all_content, "La couleur rose poudré doit être définie")

    def test_color_gold(self):
        self.assertIn("#C4956A", self.all_content, "La couleur dorée doit être définie")

    def test_color_brown_rose(self):
        self.assertIn("#5A3E36", self.all_content, "La couleur brun-rosé doit être définie")

    def test_font_playfair(self):
        self.assertIn("Playfair Display", self.html, "La police Playfair Display doit être utilisée")

    def test_font_cormorant(self):
        self.assertIn("Cormorant Garamond", self.html, "La police Cormorant Garamond doit être utilisée")

    def test_font_lato(self):
        self.assertIn("Lato", self.html, "La police Lato doit être utilisée")

    def test_google_fonts_loaded(self):
        self.assertIn("fonts.googleapis.com", self.html, "Google Fonts doit être chargé")


class TestResponsiveDesign(unittest.TestCase):
    """Verify responsive breakpoints are defined."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.css = load_css()

    def test_breakpoint_768(self):
        self.assertIn("768px", self.css, "Le breakpoint mobile (768px) doit exister")

    def test_breakpoint_480(self):
        self.assertIn("480px", self.css, "Le breakpoint petit mobile (480px) doit exister")

    def test_nav_toggle_exists(self):
        self.assertIn("nav-toggle", self.html, "Le bouton hamburger doit exister")

    def test_mobile_menu(self):
        self.assertIn("nav-menu", self.html, "Le menu mobile doit exister")

    def test_floating_cta(self):
        self.assertIn("floating-cta", self.html, "Le CTA flottant mobile doit exister")


class TestSEO(unittest.TestCase):
    """SEO and structured data checks."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.parser = parse_html(cls.html)

    def test_meta_description(self):
        meta_descs = [m for m in self.parser.meta_tags if m.get("name") == "description"]
        self.assertTrue(len(meta_descs) > 0, "La meta description doit être présente")
        self.assertIn("Aculifting", meta_descs[0].get("content", ""))

    def test_open_graph_title(self):
        og_titles = [m for m in self.parser.meta_tags if m.get("property") == "og:title"]
        self.assertTrue(len(og_titles) > 0, "L'Open Graph title doit être présent")

    def test_open_graph_description(self):
        og_descs = [m for m in self.parser.meta_tags if m.get("property") == "og:description"]
        self.assertTrue(len(og_descs) > 0, "L'Open Graph description doit être présente")

    def test_schema_org(self):
        self.assertIn("schema.org", self.html, "Le markup Schema.org doit être présent")
        self.assertIn("MedicalBusiness", self.html, "Le type MedicalBusiness doit être défini")

    def test_og_locale(self):
        og_locales = [m for m in self.parser.meta_tags if m.get("property") == "og:locale"]
        self.assertTrue(len(og_locales) > 0, "L'Open Graph locale doit être fr_FR")


class TestAccessibility(unittest.TestCase):
    """Basic accessibility checks."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.parser = parse_html(cls.html)

    def test_aria_labels_exist(self):
        self.assertTrue(len(self.parser.aria_labels) > 0, "Des aria-labels doivent être présents")

    def test_nav_toggle_aria(self):
        self.assertIn("Toggle navigation", self.parser.aria_labels, "Le bouton nav doit avoir un aria-label")

    def test_social_links_aria(self):
        self.assertIn("Instagram", self.parser.aria_labels, "Le lien Instagram doit avoir un aria-label")
        self.assertIn("Facebook", self.parser.aria_labels, "Le lien Facebook doit avoir un aria-label")

    def test_form_labels(self):
        self.assertIn("label", self.parser.tags, "Les champs du formulaire doivent avoir des labels")

    def test_form_required_fields(self):
        self.assertIn('required', self.html, "Le formulaire doit avoir des champs obligatoires")


class TestContactForm(unittest.TestCase):
    """Validate contact form structure."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.parser = parse_html(cls.html)

    def test_form_exists(self):
        self.assertTrue(len(self.parser.forms) > 0, "Le formulaire de contact doit exister")

    def test_form_action(self):
        form = self.parser.forms[0]
        self.assertIn("formsubmit.co", form["action"], "Le formulaire doit utiliser FormSubmit")

    def test_form_method(self):
        self.assertIn('method="POST"', self.html, "Le formulaire doit utiliser POST")

    def test_form_fields(self):
        form = self.parser.forms[0]
        field_names = {inp.get("name", "") for inp in form["inputs"]}
        self.assertIn("name", field_names, "Le champ nom doit exister")
        self.assertIn("email", field_names, "Le champ email doit exister")
        self.assertIn("message", field_names, "Le champ message doit exister")


class TestNavigation(unittest.TestCase):
    """Test internal links are valid."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()
        cls.parser = parse_html(cls.html)

    def test_internal_links_valid(self):
        internal_links = [l for l in self.parser.links if l.startswith("#")]
        valid_ids = self.parser.ids
        for link in internal_links:
            target_id = link[1:]
            self.assertIn(target_id, valid_ids, f"Le lien {link} pointe vers un id inexistant")

    def test_external_links_have_rel(self):
        self.assertIn('rel="noopener noreferrer"', self.html, "Les liens externes doivent avoir rel=noopener noreferrer")

    def test_tel_link(self):
        self.assertIn("tel:+33613238681", self.html, "Le lien téléphone doit exister")

    def test_mailto_link(self):
        self.assertIn("mailto:yaminahinrich@yahoo.fr", self.html, "Le lien email doit exister")


class TestJavaScript(unittest.TestCase):
    """Validate JavaScript functionality markers."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()

    def test_render_functions_exist(self):
        for fn in ["renderNavigation", "renderHero", "renderAbout", "renderAculifting"]:
            self.assertIn(fn, self.html, f"La fonction {fn} doit exister")

    def test_dom_content_loaded(self):
        self.assertIn("DOMContentLoaded", self.html, "L'initialisation DOMContentLoaded doit exister")

    def test_intersection_observer(self):
        self.assertIn("IntersectionObserver", self.html, "L'Intersection Observer doit être utilisé")

    def test_smooth_scroll(self):
        self.assertIn("smooth", self.html, "Le smooth scroll doit être implémenté")

    def test_faq_accordion(self):
        self.assertIn("faq-question", self.html, "L'accordéon FAQ doit exister")

    def test_scroll_animations(self):
        self.assertIn("fade-in", self.html, "Les animations de scroll (fade-in) doivent être définies")


class TestContentCompleteness(unittest.TestCase):
    """Verify all key content sections have data."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()

    def test_faq_items_count(self):
        count = self.html.count("faq-item")
        # Each faq-item appears in HTML + CSS references, count only the div occurrences
        div_count = len(re.findall(r'class="faq-item', self.html))
        self.assertGreaterEqual(div_count, 6, f"Au moins 6 questions FAQ attendues (trouvé {div_count})")

    def test_testimonials_count(self):
        count = len(re.findall(r'class="testimonial-card', self.html))
        self.assertGreaterEqual(count, 3, f"Au moins 3 témoignages attendus (trouvé {count})")

    def test_pricing_cards_count(self):
        count = len(re.findall(r'class="pricing-card', self.html))
        self.assertGreaterEqual(count, 3, f"Au moins 3 cartes tarif attendues (trouvé {count})")

    def test_timeline_steps_count(self):
        count = len(re.findall(r'class="timeline-step', self.html))
        self.assertGreaterEqual(count, 4, f"Au moins 4 étapes timeline attendues (trouvé {count})")

    def test_benefit_icons_defined(self):
        for icon in ["sparkles", "face", "sun", "leaf", "clock", "heart"]:
            self.assertIn(f'"{icon}"', self.html, f"L'icône {icon} doit être définie")

    def test_footer_links(self):
        footer_section = self.html[self.html.index("<footer"):]
        for href in ["#hero", "#aculifting", "#deroulement", "#tarifs", "#testimonials", "#contact"]:
            self.assertIn(href, footer_section, f"Le footer doit contenir le lien {href}")


class TestSingleFileIntegrity(unittest.TestCase):
    """Verify assets are properly linked."""

    @classmethod
    def setUpClass(cls):
        cls.html = load_html()

    def test_no_external_js(self):
        js_scripts = re.findall(r'<script[^>]*src=', self.html)
        self.assertEqual(len(js_scripts), 0, "Aucun JS externe ne doit être chargé")

    def test_css_linked(self):
        self.assertIn('href="style.css"', self.html, "Le CSS doit être lié via style.css")

    def test_css_file_exists(self):
        css_path = Path(__file__).parent / "style.css"
        self.assertTrue(css_path.exists(), "Le fichier style.css doit exister")

    def test_svg_logo_referenced(self):
        self.assertIn("svg", self.html, "Le logo SVG doit être référencé")


if __name__ == "__main__":
    unittest.main(verbosity=2)
