import asyncio
import openai
import os
import sys
from dotenv import find_dotenv, load_dotenv
from ochestrator import assistants_ochestrator

async def main():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Access the value of OPEN_API_KEY
    openai_api_key = os.getenv("OPEN_API_KEY")

    # Set the OpenAI API key
    openai.api_key = openai_api_key

    # List available models
    # ai.print_models()
    # sys.exit()
    max_exchanges_count = 3
    #define the need and send it to the ochestrator
    #need = "je souhaiterais afficher les informations administratives de l'utilisateur"
    need= "je souhaiterais créer un module de messagerie pour que les apprenants puisse communiquer entre eux, mais aussi avec des officiels"
    orchestrator = assistants_ochestrator(need, max_exchanges_count)

    try:
        orchestrator.init_assistants()
        orchestrator.print_assistants_ids()
        str = """```json
{
  "us_desc": "En tant qu'apprenant, je veux pouvoir communiquer via un module de messagerie sur le site LMS, pour interagir avec d'autres apprenants et avec des officiels, y compris pouvoir créer et participer à des groupes de discussion, recevoir des notifications, rechercher et gérer des messages, avec la possibilité pour les officiels de superviser et d'intervenir dans ces échanges quand nécessaire.",
  "use_cases": [
    {
      "uc_desc": "Apprenant envoie et reçoit des messages individuellement ou dans des groupes de discussion",
      "acceptance_criteria": [
        "L'apprenant peut envoyer un message à un autre apprenant ou à un groupe.",
        "L'apprenant reçoit des notifications pour les nouveaux messages.",
        "Les groupes de discussion peuvent être créés par les apprenants."
      ]
    },
    {
      "uc_desc": "Apprenant recherche et gère des messages",
      "acceptance_criteria": [
        "L'apprenant peut rechercher des messages par mots-clés ou par expéditeur.",
        "Les messages peuvent être marqués comme lus/non lus.",
        "L'apprenant peut supprimer des messages ou les marquer comme importants."
      ]
    },
    {
      "uc_desc": "Officiels accèdent et interviennent dans les échanges",
      "acceptance_criteria": [
        "Les officiels peuvent visualiser tous les messages échangés par les apprenants.",
        "Les officiels peuvent répondre directement à un message d'un apprenant.",
        "Il existe un système pour les officiels d'envoyer des messages groupés ou individuels aux apprenants."
      ]
    },
    {
      "uc_desc": "Modération et supervision des messages",
      "acceptance_criteria": [
        "Les apprenants ont la possibilité de signaler un message inapproprié.",
        "Les officiels peuvent superviser et intervenir dans les conversations si nécessaire.",
        "Des mesures sont en place pour la validation des messages par un officiel avant leur publication, si jugé nécessaire."
      ]
    },
    {
      "uc_desc": "Intégration des fonctions supplémentaires et respect de la confidentialité",
      "acceptance_criteria": [
        "Chaque message contient des informations supplémentaires telles que la date/heure d'envoi, la priorité, et le destinataire.",
        "Les officiels doivent évaluer la possibilité pour les apprenants de supprimer leurs propres messages en fonction des politiques de conservation des données.",
        "La fonctionnalité de traduction automatique est disponible pour faciliter la communication entre apprenants de différentes langues."
      ]
    }
  ]
}
```"""
        await orchestrator.write_qa_acceptance_tests_from_us_json_async(str)
        #await orchestrator.run_async()
    except Exception as ex:
        print(ex)
    finally:    
        orchestrator.dispose()
        print("[Fin de l'échange]")


asyncio.run(main())

