# C:\Users\e.millerioux\AppData\Local\Programs\Tesseract-OCR\tesseract.exe

# """
# Installation:
# 1. Téléchargez et installez Tesseract OCR pour Windows depuis https://github.com/tesseract-ocr/tesseract (installer recommandé).
# 2. Assurez-vous que le fichier 'fra.traineddata' est présent dans le dossier tessdata (ex : C:\Program Files\Tesseract-OCR\tessdata).
# 3. Installez les dépendances Python :
#    pip install pytesseract pillow
# """
print("OCR pour les images dans le dossier spécifié")
import os
from PIL import Image
import pytesseract
print("Importation des bibliothèques terminée")

# Définissez le chemin vers l'exécutable Tesseract si nécessaire
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\e.millerioux\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# Chemin du dossier contenant les images
input_folder = r"C:\Users\e.millerioux\Downloads\MTC Tan\MTC Tan"  # Modifier ce chemin
# Chemin du dossier où seront enregistrés les résultats OCR
output_folder = r"C:\Users\e.millerioux\Downloads\MTC Tan\ocr"  # Modifier ce chemin

os.makedirs(output_folder, exist_ok=True)

# Traitement de toutes les images du dossier
for filename in os.listdir(input_folder):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
        image_path = os.path.join(input_folder, filename)
        img = Image.open(image_path)
        # Extraction OCR en français
        text = pytesseract.image_to_string(img, lang="fra")
        # Enregistrement du résultat avec la même base de nom et extension .txt
        base_name = os.path.splitext(filename)[0]
        output_path = os.path.join(output_folder, base_name + ".txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
print(f"OCR terminé pour toutes les images du dossier : {input_folder}")
print(f"Résultats enregistrés dans le dossier : {output_folder}")
