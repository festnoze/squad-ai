class TextRegistry:
    """Centralized registry for all agent static texts used in TTS pregeneration."""

    # AgentsGraph texts
    start_welcome_text = "Bonjour et bienvenue chez Studi. Je suis l'assistant virtuel de lécole."
    #unavailability_for_returning_prospect = "Votre conseiller attitré est actuellement indisponible."
    unavailability_for_new_prospect = "Nos conseillers en formation sont actuellement indisponibles."
    ask_to_repeat_text = "Désolé, je n'ai pas bien entendu. Merci de répéter."
    # thanks_to_come_back = "Merci de nous recontacter "
    appointment_text = "Je vous propose de prendre rendez-vous avec lui."
    questions_text = "Je peux répondre à vos questions concernant nos formations."
    also_questions_text = "Je peux aussi répondre à vos questions concernant nos formations."
    select_action_text = "Que souhaitez-vous faire ?"
    yes_no_consent_text = "Est-ce que cela vous convient ?"
    ask_question_text = "Comment puis-je vous aider ?"
    technical_error_text = "Je rencontre un problème technique, le service est temporairement indisponible, merci de nous recontacter plus tard. Merci et au revoir."
    lead_agent_error_text = "Je rencontre un problème technique avec l'agent de contact."
    rag_communication_error_text = "Je suis désolé, une erreur s'est produite lors de la communication avec le service."
    max_consecutive_errors_text = "Nous rencontrons actuellement des difficultés à prendre en compte votre demande. Veuillez nous excuser pour le désagréement. Votre appel a été pris en compte et votre conseiller vous recontactera dès que possible. Merci et au revoir."

    # CalendarAgent texts
    availability_request_text = "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?"
    no_timeframes_text = "Quand souhaitez-vous réserver un rendez-vous ?"
    slot_unavailable_text = "Ce créneau n'est pas disponible, souhaiteriez-vous un autre horaire ?"
    confirmation_prefix_text = "Récapitulons : votre rendez-vous sera planifié le "
    confirmation_suffix_text = "Merci de confirmer ce rendez-vous pour le valider."
    date_not_found_text = "Je n'ai pas trouvé la date et l'heure du rendez-vous. Veuillez me préciser la date et l'heure du rendez-vous souhaité."
    appointment_confirmed_prefix_text = "C'est confirmé, votre rendez-vous est maintenant planifié pour le "
    appointment_confirmed_suffix_text = "Merci et au revoir."
    appointment_unavailable_slot_text = "Je suis désolé, ce créneau n'est pas disponible. A la place, "
    appointment_failed_text = "Je n'ai pas pu planifier le rendez-vous. Souhaitez-vous essayer un autre créneau ?"
    modification_not_supported_text = "Je ne suis pas en mesure de gérer les modifications de rendez-vous."
    cancellation_not_supported_text = "Je ne suis pas en mesure de gérer les annulations de rendez-vous."
    no_appointment_requested_text = "Votre appel a bien été prise en compte, votre conseiller en formation vous recontactera dès que possible. Merci et au revoir."
    appointment_too_far_text = "Désolé, il n'est pas possible de prendre de rendez-vous à plus de 30 jours. Quels autres créneaux vous conviendraient ?"

    @classmethod
    def get_all_texts(cls) -> list[str]:
        """Get all text values for pregeneration."""
        # Get all class attributes that are strings (excluding methods and special attributes)
        texts = []
        for attr_name in dir(cls):
            if not attr_name.startswith("_") and not callable(getattr(cls, attr_name)):
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, str):
                    texts.append(attr_value)
        return texts
