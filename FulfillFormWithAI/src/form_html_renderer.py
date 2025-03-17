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
            '  table { border-collapse: collapse; width: 100%; }',
            '  table, th, td { border: 1px solid #ccc; }',
            '  th, td { padding: 8px; text-align: left; }',
            '  .valid { border: 2px solid green; }',
            '  .invalid { border: 2px solid red; }',
            '  .tooltip { position: relative; display: inline-block; }',
            '  .tooltip .tooltiptext { visibility: hidden; width: 200px; background-color: #555; color: #fff;',
            '    text-align: center; border-radius: 6px; padding: 5px; position: absolute; z-index: 1;',
            '    bottom: 125%; left: 50%; margin-left: -100px; opacity: 0; transition: opacity 0.3s; }',
            '  .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }',
            '</style>',
            '</head>',
            '<body>',
            '<h1>{}</h1>'.format(self.form.name)
        ]

        # Pour chaque groupe du formulaire, créer une section avec un tableau de champs
        for group in self.form.groups:
            html.append('<div class="group">')
            html.append('<h2 class="tooltip" title="{}">{}</h2>'.format(group.description, group.name.upper()))
            html.append('<table>')
            html.append('<thead>')
            html.append('<tr>')
            html.append('<th>Champ</th>')
            html.append('<th>Valeur</th>')
            html.append('</tr>')
            html.append('</thead>')
            html.append('<tbody>')

            for field in group.fields:
                valid_class = "valid" if field.is_valid else "invalid"
                valid_text = "Oui" if field.is_valid else "Non"
                html.append('<tr>')
                html.append('<td class="tooltip" title="{}">{}</td>'.format(field.description, self.format_field_name(field.name)))
                html.append('<td class="{}">{}</td>'.format(valid_class, field.value))
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
