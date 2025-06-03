import yaml
from pandas_gbq import read_gbq
from google.oauth2 import service_account
import logging
import os

logger = logging.getLogger(__name__)

class SFAgent:    
    def __init__(self, config_path: str = "app/agents/configs/sf_agent.yaml"):
        self.config = self._load_config(config_path)
        self.credentials = self.config["sf_data"]["credentials_path"]
        self.account = None
        logger.info(f"SFAgent initialized with credentials path: {self.credentials}")

    def _load_config(self, file_path):
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            full_path = os.path.join(project_root, file_path)
            with open(full_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading SalesForce configuration file from: '{file_path}': {e}")
            raise

    def get_account_info(self, tel):
        """
        Search for an account with the given phone number in Salesforce data.
        Returns the account info if found, otherwise None.
        """
        try:
            # Cherche dans les données SF, un account avec le numéro de téléphone
            logger.info(f"Looking up account info for phone: {tel}")
            credentials = service_account.Credentials.from_service_account_file(self.credentials)
            project_id = 'data-edg'
            table = "data-edg.DataEDG_US.SF_Account_raw"

            query = f"""
                     SELECT acc.FirstName as FirstName,acc.LastName as LastName,acc.PersonEmail as Email,opp.Id,opp.CreatedDate,user.FirstName as OwnerFirstName,user.LastName as OwnerLastName,user.Username as OwnerEmail 
                     FROM `data-edg.DataEDG_US.SF_Account_raw` acc
            JOIN `DataEDG_US.sf_opportunity_cleaned` opp ON opp.accountId = acc.Id
            JOIN `DataEDG_US.SF_User_raw` user ON opp.OwnerID=user.Id
            WHERE PersonMobilePhone = '{tel}'
            AND opp.end_date = CAST("9999-12-31" AS TIMESTAMP)
            ORDER BY opp.CreatedDate DESC
            """

            df = read_gbq(query, project_id=project_id, credentials=credentials)

            if df.empty:
                logger.info(f"No account found for phone: {tel}")
                return None

            self.account = df.iloc[0].to_dict()
            logger.info(f"Found account for {tel}: {self.account['FirstName']} {self.account['LastName']}")
            return self.account
            
        except Exception as e:
            logger.error(f"Error retrieving account info: {e}", exc_info=True)
            return None
