import os
from textwrap import dedent
from common_tools.models.metadata_description import MetadataDescription
from common_tools.helpers.file_helper import file

class MetadataDescriptionHelper:    
    @staticmethod
    def get_metadata_descriptions_for_studi_public_site(out_dir):
        all_dir = os.path.join(out_dir, 'all')
        domains_names = MetadataDescriptionHelper.get_all_json(all_dir, 'all_domains_names')
        sub_domains_names = MetadataDescriptionHelper.get_all_json(all_dir, 'all_sub_domains_names')
        certifications_names = MetadataDescriptionHelper.get_all_json(all_dir, 'all_certifications_names')
        diplomes_names = MetadataDescriptionHelper.get_all_json(all_dir, 'all_diplomas_names')
        trainings_names = MetadataDescriptionHelper.get_all_json(all_dir, 'all_trainings_names')

        warning_exactitude = "Attention, le texte de la valeur doit correspondre exactement au texte de l'une des valeurs possibles."
        warning_training_only = "Attention : cette meta-data n'existe que pour les documents relatifs aux formations (type = 'formation'). Ne pas ajouter ce filtre pour un type différent que 'formation'."
        and_operator_not_allowed = "Attention : Ne jamais appliquer d'opérateur 'and' entre plusieurs éléments avec cette même clé. (Utilisez plutôt l'opérateur 'or' pour combiner plusieurs éléments avec cette même clé)."
        
        return [
                MetadataDescription(name='id', description="L'identifiant interne du document courant", type='str'),
                MetadataDescription(name='type', description= dedent(f"""\
                    Représente le type de données contenu dans le document.
                    Ajoute systématiquement un filtre sur le 'type'. Ce filtre aura systématiquement la valeur : 'formation', sauf si la question parle explicitement d'un autre thème listé sans lien avec les formations correspondantes (Exemple: demande d'infos sur un 'métier' ou un 'domaine'). 
                    Attention, n'appliquer qu'un seul filtre sur 'type' maximum. Ne jamais utiliser d'opérateurs 'or' ou 'and' pour combiner plusieurs types. Dans ce cas, ne pas mettre de filtre sur 'type'.
                    Si 'type' = 'formation', vérifie si la demande est à un sujet précis concerant la formation, auquel cas, regarde pour aussi ajouter des filtres spécifiques aux formations parmi : 
                    ['domain_name', 'sub_domain_name', 'certification_name', 'academic_level'], si on recherche des informations spécifiques sur une formation, ou une formation précise."""),
                    possible_values= ['formation', 'métier', 'certifieur', 'certification', 'diplôme', 'domaine', 'sous-domaine'],
                    type='str'),
                    # à ajouter à la liste 2 lignes plus haut :  'training_info_type',
                # MetadataDescription(name='training_info_type', description= dedent(f"""\
                #     Le type d'informations spécifique concernant une formation.
                #     {warning_training_only}"""),
                #       possible_values= [
                #         'summary' (résumé factuel de toutes les informations sur la formation),
                #         'bref' (description commerciale concise de la formation),
                #         'header-training' (informations générales sur la formation, dont : description, durée en heures et en mois, type de diplôme ou certification obtenu), 
                #         'programme' (description du contenu détaillé de la formation), 
                #         'cards-diploma' (diplômes obtenus à l'issu de la formation), 
                #         'methode' (description de la méthode de l'école, rarement utile), 
                #         'modalites' (les conditions d'admission, de formation, de passage des examens et autres modalités), 
                #         'financement' (informations sur le tarif, le prix, et le financement et les modes de financement de la formation), 
                #         'simulation' (simulation de la date de début et de la durée de formation, en cas de démarrage à la prochaine session / promotion) 
                #     ],
                #   type='str'),
                MetadataDescription(name='domain_name', description= dedent(f"""\
                    Le nom du domaine auquel appartient la formation. {warning_exactitude}
                    {warning_training_only}
                    {and_operator_not_allowed}"""),
                    possible_values= domains_names,
                    type='str'),
                MetadataDescription(name='sub_domain_name', description= dedent(f"""\
                    Le nom du sous-domaine ou filière auquel appartient la formation. {warning_exactitude}
                    {warning_training_only}
                    {and_operator_not_allowed}"""),
                    possible_values= sub_domains_names,
                    type='str'),
                MetadataDescription(name='certification_name', description= dedent(f"""\
                    Le type de certification obtenu au terme de la formation.
                    {warning_training_only}
                    {and_operator_not_allowed}"""), 
                    possible_values= certifications_names,
                    type='str'),
                MetadataDescription(
                    name='academic_level', 
                    description= dedent(f"""\
                        Le type de diplôme obtenu au terme de la formation.
                        {warning_training_only}
                        {and_operator_not_allowed}"""),
                    possible_values= diplomes_names, 
                    type='str'),
                MetadataDescription(
                    name='name', 
                    description=f"""\
                        Le nom du document. 
                        Par exemple, en conjonction avec le filtre : type = 'formation', il s'agira du nom de la formation.
                        Ce filtre est à utiliser lorsque l'on cherche un élément nommé explicitement (s'applique pour 'type' = ['formation', 'métier']).
                        Ce filtre est utilisable avec n'importe quelle valeur, même partielle ou approximative (car l'élément sémantiquement le plus proche sera alors recherché).""",
                        possible_values=  trainings_names,
                        type='str'),

                # MetadataDescription(name='changed', description="La date du document", type='str'),
                # MetadataDescription(name='url', description="l'URL vers la page web de l'élément recherché. Ne s'applique que pour les types suivants : formation.", type='str'),
                #MetadataDescription(name='rel_ids', description="permet de rechercher les documents connexes à l'id du document fourni en valeur", type='str')
            ]
        
    @staticmethod
    def get_all_json(path, file_name):
        file_name = file_name + '.json'
        file_path = os.path.join(path, file_name)
        if not file.file_exists(file_path): raise ValueError(f"File '{file_path}' does not exist")
        content = file.get_as_json(file_path)
        return content
    
    