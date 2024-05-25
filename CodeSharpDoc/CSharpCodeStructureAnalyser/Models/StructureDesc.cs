namespace CSharpCodeStructureAnalyser.Models;

public record StructureDesc : BaseDesc
{
    public string FilePath { get; set; }
    public int IndexShiftCode { get; set; }
    public StructureType StructType { get; set; }
    public string NamespaceName { get; set; }
    public List<string> Usings { get; set; }
    public string AccessModifier { get; set; }
    public string StructName { get; set; }
    public string BaseClassName { get; set; }
    public List<string> InterfacesNames { get; set; }
    public List<StructureDesc> RelatedStructures { get; set; }
    public List<MethodDesc> Methods { get; set; }
    public List<PropertyDesc> Properties { get; set; }

    public StructureDesc(
        string filePath, 
        int indexShiftCode, 
        StructureType structType, 
        string namespaceName, 
        List<string> usings, 
        string structName, 
        string accessModifier, 
        string baseClassName, 
        List<string> interfacesNames = null!, 
        List<MethodDesc> methods = null!, 
        List<PropertyDesc> properties = null!) : base(structName)
    {
        FilePath = filePath;
        IndexShiftCode = indexShiftCode;
        StructType = structType;
        NamespaceName = namespaceName;
        Usings = usings ?? new List<string>();
        AccessModifier = accessModifier;
        StructName = structName;
        BaseClassName = baseClassName;
        InterfacesNames = interfacesNames ?? new List<string>();
        RelatedStructures = new List<StructureDesc>();
        Methods = methods ?? new List<MethodDesc>();
        Properties = properties ?? new List<PropertyDesc>();
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
