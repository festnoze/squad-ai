import re

class UnicodeHelper:
    @staticmethod
    
    def find_ambiguous_characters(content: str) -> list:
        # Define a regex pattern for ambiguous Unicode characters
        ambiguous_chars = re.compile(r"[\u00A0-\u00BF\u2000-\u206F\u2E00-\u2E7F\u3000-\u303F]")

        # Find all ambiguous characters in the content
        matches = ambiguous_chars.findall(content)

        # Return the distinct list of characters
        return list(set(matches))
    
    @staticmethod
    def replace_ambiguous_unicode_characters(content: str) -> str:
        replacements = {
            '’': "'",  # Curly apostrophe to straight
            '‘': "'",  # Left single quote to straight
            '“': '"',  # Left double quote to straight
            '”': '"',  # Right double quote to straight
            '«': '"',  # Left double angle quote to straight double quote
            '»': '"',  # Right double angle quote to straight double quote
            '…': '...',  # Ellipsis to three dots
            '°': '#',  # Degree symbol  to hash
            '⁄': '/',  # Fraction slash to regular slash
            '–': '-',  # En dash to regular hyphen
            '\u00A0': ' ',  # Non-breaking space to regular space
            '\u202F': ' ',  # Narrow no-break space to regular space
            '\u2009': ' ',  # Thin space to regular space
            '\u200A': ' ',  # Hair space to regular space
            '\u200B': '',   # Zero-width space removed
            '\u2060': '',   # Word joiner removed
            '\u2028': '',   # Line separator removed
            '\u2029': '',   # Paragraph separator removed
            '\uFEFF': '',   # Zero-width no-break space removed
            '\u200D': '',   # Zero-width joiner removed            
            }

        pattern = re.compile('|'.join(re.escape(char) for char in replacements.keys()))

        def replace_match(match):
            char = match.group(0)
            return replacements.get(char, '')

        cleaned_content = pattern.sub(replace_match, content)
        return cleaned_content

