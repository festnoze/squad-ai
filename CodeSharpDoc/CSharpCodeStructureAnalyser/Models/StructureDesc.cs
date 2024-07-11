using System.Text.Json.Serialization;

namespace CSharpCodeStructureAnalyser.Models;

public record StructureDesc : BaseDesc
{
    [JsonPropertyName("file_path")]
    public string FilePath { get; set; }

    [JsonPropertyName("index_shift_code")]
    public int IndexShiftCode { get; set; }

    [JsonPropertyName("indent_level")]
    public int IndentLevel { get; set; }

    [JsonPropertyName("struct_type")]
    public StructureType StructType { get; set; }

    [JsonPropertyName("namespace_name")]
    public string NamespaceName { get; set; }

    [JsonPropertyName("usings")]
    public List<string> Usings { get; set; }

    [JsonPropertyName("access_modifier")]
    public string AccessModifier { get; set; }

    [JsonPropertyName("struct_name")]
    public string StructName { get; set; }

    [JsonPropertyName("base_class_name")]
    public string BaseClassName { get; set; }

    [JsonPropertyName("existing_summary")]
    public string ExistingSummary { get; set; }

    [JsonPropertyName("interfaces_names")]
    public List<string> InterfacesNames { get; set; }

    [JsonPropertyName("attributs")]
    public List<string> Attributs { get; set; }

    [JsonPropertyName("related_structures")]
    public List<StructureDesc> RelatedStructures { get; set; }

    [JsonPropertyName("methods")]
    public List<MethodDesc> Methods { get; set; }

    [JsonPropertyName("properties")]
    public List<PropertyDesc> Properties { get; set; }

    [JsonPropertyName("enum_members")]
    public EnumMembersDesc? EnumMembers { get; set; }

    [JsonPropertyName("generated_summary")]
    public string? GeneratedSummary { get; set; }

    public StructureDesc(
        string filePath, 
        int indexShiftCode,
        int indentLevel,
        StructureType structType, 
        string namespaceName, 
        List<string> usings, 
        string structName, 
        string accessModifier, 
        string baseClassName, 
        List<string> interfacesNames = null!,
        string existingSummary = "",
        List<string> attributs = null!,
        List<MethodDesc> methods = null!, 
        List<PropertyDesc> properties = null!,
        EnumMembersDesc? enumMembers= null,
        string? generatedSummary = null) : base(structName)
    {
        FilePath = filePath;
        IndexShiftCode = indexShiftCode;
        IndentLevel = indentLevel;
        StructType = structType;
        NamespaceName = namespaceName;
        Usings = usings ?? new List<string>();
        AccessModifier = accessModifier;
        StructName = structName;
        BaseClassName = baseClassName;
        InterfacesNames = interfacesNames ?? new List<string>();
        ExistingSummary = existingSummary;
        Attributs = attributs ?? new List<string>();
        RelatedStructures = new List<StructureDesc>();
        Methods = methods ?? new List<MethodDesc>();
        Properties = properties ?? new List<PropertyDesc>();
        EnumMembers = enumMembers;
        GeneratedSummary = generatedSummary;
    }

    public string ToJson()
    {
        return Newtonsoft.Json.JsonConvert.SerializeObject(this, Newtonsoft.Json.Formatting.Indented);
    }

    public string GenerateCodeFromClassDesc()
    {
        var classFile = string.Empty;
        foreach (var use in Usings)
        {
            classFile += $"using {use};\n";
        }
        classFile += "\n";
        if (!string.IsNullOrEmpty(NamespaceName))
        {
            classFile += $"namespace {NamespaceName};\n\n";
        }
        classFile += $"{AccessModifier} {StructType.ToString().ToLower()} {StructName}";
        if (InterfacesNames.Count > 0)
        {
            classFile += " : " + string.Join(", ", InterfacesNames);
        }
        classFile += "\n{{\n";
        foreach (var prop in Properties)
        {
            classFile += $"{Indent(1)}{prop}\n";
        }
        foreach (var method in Methods)
        {
            classFile += method.ToCode(1, true) + "\n";
        }
        classFile += "}";
        return classFile;
    }

    private string Indent(int level)
    {
        return new string(' ', level * 4);
    }
}
