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
        self.form.perform_full_validation()

    def render(self) -> str:
        """
        Construit la page HTML complète sous forme de chaîne de caractères.
        :return: Code HTML complet pour visualiser le formulaire.
        """        
        # Calculate max field name length for fixed width column
        max_char_width = self.calculate_max_field_length()

        html = [
            '<!DOCTYPE html>',
            '<html lang="fr">',
            '<head>',
            '<meta charset="UTF-8">',
            '<title>{}</title>'.format(self.form.name),
            '<style>',
            '  body { font-family: Calibri, sans-serif, 20px; margin: 20px; }',
            '  .group { margin-bottom: 30px; }',
            '  table { border-collapse: separate; border-spacing: 8px; padding: 8px; width: 100%; max-width: 1000px; }',
            '  table, th { border: 1px solid #DDD; border-radius: 10px;} ',
            '  .valid { border: 2px solid #0B0; border-radius: 8px;} ',
            '  .invalid { border: 2px solid #E42; border-radius: 8px;} ',
            '  .tooltip { position: relative; display: inline-block; }',
            '  .tooltip .tooltiptext { visibility: hidden; width: 200px; background-color: #555; color: #fff;',
            '    text-align: center; border-radius: 6px; padding: 5px; position: absolute; z-index: 1;',
            '    bottom: 125%; left: 50%; margin-left: -100px; opacity: 0; transition: opacity 0.3s; }',
            '  .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }',
            '  .field-name, .field-spacer, .field-value { padding: 0; }',
            f'  .field-name {{ white-space: nowrap; text-align: right; width: {max_char_width}ch;}}',
            '  .field-spacer { width: 5px; }',
            '  .field-value { white-space: normal; word-wrap: break-word; width: 100%; text-align: left; }',
            '  td.field-name, td.field-spacer, td.field-value { padding: 12px 5px !important; vertical-align: middle; }',
            '  td.valid.field-value, td.invalid.field-value { padding: 10px 5px !important; vertical-align: middle; }',
            '  input, textarea, select { width: 100%; height: 100%; border: none; outline: none; box-sizing: border-box; background: transparent; }',
            '</style>',
            '</head>',
            '<body>',
            '<h1>{}</h1>'.format(self.form.description), 
            '<h3><i>{}</i></h3>'.format(self.format_field_name(self.form.name)),
        ]
        
        
        # Pour chaque groupe du formulaire, créer une section avec un tableau de champs
        for group in self.form.groups:
            html.append('<div>')
            html.append('<h2 class="tooltip" title="{}">{}</h2>'.format(group.description, self.format_field_name(group.name)))
            html.append('<table>')
            html.append('<tbody>')
            for field in group.fields:
                valid_class = "valid" if field.is_valid else "invalid"
                #valid_text = "Oui" if field.is_valid else "Non"
                html.append('<tr>')
                html.append('<td class="tooltip field-name" title="{}">{}</td>'.format(self.format_field_name(field.name), field.description))
                html.append('<td class="field-spacer"></td>')
                html.append('<td class="{} field-value"><input type="text" class="field-input" value="{}" data-field-name="{}" data-field-description="{}" data-is-valid="{}" data-optional="{}" data-type="{}" data-regex="{}" data-regex-description="{}" data-min="{}" data-max="{}" data-validation-func-name="{}" data-default-value="{}" data-allowed-values="{}"></td>'.format(valid_class, field.value if field.value else '', field.name, field.description, field.is_valid, field.optional, field.type, field.regex if field.regex is not None else "", field.regex_description if field.regex_description is not None else "", field.min_size_or_value, field.max_size_or_value, field.validation_func_name if field.validation_func_name is not None else "", field.default_value if field.default_value is not None else "", field.allowed_values if field.allowed_values is not None else ""))
                html.append('</tr>')
            html.append('</tbody>')
            html.append('</table>')
            html.append('</div>')
        html.append('<button id="exportBtn">Export modifications</button>')
        html.append('<script>')
        html.append('document.getElementById("exportBtn").addEventListener("click", function() {')
        html.append('  const formName = document.querySelector("h1").textContent;')
        html.append('  const groups = [];')
        html.append('  document.querySelectorAll("div.group").forEach(div => {')
        html.append('    const groupName = div.getAttribute("data-group-name");')
        html.append('    const groupDesc = div.getAttribute("data-group-description");')
        html.append('    const fields = [];')
        html.append('    div.querySelectorAll("input.field-input").forEach(input => {')
        html.append('      fields.push({')
        html.append('        name: input.getAttribute("data-field-name"),')
        html.append('        value: input.value,')
        html.append('        is_valid: input.getAttribute("data-is-valid") === "True",')
        html.append('        group_name: groupName,')
        html.append('        description: input.getAttribute("data-field-description"),')
        html.append('        optional: input.getAttribute("data-optional") === "True",')
        html.append('        type: input.getAttribute("data-type"),')
        html.append('        regex: input.getAttribute("data-regex") || null,')
        html.append('        regex_description: input.getAttribute("data-regex-description") || null,')
        html.append('        min_size_or_value: input.getAttribute("data-min"),')
        html.append('        max_size_or_value: input.getAttribute("data-max"),')
        html.append('        validation_func_name: input.getAttribute("data-validation-func-name") || null,')
        html.append('        default_value: input.getAttribute("data-default-value") || null,')
        html.append('        allowed_values: input.getAttribute("data-allowed-values") || null')
        html.append('      });')
        html.append('    });')
        html.append('    groups.push({')
        html.append('      name: groupName,')
        html.append('      description: groupDesc,')
        html.append('      fields: fields')
        html.append('    });')
        html.append('  });')
        html.append('  const result = { form: { name: formName, groups: groups } };')
        html.append('  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(result, null, 2));')
        html.append('  const downloadAnchorNode = document.createElement("a");')
        html.append('  downloadAnchorNode.setAttribute("href", dataStr);')
        html.append('  downloadAnchorNode.setAttribute("download", "form.json");')
        html.append('  document.body.appendChild(downloadAnchorNode);')
        html.append('  downloadAnchorNode.click();')
        html.append('  downloadAnchorNode.remove();')
        html.append('});')
        html.append('</script>')
        html.append('</body>')
        html.append('</html>')
        return "\n".join(html)

    def format_field_name(self, name: str) -> str:
        """
        Formate le nom du champ en remplaçant les underscores par des espaces
        et met en majuscules les premiers caractères de chaque mot.
        :param name: Nom du champ à formater
        :return: Nom du champ formaté
        """
        words = name.split('_')
        formatted_name = ' '.join(word.capitalize() if word.lower() == word else word for word in words)
        return f"{formatted_name}"

    def calculate_max_field_length(self) -> int:
        """
        Calcule la longueur maximale parmi tous les noms de champs pour définir la taille de la colonne.
        :return: Longueur maximale des noms de champs en caractères
        """
        max_length = 0
        for group in self.form.groups:
            for field in group.fields:
                max_length = max(max_length, len(field.description))
        return max_length + 4  # Ajoute un peu de marge pour l'affichage
