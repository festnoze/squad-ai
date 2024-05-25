using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace CSharpCodeStructureAnalyser.Models;

public record PropertyDesc : BaseDesc
{
    public string PropName { get; set; }
    public string PropType { get; set; }
    public bool IsProperty { get; set; }
    public bool IsField => !IsProperty;

    public PropertyDesc(string propName, string propType, bool isProperty = false) : base(propName)
    {
        PropName = propName;
        PropType = propType;
        IsProperty = isProperty;
    }

    public static PropertyDesc GetPropertyDescFromSynthax(PropertyDeclarationSyntax prop)
    {
        return new PropertyDesc(prop.Identifier.Text, prop.Type.ToString(), true);
    }

    public static PropertyDesc GetPropertyDescFromCode(string code)
    {
        var parts = code.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        var propType = parts[0];
        var propName = parts[1].TrimEnd(';');
        return new PropertyDesc(propName, propType, true);
    }
}
