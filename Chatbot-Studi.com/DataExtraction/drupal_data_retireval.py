from drupal_json_api import DrupalJsonApiClient
from common_tools.helpers import txt, file, json
from common_tools.models import FileAlreadyExistsPolicy
from helpers.unicode_helper import UnicodeHelper
from textwrap import dedent

class DrupalDataRetireval:
    def __init__(self, outdir):
        txt.activate_print = True
        self.out_dir = outdir
        self.studiClient = DrupalJsonApiClient("https://www.studi.com/jsonapi/")
        self.diplay_select_menu()

    def retrieve_all_data(self):
        """ Retrieve all data from studi.com """
        self.retrieve_jobs()
        self.retrieve_fundings()
        self.retrieve_trainings()
        self.retrieve_domains()
        self.retrieve_diplomas()
        self.retrieve_certifications()
        txt.print(">>>>> Finished all drupal data retireval.")

    def retrieve_jobs(self):
        """ Retrieve all jobs from studi.com """
        jobs = self.studiClient.get_jobs()
        self.save_json_file("jobs", jobs)
        txt.print(">>> Finished jobs drupal data retireval ...")

    def retrieve_fundings(self):
        """ Retrieve all fundings from studi.com """
        fundings = self.studiClient.get_fundings()
        self.save_json_file("fundings", fundings)
        txt.print(">>> Finished fundings drupal data retireval ...")

    def retrieve_trainings(self):
        """ Retrieve all trainings from studi.com """
        trainings = self.studiClient.get_trainings()
        self.save_json_file("trainings", trainings)
        txt.print(">>> Finished trainings drupal data retireval ...")

    def retrieve_diplomas(self):
        """ Retrieve all diplomas from studi.com """
        diplomas = self.studiClient.get_diplomas()
        self.save_json_file("diplomas", diplomas)
        txt.print(">>> Finished diplomas drupal data retireval ...")

    def retrieve_certifications(self):
        """ Retrieve all certifications from studi.com """
        certifications = self.studiClient.get_certifications()
        self.save_json_file("certifications", certifications)
        txt.print(">>> Finished certifications drupal data retireval ...")

    def retrieve_domains(self):
        """ Retrieve all domains from studi.com """
        domains = self.studiClient.get_domains()
        self.save_json_file("domains", domains)
        txt.print(">>> Finished domains drupal data retireval ...")

    def display_first_item(self, item_type: str):
        data = file.get_as_str(f"{self.out_dir}{item_type.strip()}.json", encoding='utf-8-sig')
        data = json.loads(data)
        txt.print_json(data[0])

    def diplay_select_menu(self):
        while True:
            choice = input(dedent("""
                ┌──────────────────────────────┐
                │ DRUPAL DATA RETRIEVAL MENU   │
                └──────────────────────────────┘
                Choose an action:  ① ② ③ ④ ⑤ ⑥ ⑦ ⑧

                1 - Retrieve all data (jobs, fundings, trainings, domains, diplomas, certifications) from Drupal
                2 - Retrieve jobs data only from Drupal
                3 - Retrieve fundings data only from Drupal
                4 - Retrieve trainings data only from Drupal
                5 - Retrieve domains data only from Drupal
                6 - Retrieve diplomas data only from Drupal
                7 - Retrieve certifications data only from Drupal
                d - Display first item of specified type
                e - Exit to main menu
            """))
            if choice == "1":
                self.retrieve_all_data()
            elif choice == "2":
                self.retrieve_jobs()
            elif choice == "3":
                self.retrieve_fundings()
            elif choice == "4":
                self.retrieve_trainings()
            elif choice == "5":
                self.retrieve_domains()
            elif choice == "6":
                self.retrieve_diplomas()
            elif choice == "7":
                self.retrieve_certifications()
            elif choice.startswith("d"):
                self.display_first_item(choice[1:])
            elif choice == "e":
                txt.print("Exiting to main menu ...")
                break
    
    def save_json_file(self, filename, data):
        data_str = json.dumps(data, indent=4)
        data_str = UnicodeHelper.replace_ambiguous_unicode_characters(data_str)
        file.write_file(data_str, f"{self.out_dir}{filename}.json", FileAlreadyExistsPolicy.Override)