import datetime
import random
import string
from langchain.tools import tool
from langchain_core.runnables import Runnable
#
from common_tools.helpers.llm_helper import Llm

class ToolsHelper:
    pass    
    
class WordsToolBox:
    llm_or_chain: Runnable = None    
    @tool
    def number_to_french_words(nbr: int):
        """Convert an integer number to a string representation with words in french
        Args:
            nbr (int): The number to convert to words"""
        prompt = f"Convert the number {nbr} to words in french"
        response = WordsToolBox.llm_or_chain.invoke(prompt)
        return Llm.get_llm_answer_content(response)
    
    @tool
    def translate_in_spanish(text: str):
        """Convert a text into spanish
        Args:
            text (str): The text to convert"""
        prompt = f"Convert the following text into spanish: '{text}'"
        response = WordsToolBox.llm_or_chain.invoke(prompt)
        return Llm.get_llm_answer_content(response)
    
    @tool
    def to_lowercase(text):
        """Convert text to lowercase
        Args:
            text (str): The text to convert
        """
        return text.lower()
    
    @tool
    def to_uppercase(text):
        """Convert text to uppercase
        Args:
            text (str): The text to convert"""
        return text.upper()
    
    @tool
    def to_upper_snake_case(text):
        """Convert text to upper snake case
        Args:
            text (str): The text to convert"""
        return text.upper().replace("-", "_").replace(" ", "_")
    
    @tool
    def to_lower_kebab_case(text):
        """Convert text to lower kebab case
        Args:
            text (str): The text to convert"""
        return text.lower().replace("_", "-").replace(" ", "-")
    
    @tool
    def text_to_leet(text):
        """Convert text to leet speak
        Args:
            text (str): The text to convert"""
        leet_dict = {
            'a': '4', 'b': '8', 'c': '<', 'd': 'd', 'e': '3', 'f': 'f', 'g': '6', 'h': '#',
            'i': '1', 'j': 'j', 'k': 'k', 'l': '1', 'm': 'm', 'n': 'n', 'o': '0', 'p': 'p',
            'q': 'q', 'r': 'r', 's': '5', 't': '7', 'u': 'u', 'v': 'v', 'w': 'w', 'x': 'x',
            'y': 'y', 'z': '2', 'A': '4', 'B': '8', 'C': '<', 'D': 'd', 'E': '3', 'F': 'f',
            'G': '6', 'H': '#', 'I': '1', 'J': 'j', 'K': 'k', 'L': '1', 'M': 'm', 'N': 'n',
            'O': '0', 'P': 'p', 'Q': 'q', 'R': 'r', 'S': '5', 'T': '7', 'U': 'u', 'V': 'v',
            'W': 'w', 'X': 'x', 'Y': 'y', 'Z': '2'
        }        
        return ''.join(leet_dict.get(char, char) for char in text)


    
class MathToolBox:
    @tool
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    @tool
    def divide(a: int, b: int) -> float:
        """Divide two numbers."""
        return a / b

    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @tool
    def subtract(a: int, b: int) -> int:
        """Subtract two numbers."""
        return a - b

    @tool
    def power(base: int, exponent: int) -> int:
        """Raise a number to a power."""
        return base ** exponent

    @tool
    def root(base: int, exponent: int) -> float:
        """Take the root of a number."""
        return base ** (1 / exponent)
    
    @tool
    def round_int(nbr: float) -> int:
        """Round a float number to the nearest integer."""
        return round(nbr)





class RandomToolBox:
    @tool
    def get_random_string(length: int) -> str:
        """Get a random string of a given length."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    @tool
    def get_random_number_of_length(length: int) -> str:
        """Get a random number of a given length."""
        return ''.join(random.choices(string.digits, k=length))

    @tool
    def get_random_email():
        """Get a random email address."""
        return RandomToolBox.get_random_string(10) + '@' + RandomToolBox.get_random_string(5) + '.com'
    
    @tool
    def get_random_number():
        """Return a random number between 1 and 100. Take a fake parameter"""
        return random.randint(1, 100)

    @tool
    def get_random_phone_number():
        """Get a random phone number starting with '0' and followed by 9 random digits."""
        return '0' + RandomToolBox.get_random_number_of_length(9)

    @tool
    def get_random_date():
        """Get a random date between 1900 and 2020."""
        return datetime.date(random.randint(1900, 2020), random.randint(1, 12), random.randint(1, 28))

    @tool
    def get_random_datetime():
        """Get a random datetime between 1900 and 2020."""
        return datetime.datetime(random.randint(1900, 2020), random.randint(1, 12), random.randint(1, 28),
                                 random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))

    @tool
    def get_random_time():
        """Get a random time between 0 and 23 hours, 0 and 59 minutes, and 0 and 59 seconds."""
        return datetime.time(random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))

    @tool
    def get_random_boolean():
        """Get a random boolean value (True or False)."""
        return random.choice([True, False])

    @tool
    def get_random_choice(choices):
        """Get a random choice from a list of choices."""
        return random.choice(choices)

    @tool
    def get_random_choices(choices, length):
        """Get a list of random choices from a list of choices with a specified length."""
        return random.choices(choices, k=length)

    @tool
    def get_random_text(length):
        """Get a random text of a given length, consisting of uppercase letters, lowercase letters, digits, and spaces."""
        return ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits + ' ', k=length))

    @tool
    def get_random_paragraph(length):
        """Get a random paragraph of a given length, consisting of random texts with random lengths."""
        return ' '.join([RandomToolBox.get_random_text(random.randint(5, 15)) for _ in range(length)])

    @tool
    def get_random_url():
        """Get a random URL starting with 'http://' followed by a random string and '.com'."""
        return 'http://' + RandomToolBox.get_random_string(10) + '.com'

    @tool
    def get_random_image_url():
        """Get a random image URL starting with 'http://' followed by a random string and '.com/image.png'."""
        return 'http://' + RandomToolBox.get_random_string(10) + '.com/image.png'

    @tool
    def get_random_file_url():
        """Get a random file URL starting with 'http://' followed by a random string and '.com/file.pdf'."""
        return 'http://' + RandomToolBox.get_random_string(10) + '.com/file.pdf'

    @tool
    def get_random_video_url():
        """Get a random video URL starting with 'http://' followed by a random string and '.com'."""
        return 'http://' + RandomToolBox.get_random_string(10) + '.com'