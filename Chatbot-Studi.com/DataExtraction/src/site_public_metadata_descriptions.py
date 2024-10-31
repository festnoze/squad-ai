from textwrap import dedent
from langchain.chains.query_constructor.schema import AttributeInfo
from common_tools.helpers.file_helper import file

class MetadataDescriptionHelper:    
    @staticmethod
    def get_metadata_descriptions_for_studi_public_site(out_dir):
        if not file.file_exists(out_dir + 'all/all_domains_names.json'):
            return None
        domains_names = ', '.join(file.get_as_json(out_dir + 'all/all_domains_names.json'))
        sub_domains_names = ', '.join(file.get_as_json(out_dir + 'all/all_sub_domains_names.json'))
        certifications_names = ', '.join(file.get_as_json(out_dir + 'all/all_certifications_names.json'))
        diplomes_names = ', '.join(file.get_as_json(out_dir + 'all/all_diplomas_names.json'))
        warning_training_only = "Attention : cette meta-data n'existe que pour les documents relatifs aux formations (type = 'formation'). Ne pas ajouter ce filtre pour un type différent que 'formation'."
        and_operator_not_allowed = "Attention : Seul l'opérateur 'or' est utilisable pour combiner plusieurs éléments avec cette même clé, ne jamais appliquer d'opérateur 'and' entre plusieurs éléments avec cette même clé."
        list_possible_values = "Peut prendre une valeur parmi la liste suivante. Chaque élément est sous le format : 'valeur' (description -optionnelle)"

        return [
                #AttributeInfo(name='id', description="L'identifiant interne du document courant", type='str'),
                AttributeInfo(name='type', description= dedent(f"""\
                    Représente le type de données contenu dans le document.
                    Ajoute systématiquement un filtre sur le 'type'. Ce filtre aura systématiquement la valeur : 'formation', sauf si la question parle explicitement d'un autre thème listé sans lien avec les formations correspondantes (Exemple: demande d'infos sur un 'métier' ou un 'domaine').
                    {list_possible_values} : ['formation', 'métier', 'certifieur', 'certification', 'diplôme', 'domaine', 'sous-domaine']. 
                    Attention, n'appliquer qu'un seul filtre sur 'type' maximum. Ne jamais utiliser d'opérateurs 'or' ou 'and' pour combiner plusieurs types. Dans ce cas, ne pas mettre de filtre sur 'type'.
                    Si 'type' = 'formation', vérifie si la demande est à un sujet précis concerant la formation, auquel cas, regarde pour aussi ajouter des filtres spécifiques aux formations parmi : ['training_info_type', 'domaine_name', 'certification_name', 'academic_level'], si on recherche des informations spécifiques sur une formation, ou une formation précise"""), type='str'),
                #AttributeInfo(name='name', description="Le nom du document. Par exemple, en conjonction avec le filtre : type = 'formation', il s'agira du nom de la formation. Attention : à n'utiliser que si le nom exact de l'objet recherché a été précédemment fourni par l'assistant (pas par l'utilisateur).", type='str'),
                #AttributeInfo(name='changed', description="La date du dernier changement de la donnée", type='str'),
                AttributeInfo(name='training_info_type', description= dedent(f"""\
                    Représente le type d'informations spécifique concernant une formation.
                    {list_possible_values} : [
                        'summary' (résumé factuel de toutes les informations sur la formation),
                        'bref' (description commerciale concise de la formation),
                        'header-training' (informations générales sur la formation, dont : description, durée en heures et en mois, type de diplôme ou certification obtenu), 
                        'academic_level' (niveau académique ou niveau d'études de la formation),
                        'programme' (description du contenu détaillé de la formation), 
                        'cards-diploma' (diplômes obtenus à l'issu de la formation), 
                        'methode' (description de la méthode de l'école, rarement utile), 
                        'modalites' (les conditions d'admission, de formation, de passage des examens et autres modalités), 
                        'financement' (informations sur le tarif, le prix, et le financement et les modes de financement de la formation), 
                        'simulation' (simulation de la date de début et de la durée de formation, en cas de démarrage à la prochaine session / promotion) 
                    ]
                    {warning_training_only}"""), type='str'),
                AttributeInfo(name='domaine_name', description= dedent(f"""\
                    Le nom du domaine auquel appartient la formation.
                    {list_possible_values} : [{domains_names}].
                    {warning_training_only}
                    {and_operator_not_allowed}"""), type='str'),
                AttributeInfo(name='sub_domaine_name', description= dedent(f"""\
                    Le nom du sous-domaine ou filière auquel appartient la formation.
                    {list_possible_values} : [{sub_domains_names}].
                    {warning_training_only}
                    {and_operator_not_allowed}"""), type='str'),
                AttributeInfo(name='certification_name', description= dedent(f"""\
                    Uniquement pour les formations, il s'agit du type de certification obtenu au terme de la formation.
                    {list_possible_values} : [{certifications_names}].
                    {warning_training_only}
                    {and_operator_not_allowed}"""), type='str'),
                AttributeInfo(name='academic_level', description= dedent(f"""\
                    Uniquement pour les formations, il s'agit du type de diplôme obtenu au terme de la formation.
                    {list_possible_values} : [{diplomes_names}].
                    {warning_training_only}
                    {and_operator_not_allowed}"""), type='str'),
                AttributeInfo(name='url', description="l'URL vers la page web de l'élément recherché. Ne s'applique que pour les types suivants : formation.", type='str'),
                #AttributeInfo(name='rel_ids', description="permet de rechercher les documents connexes à l'id du document fourni en valeur", type='str')
            ]
    