import asyncio
import logging
import re
import time
from typing import Optional, List


class TextQueueManager:
    """
    Classe dédiée à la gestion du texte à synthétiser et envoyer en audio.
    Au lieu de maintenir une file d'attente d'objets audio, cette classe
    maintient une chaîne de texte à traiter progressivement.
    """
    
    def __init__(self, logger=None):
        """Initialise le gestionnaire de texte"""
        self.text_to_send = ""
        self.is_processing = False
        self.lock = asyncio.Lock()
        self.logger = logger or logging.getLogger(__name__)
        
    async def add_text(self, text: str) -> None:
        """
        Ajoute du texte à la fin de la chaîne existante.
        Thread-safe grâce au verrou asyncio.
        
        Args:
            text: Le texte à ajouter
        """
        async with self.lock:
            self.text_to_send += text
            self.logger.debug(f"Texte ajouté, longueur actuelle: {len(self.text_to_send)} caractères")
    
    async def get_next_chunk(self, max_words: int = 10) -> str:
        """
        Récupère le prochain segment de texte à transformer en audio.
        Prend soit la première phrase, soit un maximum de mots spécifié.
        
        Args:
            max_words: Nombre maximum de mots à extraire
            
        Returns:
            Le segment de texte à traiter
        """
        if not self.text_to_send:
            return ""
            
        async with self.lock:
            # Chercher d'abord une phrase complète (se terminant par . ! ? ou :)
            sentence_match = re.search(r'^(.*?[.!?:])\s', self.text_to_send)
            
            if sentence_match:
                # Extraire la première phrase trouvée
                sentence = sentence_match.group(1).strip()
                # Supprimer cette phrase du texte à envoyer (et l'espace qui suit)
                self.text_to_send = self.text_to_send[len(sentence_match.group(0)):]
                return sentence
            
            # Si pas de phrase complète, prendre un nombre limité de mots
            words = self.text_to_send.split()
            
            if not words:
                return ""
                
            if len(words) <= max_words:
                # Prendre tous les mots disponibles
                chunk = self.text_to_send.strip()
                self.text_to_send = ""
                return chunk
            
            # Prendre les max_words premiers mots
            chunk = " ".join(words[:max_words])
            # Supprimer ces mots du texte à envoyer
            self.text_to_send = self.text_to_send[len(chunk):].lstrip()
            return chunk
    
    def is_empty(self) -> bool:
        """
        Vérifie si la file de texte est vide.
        
        Returns:
            True si la file est vide, False sinon
        """
        return len(self.text_to_send) == 0
        
    def get_remaining_size(self) -> int:
        """
        Retourne la taille du texte restant à traiter.
        
        Returns:
            Nombre de caractères restants
        """
        return len(self.text_to_send)
    
    def clear(self) -> None:
        """Vide la file de texte."""
        self.text_to_send = ""
        self.logger.debug("File de texte vidée")
    
    @staticmethod
    def split_text_into_sentences(text: str) -> List[str]:
        """
        Divise un texte en phrases pour un traitement plus naturel.
        
        Args:
            text: Le texte à diviser
            
        Returns:
            Liste de phrases
        """
        # Diviser par les caractères de ponctuation de fin de phrase, en gardant la ponctuation
        sentences = re.findall(r'[^.!?:]+[.!?:]?', text)
        return [s.strip() for s in sentences if s.strip()]
