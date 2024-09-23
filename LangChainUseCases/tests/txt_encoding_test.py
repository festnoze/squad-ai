
import pytest
from helpers.txt_helper import txt

class TestSampleModule:

    def setup_method(self):
        pass

    def teardown_method(self):
        pass
    @pytest.mark.parametrize("input_str, expected_output", 
    [
        ("<p>met en œuvre la stratégie marketing d'une entreprise</p>", "met en œuvre la stratégie marketing d'une entreprise"),
        ("<br>met en oeuvre</br> la <H4>stratégie marketing d'une entreprise</h4>", "met en oeuvre la stratégie marketing d'une entreprise"),
        ("met <p>en oeuvre </p>la <h3>stratégie marketing d'une entreprise</h3>", "met en oeuvre la stratégie marketing d'une entreprise"),
    ])
    def test_remove_html_tags(self, input_str, expected_output):
        assert txt.remove_html_tags(input_str) == expected_output

    @pytest.mark.parametrize("input_str, expected_output", 
    [
        (r"met en \u0153uvre la strat\u00e9gie marketing d\u2019une entreprise", "met en œuvre la stratégie marketing d’une entreprise"),
        (r"veille \u00e0 la r\u00e9alisation de la strat\u00e9gie d\u00e9finie", "veille à la réalisation de la stratégie définie"),
    ])
    def test_replace_unicode_special_chars(self, input_str, expected_output):
        assert txt.replace_unicode_special_chars(input_str) == expected_output

