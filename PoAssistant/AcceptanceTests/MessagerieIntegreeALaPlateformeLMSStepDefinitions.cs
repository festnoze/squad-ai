using System;
using TechTalk.SpecFlow;

namespace AcceptanceTests
{
    [Binding]
    public class MessagerieIntegreeALaPlateformeLMSStepDefinitions
    {
        [Given(@"un utilisateur connecté à la plateforme LMS")]
        public void GivenUnUtilisateurConnecteALaPlateformeLMS()
        {
            throw new PendingStepException();
        }

        [When(@"l’utilisateur envoie un message à un autre utilisateur")]
        public void WhenLUtilisateurEnvoieUnMessageAUnAutreUtilisateur()
        {
            throw new PendingStepException();
        }

        [Then(@"l’utilisateur destinataire reçoit le message instantanément")]
        public void ThenLUtilisateurDestinataireRecoitLeMessageInstantanement()
        {
            throw new PendingStepException();
        }

        [Given(@"l’utilisateur souhaite envoyer une pièce jointe")]
        public void GivenLUtilisateurSouhaiteEnvoyerUnePieceJointe()
        {
            throw new PendingStepException();
        }

        [When(@"la taille de la pièce jointe est supérieure à(.*)MB")]
        public void WhenLaTailleDeLaPieceJointeEstSuperieureAMB(int p0)
        {
            throw new PendingStepException();
        }

        [Then(@"un message d’erreur s’affiche indiquant que la taille de la pièce jointe est trop grande")]
        public void ThenUnMessageDErreurSAfficheIndiquantQueLaTailleDeLaPieceJointeEstTropGrande()
        {
            throw new PendingStepException();
        }

        [When(@"le format de la pièce jointe n’est pas PDF, DOCX, JPG, PNG ou MP(.*)")]
        public void WhenLeFormatDeLaPieceJointeNEstPasPDFDOCXJPGPNGOuMP(int p0)
        {
            throw new PendingStepException();
        }

        [Then(@"un message d’erreur s’affiche indiquant que le format de la pièce jointe est invalide")]
        public void ThenUnMessageDErreurSAfficheIndiquantQueLeFormatDeLaPieceJointeEstInvalide()
        {
            throw new PendingStepException();
        }

        [When(@"un nouvel utilisateur lui envoie un message")]
        public void WhenUnNouvelUtilisateurLuiEnvoieUnMessage()
        {
            throw new PendingStepException();
        }

        [Then(@"une notification s’affiche indiquant qu’un nouveau message a été reçu")]
        public void ThenUneNotificationSAfficheIndiquantQuUnNouveauMessageAEteRecu()
        {
            throw new PendingStepException();
        }

        [Given(@"l’utilisateur souhaite recevoir des notifications par courriel pour les nouveaux messages \(optionnel\)")]
        public void GivenLUtilisateurSouhaiteRecevoirDesNotificationsParCourrielPourLesNouveauxMessagesOptionnel()
        {
            throw new PendingStepException();
        }

        [Then(@"un courriel de notification est envoyé à l’utilisateur")]
        public void ThenUnCourrielDeNotificationEstEnvoyeALUtilisateur()
        {
            throw new PendingStepException();
        }

        [Given(@"l’utilisateur souhaite recevoir des notifications push pour les nouveaux messages \(optionnel\)")]
        public void GivenLUtilisateurSouhaiteRecevoirDesNotificationsPushPourLesNouveauxMessagesOptionnel()
        {
            throw new PendingStepException();
        }

        [Then(@"une notification push est envoyée à l’utilisateur")]
        public void ThenUneNotificationPushEstEnvoyeeALUtilisateur()
        {
            throw new PendingStepException();
        }
    }
}
