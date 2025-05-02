import json
import yaml
import os
import requests
from pandas_gbq import read_gbq
from google.oauth2 import service_account
class SFAgent:
    
    def __init__(self, config_path: str = "sf_agent.yaml"):
        self.config = self._load_config(config_path)
        self.credentials = self.config["sf_data"]["credentials_path"]
        self.account = None

    def _load_config(self, path):
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def get_account_info(self,tel):
        # Cherche dans les données SF, un account avec le numéro de téléphone
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
            return

        self.account = df.iloc[0]
        return 
        
