import argparse
from ocr_folder_images import OCRFolderImages

parser: argparse.ArgumentParser = argparse.ArgumentParser()
parser.add_argument("--folder", default="images_to_ocr", help="Folder containing images to process")
args = parser.parse_args()

title = "La Stratégie des Douze Points Magiques de Dr Tan"
OCRFolderImages(args.folder).process_all_folder_images(title)
#OCRFolderImages(args.folder)._build_index()
#OCRFolderImages(args.folder)._build_viewer()