from textwrap import dedent
from langchain.chains.query_constructor.schema import AttributeInfo
from common_tools.helpers.file_helper import file

class MetadataDescriptionHelper:    
    @staticmethod
    def get_metadata_descriptions_for_studi_public_site(out_dir):
        if not file.file_exists(out_dir + 'all/all_domains_names.json'):
            return None
        domains_names = ', '.join(file.get_as_json(out_dir + 'all/all_domains_names.json'))
        certifications_names = ', '.join(file.get_as_json(out_dir + 'all/all_certifications_names.json'))
        warning_training_only = "Attention : cette meta-data existe uniquement pour les documents relatifs aux formations, c'est à dire ceux où : type = 'formation'. Ne pas ajouter ce filtre pour un type différent que 'formation'."
        list_possible_values = "Prend l'une valeur parmi la liste exhaustive suivante (la valeur est entre simple cotes, et si elle est suivi de parenthèses, il s'agit de sa description)"

        return [
                AttributeInfo(name='id', description="L'identifiant interne du document courant", type='str'),
                AttributeInfo(name='type', description= dedent(f"""\
                    Le type de données contenu dans ce document.
                    Ajoute systématiquement un filtre sur le 'type'. Par défaut ce filtre aura la valeur : 'formation', sauf si la question parle explicitement d'un autre thème listé (comme 'métier' ou 'domaine'), 
                    {list_possible_values} : ['formation', 'métier', 'certifieur', 'certification', 'diplôme', 'domaine']. 
                    Attention, n'appliquer qu'un seul filtre sur 'type' maximum. 
                    Si tu ajoutes : 'type' = 'formation', analyse la demande pour voir si tu ne peux pas aussi ajouter un filtre sur : 'training_info_type', 'name_domain' ou 'name_certification', si on recherche des informations spécifiques sur une formation, ou une formation précise"""), type='str'),
                AttributeInfo(name='name', description="Le nom du document. Par exemple, en conjonction avec le filtre : type equals 'formation', il s'agira du nom de la formation. Attention : à n'utiliser que si le nom exact de l'objet recherché a été précédemment fourni par l'assistant (pas par l'utilisateur).", type='str'),
                AttributeInfo(name='changed', description="La date du dernier changement de la donnée", type='str'),
                AttributeInfo(name='training_info_type', description= dedent(f"""\
                    Spécifie le type d'informations concernant une formation.
                    Attention : cette meta-data n'existe que pour les documents relatifs aux formations, c'est à dire ceux où : type = 'formation'. Ne pas ajouter ce filtre si le type est différent de 'formation'. 
                    {list_possible_values} (la valeur est entre simple cotes, et sa description entre parenthèses) : [
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
                    ]"""), type='str'),
                AttributeInfo(name='name_domain', description= dedent(f"""\
                    Le nom du domaine (ou filière) à laquelle appartient la formation.
                    {list_possible_values} : [{domains_names}].
                    {warning_training_only}"""), type='str'),
                AttributeInfo(name='name_certification', description= dedent(f"""\
                    Le nom du type de diplôme ou du type de certification obtenu au terme de la formation.
                    {list_possible_values} : [{certifications_names}].
                    {warning_training_only}"""), type='str'),
                AttributeInfo(name='url', description="l'URL vers la page web de l'élément recherché. Ne s'applique que pour les types suivants : formation.", type='str'),
                #AttributeInfo(name='rel_ids', description="permet de rechercher les documents connexes à l'id du document fourni en valeur", type='str')
            ]
    