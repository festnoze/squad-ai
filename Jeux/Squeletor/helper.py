from PIL import Image

class Helper:
    def has_transparency(image_path):
        img = Image.open(image_path)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            alpha = img.getchannel("A")
            return any([pix < 255 for pix in alpha.getextrema()])  # Vérifie si au moins un pixel n'est pas opaque
        return False