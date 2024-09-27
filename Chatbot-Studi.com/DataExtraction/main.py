from textwrap import dedent
from drupal_data_retireval import DrupalDataRetireval
from generate_cleaned_data import GenerateCleanedData

class Main:
    while True:
        choice = input(dedent("""
            ┌──────────────────────────────┐
            │ DATA EXTRACTION - MAIN MENU  │
            └──────────────────────────────┘
            Tap the number of the selected action:  ① ② ③
            1 - Retrieve data from Drupal site
            2 - Generate cleaned data from retireved ones
            3 - Exit
        """))
        if choice == "1":
            DrupalDataRetireval()
        elif choice == "2":
            GenerateCleanedData()
        elif choice == "3":
            print("Exiting ...")
            exit()

if __name__ == '__main__':
    Main()