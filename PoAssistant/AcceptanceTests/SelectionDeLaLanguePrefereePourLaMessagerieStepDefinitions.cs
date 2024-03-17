using System;
using TechTalk.SpecFlow;

namespace AcceptanceTests
{
    [Binding]
    public class SelectionDeLaLanguePrefereePourLaMessagerieStepDefinitions
    {
        [Given(@"L’utilisateur est sur la page de paramètres")]
        public void GivenLUtilisateurEstSurLaPageDeParametres()
        {
            throw new PendingStepException();
        }

        [When(@"L’utilisateur clique sur le menu déroulant de sélection de langue")]
        public void WhenLUtilisateurCliqueSurLeMenuDeroulantDeSelectionDeLangue()
        {
            throw new PendingStepException();
        }

        [When(@"L’utilisateur choisit ""([^""]*)"" dans la liste des langues disponibles")]
        public void WhenLUtilisateurChoisitDansLaListeDesLanguesDisponibles(string français)
        {
            throw new PendingStepException();
        }

        [Then(@"L’interface utilisateur affiche ""([^""]*)"" comme langue sélectionnée")]
        public void ThenLInterfaceUtilisateurAfficheCommeLangueSelectionnee(string français)
        {
            throw new PendingStepException();
        }

        [Given(@"L’utilisateur sélectionne ""([^""]*)"" comme langue préférée depuis le menu déroulant")]
        public void GivenLUtilisateurSelectionneCommeLanguePrefereeDepuisLeMenuDeroulant(string anglais)
        {
            throw new PendingStepException();
        }

        [Given(@"L’utilisateur enregistre ses préférences")]
        public void GivenLUtilisateurEnregistreSesPreferences()
        {
            throw new PendingStepException();
        }

        [When(@"L’utilisateur revient sur la page de paramètres")]
        public void WhenLUtilisateurRevientSurLaPageDeParametres()
        {
            throw new PendingStepException();
        }

        [Then(@"Le menu déroulant de sélection de langue affiche ""([^""]*)"" comme langue préférée précédemment sélectionnée")]
        public void ThenLeMenuDeroulantDeSelectionDeLangueAfficheCommeLanguePrefereePrecedemmentSelectionnee(string anglais)
        {
            throw new PendingStepException();
        }

        [Given(@"L’utilisateur a sélectionné ""([^""]*)"" comme langue préférée depuis le menu déroulant")]
        public void GivenLUtilisateurASelectionneCommeLanguePrefereeDepuisLeMenuDeroulant(string espagnol)
        {
            throw new PendingStepException();
        }

        [Given(@"L’utilisateur envoie un message en utilisant la messagerie")]
        public void GivenLUtilisateurEnvoieUnMessageEnUtilisantLaMessagerie()
        {
            throw new PendingStepException();
        }

        [Then(@"Le message est affiché dans la langue ""([^""]*)"" dans la conversation du destinataire")]
        public void ThenLeMessageEstAfficheDansLaLangueDansLaConversationDuDestinataire(string espagnol)
        {
            throw new PendingStepException();
        }
    }
}
