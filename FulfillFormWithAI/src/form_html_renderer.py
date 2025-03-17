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
            '  .form-row { display: flex; align-items: center; gap: 5px; margin-bottom: 5px; }',
            '  .field-name { flex: 0 0 auto; padding-right: 5px; font-weight: bold; }',
            '  .field-value { flex: 1; padding: 5px; border: 1px solid #ccc; }',
            '  .valid { border-color: green; }',
            '  .invalid { border-color: red; }',
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

        for group in self.form.groups:
            html.append('<div class="group">')
            html.append('<h2 class="tooltip" title="{}">{}</h2>'.format(group.description, group.name.upper()))
            
            for field in group.fields:
                valid_class = "valid" if field.is_valid else "invalid"
                html.append('<div class="form-row">')
                html.append('<div class="field-name tooltip" title="{}">{}</div>'.format(field.description, self.format_field_name(field.name)))
                html.append('<div class="field-value {}">{}</div>'.format(valid_class, field.value))
                html.append('</div>')
            
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
