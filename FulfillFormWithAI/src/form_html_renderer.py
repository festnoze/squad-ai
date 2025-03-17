class FormHTMLRenderer:
    """
    Classe permettant de générer une page HTML pour visualiser un formulaire.
    Chaque groupe est affiché avec son nom en majuscules et un tableau listant
    ses champs avec leur nom, une tooltip pour la description, la valeur,
    et un cadre vert si valide ou rouge si invalide.
    """

    def __init__(self, form):
        """
        :param form: Instance de Form (objet Form déjà créé et validé)
        """
        self.form = form

    def render(self) -> str:
        """
        Construit la page HTML complète sous forme de chaîne de caractères.
        :return: Code HTML complet pour visualiser le formulaire.
        """
        html = [
            '<!DOCTYPE html>',
            '<html lang="fr">',
            '<head>',
            '<meta charset="UTF-8">',
            '<title>{}</title>'.format(self.form.name),
            '<style>',
            '  body { font-family: Arial, sans-serif; margin: 20px; }',
            '  .group { margin-bottom: 30px; }',
            '  table { border-collapse: collapse; border-spacing: 0; width: max-content; }',
            '  table, th { border: 1px solid #ccc; }',
            '  .valid { border: 2px solid green; }',
            '  .invalid { border: 2px solid red; }',
            '  .tooltip { position: relative; display: inline-block; }',
            '  .tooltip .tooltiptext { visibility: hidden; width: 200px; background-color: #555; color: #fff;',
            '    text-align: center; border-radius: 6px; padding: 5px; position: absolute; z-index: 1;',
            '    bottom: 125%; left: 50%; margin-left: -100px; opacity: 0; transition: opacity 0.3s; }',
            '  .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }',
            '  .field-name, .field-spacer, .field-value { padding: 0; }',
'  .field-name { white-space: nowrap; }',
            '  .field-spacer { width: 5px; }',
            '  .field-value { white-space: nowrap; }',
            '  td.field-name, td.field-spacer, td.field-value { padding: 5px !important; }',
            '</style>',
            '</head>',
            '<body>',
            '<h1>{}</h1>'.format(self.form.name)
        ]

        # Pour chaque groupe du formulaire, créer une section avec un tableau de champs
        for group in self.form.groups:
            html.append('<div class="group">')
            html.append('<h2 class="tooltip" title="{}">{}</h2>'.format(group.description, self.format_field_name(group.name)))
            html.append('<table>')
            html.append('<tbody>')
            for field in group.fields:
                valid_class = "valid" if field.is_valid else "invalid"
                valid_text = "Oui" if field.is_valid else "Non"
                html.append('<tr>')
                html.append('<td class="tooltip field-name" title="{}">{}</td>'.format(field.description, self.format_field_name(field.name)))
                html.append('<td class="field-spacer"></td>')
                html.append('<td class="{} field-value">{}</td>'.format(valid_class, field.value))
                html.append('</tr>')
            html.append('</tbody>')
            html.append('</table>')
            html.append('</div>')
        html.append('</body>')
        html.append('</html>')
        return '\n'.join(html)

    def format_field_name(self, name: str) -> str:
        """
        Formate le nom du champ en remplaçant les underscores par des espaces
        et met en majuscules les premiers caractères de chaque mot.
        :param name: Nom du champ à formater
        :return: Nom du champ formaté
        """
        words = name.split('_')
        formatted_name = ' '.join(word.capitalize() for word in words)
        return formatted_name

    def calculate_max_field_length(self) -> int:
        """
        Calcule la longueur maximale parmi tous les noms de champs pour définir la taille de la colonne.
        :return: Longueur maximale des noms de champs en caractères
        """
        max_length = 0
        for group in self.form.groups:
            for field in group.fields:
                max_length = max(max_length, len(field.name))
        return max_length + 2  # Ajoute un peu de marge pour l'affichage
